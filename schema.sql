PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS brands (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  brand_id INTEGER REFERENCES brands(id),
  category_id INTEGER REFERENCES categories(id),
  active INTEGER NOT NULL DEFAULT 1
);

-- The thing you actually scan and sell (e.g. "Amaya 20W Charger / White")
CREATE TABLE IF NOT EXISTS variants (
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  sku TEXT UNIQUE NOT NULL,
  barcode TEXT UNIQUE,
  label TEXT,
  cost INTEGER NOT NULL DEFAULT 0,      -- whole shillings
  price INTEGER NOT NULL,               -- whole shillings
  stock INTEGER NOT NULL DEFAULT 0,
  reorder_level INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_movements (
  id INTEGER PRIMARY KEY,
  variant_id INTEGER NOT NULL REFERENCES variants(id),
  qty_change INTEGER NOT NULL,
  reason TEXT NOT NULL,
  user_id INTEGER REFERENCES users(id),
  note TEXT NOT NULL DEFAULT '',
  ref_type TEXT,
  ref_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'cashier',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shop_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
  id INTEGER PRIMARY KEY,
  shift_id INTEGER,                      -- linked to shifts later
  customer_id INTEGER,                   -- linked to customers later
  user_id INTEGER REFERENCES users(id),
  subtotal INTEGER NOT NULL,
  discount INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL,
  change_given INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'completed',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sale_items (
  id INTEGER PRIMARY KEY,
  sale_id INTEGER NOT NULL REFERENCES sales(id),
  variant_id INTEGER NOT NULL REFERENCES variants(id),
  qty INTEGER NOT NULL,
  unit_price INTEGER NOT NULL,           -- snapshot at time of sale
  unit_cost INTEGER NOT NULL             -- snapshot, keeps profit reports correct
);

CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY,
  sale_id INTEGER NOT NULL REFERENCES sales(id),
  method TEXT NOT NULL,                  -- cash | card | mpesa
  amount INTEGER NOT NULL,               -- amount applied to the sale (change excluded)
  reference TEXT                         -- M-Pesa code or card slip number
);
