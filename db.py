import sqlite3
from pathlib import Path

from flask import current_app, g
from platformdirs import user_data_dir

APP_NAME = "AccessoriesPOS"


def get_db_path() -> Path:
    """Keep the database in the user's app-data folder, not next to the app."""
    folder = Path(user_data_dir(APP_NAME))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "shop.db"


def get_db() -> sqlite3.Connection:
    """One connection per request."""
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(db_path) -> None:
    """Create tables if they don't exist yet."""
    schema = (Path(__file__).parent / "schema.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    movement_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(stock_movements)").fetchall()
    }
    if "user_id" not in movement_columns:
        conn.execute("ALTER TABLE stock_movements ADD COLUMN user_id INTEGER REFERENCES users(id)")
    if "note" not in movement_columns:
        conn.execute("ALTER TABLE stock_movements ADD COLUMN note TEXT NOT NULL DEFAULT ''")
    sales_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(sales)").fetchall()
    }
    if "user_id" not in sales_columns:
        conn.execute("ALTER TABLE sales ADD COLUMN user_id INTEGER REFERENCES users(id)")
    conn.commit()
    conn.close()


def seed_demo_data(db_path) -> None:
    """Add a few sample electronic accessories if the catalog is empty."""
    conn = sqlite3.connect(db_path)
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        conn.execute("INSERT INTO brands (name) VALUES ('Amaya'), ('Anker'), ('Generic')")
        conn.execute("INSERT INTO categories (name) VALUES ('Chargers'), ('Cables'), ('Earphones')")
        conn.execute("INSERT INTO products (name, brand_id, category_id) VALUES "
                     "('20W Fast Charger', 1, 1), ('USB-C Cable 1m', 1, 2), ('Wired Earphones', 3, 3)")
        conn.execute("INSERT INTO variants (product_id, sku, barcode, label, cost, price, stock, reorder_level) VALUES "
                     "(1, 'AMY-CHG-20W-WHT', '6001000000011', 'Amaya 20W Charger / White', 700, 1200, 25, 5), "
                     "(2, 'AMY-CBL-USBC-1M', '6001000000028', 'Amaya USB-C Cable 1m', 250, 500, 40, 10), "
                     "(3, 'GEN-EAR-WIRED', '6001000000035', 'Generic Wired Earphones', 150, 350, 3, 5)")
        conn.commit()
    conn.close()
