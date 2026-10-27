import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from db import close_db, get_db, init_db, seed_demo_data
from routes.auth import auth_bp
from routes.inventory import inventory_bp
from routes.pages import NAV, pages_bp
from routes.settings import settings_bp
from services.inventory import InventoryError, set_stock_count


@pytest.fixture
def app(tmp_path):
    database = str(tmp_path / "inventory.db")
    app = Flask(__name__, root_path=str(Path(__file__).parent.parent))
    app.config.update(DATABASE=database, SECRET_KEY="inventory-test")
    init_db(database)
    seed_demo_data(database)
    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(settings_bp)
    app.context_processor(lambda: {"nav": NAV})
    with app.app_context():
        get_db().execute(
            "INSERT INTO users (full_name, username, password_hash) "
            "VALUES ('Stock Clerk', 'stock-clerk', 'hash')"
        )
        get_db().commit()
    return app


@pytest.fixture
def client(app):
    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["user_id"] = 1
        browser_session["name"] = "Stock Clerk"
    return client


def test_inventory_page_shows_stock_and_movement_history(client):
    with client.application.app_context():
        get_db().execute(
            "INSERT INTO stock_movements (variant_id, qty_change, reason, user_id, note) "
            "VALUES (1, -1, 'stocktake', 1, 'Opening count')"
        )
        get_db().commit()

    response = client.get("/inventory")

    assert response.status_code == 200
    assert b"Stock on hand" in response.data
    assert b"Generic Wired Earphones" in response.data
    assert b"Recent stock movements" in response.data
    assert b"Opening count" in response.data


def test_inventory_api_searches_and_filters_stock(client):
    low = client.get("/api/inventory?stock=low")
    assert low.status_code == 200
    assert [item["sku"] for item in low.json["products"]] == ["GEN-EAR-WIRED"]

    out = client.get("/api/inventory?stock=out")
    assert out.status_code == 200
    assert out.json["products"] == []

    search = client.get("/api/inventory?q=6001000000028")
    assert search.status_code == 200
    assert [item["sku"] for item in search.json["products"]] == ["AMY-CBL-USBC-1M"]


def test_stocktake_saves_count_and_audited_movement(app):
    with app.app_context():
        result = set_stock_count(get_db(), 1, "22", 1, "Physical count")
        variant = get_db().execute("SELECT stock FROM variants WHERE id = 1").fetchone()
        movement = get_db().execute(
            """
            SELECT qty_change, reason, user_id, note FROM stock_movements
            WHERE variant_id = 1 ORDER BY id DESC LIMIT 1
            """
        ).fetchone()

    assert result == {"previous_stock": 25, "stock": 22, "difference": -3}
    assert variant["stock"] == 22
    assert tuple(movement) == (-3, "stocktake", 1, "Physical count")


def test_stocktake_form_redirects_back_to_filtered_inventory(client):
    response = client.post(
        "/inventory/1/stock?q=charger&stock=low",
        data={"counted_stock": "24", "note": "Shelf count", "q": "charger", "stock": "low"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/inventory?q=charger&stock=low"


@pytest.mark.parametrize("counted_stock", ["-1", "1.5", "invalid", ""])
def test_invalid_stocktake_does_not_change_stock(app, counted_stock):
    with app.app_context():
        with pytest.raises(InventoryError):
            set_stock_count(get_db(), 1, counted_stock, 1)
        stock = get_db().execute("SELECT stock FROM variants WHERE id = 1").fetchone()[0]
        movements = get_db().execute(
            "SELECT COUNT(*) FROM stock_movements WHERE variant_id = 1"
        ).fetchone()[0]

    assert stock == 25
    assert movements == 0


def test_stocktake_requires_a_different_count(app):
    with app.app_context():
        with pytest.raises(InventoryError, match="matches current stock"):
            set_stock_count(get_db(), 1, "25", 1)
        assert get_db().execute(
            "SELECT COUNT(*) FROM stock_movements WHERE variant_id = 1"
        ).fetchone()[0] == 0


def test_inventory_pages_and_api_require_login(client):
    with client.session_transaction() as browser_session:
        browser_session.clear()

    assert client.get("/inventory").status_code == 302
    assert client.get("/api/inventory").status_code == 302


def test_stock_movements_capture_cashier_for_pos_sales(app):
    from services.sales import complete_sale

    with app.app_context():
        complete_sale(
            get_db(),
            [{"variant_id": 1, "qty": 1}],
            [{"method": "cash", "amount": 1200}],
            user_id=1,
        )
        movement = get_db().execute(
            "SELECT qty_change, reason, user_id FROM stock_movements "
            "WHERE reason = 'sale' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert tuple(movement) == (-1, "sale", 1)


def test_init_db_migrates_existing_stock_movement_table(tmp_path):
    path = tmp_path / "legacy-inventory.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE brands (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE products (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, brand_id INTEGER, category_id INTEGER,
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE variants (
          id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, sku TEXT UNIQUE NOT NULL,
          barcode TEXT UNIQUE, label TEXT, cost INTEGER NOT NULL DEFAULT 0,
          price INTEGER NOT NULL, stock INTEGER NOT NULL DEFAULT 0,
          reorder_level INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE stock_movements (
          id INTEGER PRIMARY KEY, variant_id INTEGER NOT NULL, qty_change INTEGER NOT NULL,
          reason TEXT NOT NULL, ref_type TEXT, ref_id INTEGER,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE users (
          id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'cashier',
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE sales (
          id INTEGER PRIMARY KEY, subtotal INTEGER NOT NULL, discount INTEGER NOT NULL DEFAULT 0,
          total INTEGER NOT NULL, change_given INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'completed',
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    connection.commit()
    connection.close()

    init_db(path)

    connection = sqlite3.connect(path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(stock_movements)")}
    connection.close()
    assert {"user_id", "note"} <= columns
