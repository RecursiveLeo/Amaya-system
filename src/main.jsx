import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const numberFormat = new Intl.NumberFormat("en-KE");
const money = (amount) => `KSh ${numberFormat.format(amount)}`;

function Sidebar({ groups, shopName }) {
  const backendUrl = import.meta.env.DEV
    ? (import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:5000")
    : "";
  const currentPath = window.location.pathname === "/" && import.meta.env.DEV
    ? "/dashboard"
    : window.location.pathname;
  const toggle = document.getElementById("nav-toggle");
  const hrefFor = (href) => {
    if (import.meta.env.DEV && ["/dashboard", "/products"].includes(href)) return href;
    return backendUrl ? new URL(href, backendUrl).href : href;
  };

  function closeMenu() {
    if (toggle) toggle.checked = false;
  }

  return (
    <aside className="sidebar" aria-label="Main navigation">
      <a className="brand" href={hrefFor("/dashboard")}>
        <span className="brand-icon" aria-hidden="true">A</span>
        <span>{shopName}</span>
      </a>
      <div className="nav-section">
        <div className="nav-heading">Workspace</div>
        <a
          className={`nav-link ${currentPath === "/dashboard" ? "active" : ""}`}
          href={hrefFor("/dashboard")}
          aria-current={currentPath === "/dashboard" ? "page" : undefined}
          onClick={closeMenu}
        >
          <span className="nav-symbol" aria-hidden="true">▦</span>
          <span>Dashboard</span>
        </a>
      </div>
      <nav aria-label="Shop navigation">
        {groups.map((group) => (
          <section className="nav-section" key={group.title}>
            <h2 className="nav-heading">{group.title}</h2>
            {group.items.map(([label, href, built], index) => (
              <a
                className={`nav-link ${currentPath === href ? "active" : ""}`}
                href={hrefFor(href)}
                key={href}
                aria-current={currentPath === href ? "page" : undefined}
                onClick={closeMenu}
              >
                <span className="nav-symbol" aria-hidden="true">{["↗", "≡", "◷", "↩", "▤", "◈", "▦"][index % 7]}</span>
                <span>{label}</span>
                {!built && <span className="soon">soon</span>}
              </a>
            ))}
          </section>
        ))}
      </nav>
      <div className="sidebar-footer">
        <span className="footer-avatar" aria-hidden="true">A</span>
        <span><strong>{shopName}</strong><small>Shop management</small></span>
      </div>
    </aside>
  );
}

function MetricCard({ icon, tone, label, value, detail }) {
  return (
    <article className="metric-card">
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        <span className={`metric-icon ${tone}`} aria-hidden="true">{icon}</span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-foot">{detail}</div>
    </article>
  );
}

function SalesChart({ days }) {
  const peak = Math.max(...days.map((item) => item.total), 0);
  return (
    <div className="chart" role="img" aria-label="Daily sales over the last seven days">
      {days.map((item) => {
        const day = new Date(`${item.day}T00:00:00`).toLocaleDateString("en", { weekday: "short" });
        const height = peak ? Math.max(4, (item.total / peak) * 126) : 4;
        return (
          <div className="chart-column" key={item.day}>
            <span className="chart-value">{item.total ? numberFormat.format(item.total) : ""}</span>
            <div className="bar-track"><div className="bar" style={{ height: `${height}px` }} /></div>
            <span className="chart-day">{day}</span>
          </div>
        );
      })}
    </div>
  );
}

function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/dashboard", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Dashboard data request failed (${response.status}).`);
        return response.json();
      })
      .then(setData)
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setError(requestError.message);
      });
    return () => controller.abort();
  }, []);

  if (error) {
    return <div className="load-error" role="alert"><strong>Dashboard could not load.</strong><span>{error}</span></div>;
  }
  if (!data) return <p className="loading" role="status">Loading your shop dashboard…</p>;

  return (
    <div className="dashboard">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Shop overview</p>
          <h1>Dashboard</h1>
          <p className="page-subtitle">Here’s what’s happening in your shop today.</p>
        </div>
        <a className="primary-action" href="/" aria-label="Start a quick sale">
          <span aria-hidden="true">+</span> Start a quick sale
        </a>
      </header>

      <section className="metrics" aria-label="Business summary">
        <MetricCard icon="K" tone="tone-blue" label={data.personal_sales ? "Your sales today" : "Total sales today"} value={money(data.revenue)}
          detail={<>{data.personal_sales ? "Your total" : "All time"}: <strong>{money(data.all_time_sales)}</strong></>} />
        <MetricCard icon="#" tone="tone-green" label={data.personal_sales ? "Your orders today" : "Total orders today"} value={numberFormat.format(data.sales_count)}
          detail={<>{data.personal_sales ? "Your total" : "All time"}: <strong>{numberFormat.format(data.all_time_orders)} orders</strong></>} />
        <MetricCard icon="!" tone="tone-amber" label="Low stock items" value={numberFormat.format(data.low_stock)}
          detail="At or below reorder level" />
        <MetricCard icon="×" tone="tone-red" label="Out of stock" value={numberFormat.format(data.out_of_stock)}
          detail="Items that need replenishing" />
      </section>

      <div className="content-grid">
        <div className="content-column">
          <section className="panel">
            <div className="panel-heading">
              <div><h2>Sales activity</h2><p className="panel-note">Daily sales for the last seven days</p></div>
              <span className="period">Last 7 days</span>
            </div>
            <SalesChart days={data.last_7_days} />
            <div className="summary-row"><span>Gross profit today</span><strong>{money(data.gross_profit)}</strong></div>
            <div className="summary-row"><span>Items sold today</span><strong>{numberFormat.format(data.items_sold)}</strong></div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div><h2>Top sellers</h2><p className="panel-note">Best-selling items today</p></div>
            </div>
            {data.top_sellers.length ? (
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Product</th><th className="align-right">Qty sold</th><th className="align-right">Sales</th></tr></thead>
                  <tbody>{data.top_sellers.map((item) => (
                    <tr key={item.label}><td>{item.label}</td><td className="align-right">{item.qty}</td>
                      <td className="align-right amount">{money(item.amount)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <p className="empty-state">No sales yet today. Start a quick sale to see top sellers.</p>}
          </section>
        </div>

        <div className="content-column">
          <section className="panel">
            <div className="panel-heading">
              <div><h2>Stock alerts</h2><p className="panel-note">Items that need attention</p></div>
              <span className="period">{data.low_stock + data.out_of_stock} alerts</span>
            </div>
            {data.stock_alerts.length ? (
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Product</th><th className="align-right">Stock</th><th className="align-right">Reorder at</th></tr></thead>
                  <tbody>{data.stock_alerts.map((item) => (
                    <tr key={item.label}>
                      <td>{item.label}{item.brand && <small className="brand-name">{item.brand}</small>}</td>
                      <td className="align-right"><span className={`stock-pill ${item.stock <= 0 ? "stock-out" : "stock-low"}`}>
                        {item.stock <= 0 ? "OUT" : item.stock}
                      </span></td>
                      <td className="align-right">{item.reorder_level}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <p className="empty-state">All products are above their reorder level.</p>}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div><h2>Payments today</h2><p className="panel-note">Sales by payment method</p></div>
            </div>
            <div className="payment-list">
              {[["cash", "Cash"], ["mpesa", "M-Pesa"], ["card", "Card"]].map(([method, label]) => (
                <div className="payment-row" key={method}>
                  <span className="payment-name"><span className={`payment-dot dot-${method}`} aria-hidden="true" />{label}</span>
                  <strong>{money(data.by_method[method] || 0)}</strong>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

const emptyProduct = {
  name: "",
  brand: "",
  category: "",
  label: "",
  sku: "",
  barcode: "",
  cost: "0",
  price: "",
  stock: "0",
  reorder_level: "0",
};

function ProductForm({ product, saving, error, onCancel, onSubmit }) {
  const [form, setForm] = useState(product || emptyProduct);

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  function submit(event) {
    event.preventDefault();
    onSubmit(form);
  }

  return (
    <form className="product-form" onSubmit={submit}>
      <div className="form-heading">
        <div>
          <h2>{product ? "Edit product" : "Add a product"}</h2>
          <p className="panel-note">Enter product details and its sellable code.</p>
        </div>
        <button className="text-button" type="button" onClick={onCancel}>Cancel</button>
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-grid">
        <label className="field field-wide">Product name
          <input name="name" value={form.name} onChange={update} required maxLength="120" autoFocus />
        </label>
        <label className="field">Brand
          <input name="brand" value={form.brand || ""} onChange={update} maxLength="80" />
        </label>
        <label className="field">Category
          <input name="category" value={form.category || ""} onChange={update} maxLength="80" />
        </label>
        <label className="field">Product code (SKU)
          <input name="sku" value={form.sku} onChange={update} required maxLength="80" />
        </label>
        <label className="field">Barcode
          <input name="barcode" value={form.barcode || ""} onChange={update} maxLength="80" />
        </label>
        <label className="field field-wide">Variant label <span className="field-hint">Optional; defaults to the product name</span>
          <input name="label" value={form.label || ""} onChange={update} maxLength="160" />
        </label>
        <label className="field">Cost (KSh)
          <input name="cost" type="number" min="0" step="1" value={form.cost} onChange={update} required />
        </label>
        <label className="field">Selling price (KSh)
          <input name="price" type="number" min="0" step="1" value={form.price} onChange={update} required />
        </label>
        <label className="field">Stock quantity
          <input name="stock" type="number" min="0" step="1" value={form.stock} onChange={update} required />
        </label>
        <label className="field">Reorder level
          <input name="reorder_level" type="number" min="0" step="1" value={form.reorder_level} onChange={update} required />
        </label>
      </div>
      <div className="form-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>Cancel</button>
        <button className="primary-action" type="submit" disabled={saving}>
          {saving ? "Saving…" : product ? "Save changes" : "Add product"}
        </button>
      </div>
    </form>
  );
}

function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [query, setQuery] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [formProduct, setFormProduct] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setLoadError("");
      fetch(`/api/products?q=${encodeURIComponent(query)}`, { signal: controller.signal })
        .then(async (response) => {
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error || `Product search failed (${response.status}).`);
          return payload.products;
        })
        .then(setProducts)
        .catch((error) => {
          if (error.name !== "AbortError") setLoadError(error.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [query, refreshToken]);

  function startAdd() {
    setFormProduct(null);
    setFormError("");
    setNotice("");
    setFormOpen(true);
  }

  function startEdit(product) {
    setFormProduct(product);
    setFormError("");
    setNotice("");
    setFormOpen(true);
  }

  async function saveProduct(form) {
    setSaving(true);
    setFormError("");
    setNotice("");
    try {
      const editing = Boolean(formProduct);
      const response = await fetch(
        editing ? `/api/products/${formProduct.variant_id}` : "/api/products",
        {
          method: editing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
        },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `Product save failed (${response.status}).`);
      setQuery("");
      setRefreshToken((value) => value + 1);
      setFormOpen(false);
      setNotice(editing ? "Product changes saved." : "Product added.");
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="products-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Catalog and stock</p>
          <h1>Products</h1>
          <p className="page-subtitle">Add products, find them by code, and keep prices and stock up to date.</p>
        </div>
        <button className="primary-action" type="button" onClick={startAdd}>
          <span aria-hidden="true">+</span> Add product
        </button>
      </header>

      {notice && <p className="success-message" role="status">{notice}</p>}
      {formOpen && <section className="panel form-panel">
        <ProductForm
          key={formProduct ? formProduct.variant_id : "new"}
          product={formProduct}
          saving={saving}
          error={formError}
          onCancel={() => setFormOpen(false)}
          onSubmit={saveProduct}
        />
      </section>}

      <section className="panel products-panel">
        <div className="products-toolbar">
          <div>
            <h2>Product catalog</h2>
            <p className="panel-note">Search by product name, SKU/product code, or barcode.</p>
          </div>
          <label className="search-field">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search products or scan a code"
              aria-label="Search products by name, product code, or barcode"
            />
            {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear search">×</button>}
          </label>
        </div>
        {loadError ? <div className="form-error" role="alert">{loadError}</div> : loading ? (
          <p className="loading" role="status">Loading products…</p>
        ) : products.length ? (
          <div className="table-scroll">
            <table className="products-table">
              <thead><tr>
                <th>Product</th><th>Code / Barcode</th><th className="align-right">Price</th>
                <th className="align-right">Stock</th><th className="align-right">Reorder</th><th><span className="visually-hidden">Actions</span></th>
              </tr></thead>
              <tbody>{products.map((product) => (
                <tr key={product.variant_id}>
                  <td><strong className="product-name">{product.name}</strong>
                    {(product.brand || product.category) && <small className="product-meta">
                      {[product.brand, product.category].filter(Boolean).join(" · ")}
                    </small>}
                    {product.label && product.label !== product.name && <small className="product-meta">{product.label}</small>}
                  </td>
                  <td><span className="product-code">{product.sku}</span>
                    {product.barcode && <small className="product-meta">{product.barcode}</small>}
                  </td>
                  <td className="align-right amount">{money(product.price)}</td>
                  <td className="align-right"><span className={`stock-pill ${product.stock <= 0 ? "stock-out" : product.stock <= product.reorder_level ? "stock-low" : ""}`}>
                    {numberFormat.format(product.stock)}
                  </span></td>
                  <td className="align-right">{numberFormat.format(product.reorder_level)}</td>
                  <td className="align-right"><button className="edit-button" type="button" onClick={() => startEdit(product)}>Edit</button></td>
                </tr>
              ))}</tbody>
            </table>
            {products.length === 200 && <p className="table-footnote">Showing the first 200 matches. Refine your search to find more.</p>}
          </div>
        ) : <div className="empty-products">
          <span className="empty-icon" aria-hidden="true">□</span>
          <strong>{query ? "No matching products" : "No products yet"}</strong>
          <span>{query ? "Try searching by a different name, SKU, or barcode." : "Add your first product to start building your catalog."}</span>
          {!query && <button className="secondary-button" type="button" onClick={startAdd}>Add your first product</button>}
        </div>}
      </section>
    </div>
  );
}

const navData = document.getElementById("nav-data");
const sidebarRoot = document.getElementById("sidebar-root");
const shopConfigData = document.getElementById("shop-config-data");
const dashboardRoot = document.getElementById("dashboard-root");
const productsRoot = document.getElementById("products-root");
const groups = JSON.parse(navData.textContent);
const shopName = shopConfigData
  ? JSON.parse(shopConfigData.textContent).shop_name
  : "Accessories POS";

createRoot(sidebarRoot).render(<Sidebar groups={groups} shopName={shopName} />);
if (productsRoot && window.location.pathname === "/products") {
  if (dashboardRoot) dashboardRoot.remove();
  createRoot(productsRoot).render(<ProductsPage />);
} else if (dashboardRoot) {
  if (productsRoot) productsRoot.remove();
  createRoot(dashboardRoot).render(<Dashboard />);
}
