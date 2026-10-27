from pathlib import Path

import pytest
from flask import Flask

from db import close_db, get_db, init_db, seed_demo_data
from routes.auth import auth_bp
from routes.pages import NAV, pages_bp
from routes.products import products_bp
from routes.settings import settings_bp


@pytest.fixture
def client(tmp_path):
    path = str(tmp_path / "products.db")
    app = Flask(__name__, root_path=str(Path(__file__).parent.parent.parent))
    app.config["DATABASE"] = path
    app.config.update(SECRET_KEY="test-secret", SHOP_JOIN_CODE="test-code")
    init_db(path)
    seed_demo_data(path)
    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(settings_bp)
    app.context_processor(lambda: {"nav": NAV})
    return app.test_client()


def test_product_page_uses_react_products_root(client):
    response = client.get("/products")
    assert response.status_code == 200
    assert b'id="products-root"' in response.data
    assert b"dist/app.js" in response.data


def test_search_matches_sku_barcode_and_product_name(client):
    for term, sku in [
        ("AMY-CHG-20W-WHT", "AMY-CHG-20W-WHT"),
        ("6001000000028", "AMY-CBL-USBC-1M"),
        ("Wired Earphones", "GEN-EAR-WIRED"),
    ]:
        response = client.get("/api/products", query_string={"q": term})
        assert response.status_code == 200
        assert [product["sku"] for product in response.json["products"]] == [sku]


def test_create_product_and_search_by_code(client):
    response = client.post("/api/products", json={
        "name": "Braided USB Cable",
        "brand": "Amaya",
        "category": "Cables",
        "sku": "AMY-CBL-BRAIDED",
        "barcode": "6001000000999",
        "cost": 300,
        "price": 750,
        "stock": 12,
        "reorder_level": 4,
    })
    assert response.status_code == 201
    assert response.json["product"]["label"] == "Braided USB Cable"

    search = client.get("/api/products", query_string={"q": "AMY-CBL-BRAIDED"})
    assert search.status_code == 200
    assert search.json["products"][0]["stock"] == 12


def test_edit_product_and_record_stock_adjustment(client):
    listed = client.get("/api/products", query_string={"q": "AMY-CHG-20W-WHT"}).json["products"][0]
    response = client.put(f"/api/products/{listed['variant_id']}", json={
        "name": listed["name"],
        "brand": listed["brand"],
        "category": listed["category"],
        "sku": listed["sku"],
        "barcode": listed["barcode"],
        "label": listed["label"],
        "cost": listed["cost"],
        "price": 1350,
        "stock": 28,
        "reorder_level": listed["reorder_level"],
    })
    assert response.status_code == 200
    assert response.json["product"]["price"] == 1350
    assert response.json["product"]["stock"] == 28
    assert response.json["product"]["stock"] - listed["stock"] == 3
    with client.application.app_context():
        movement = get_db().execute(
            "SELECT qty_change, reason FROM stock_movements WHERE variant_id = ?",
            (listed["variant_id"],),
        ).fetchone()
    assert (movement["qty_change"], movement["reason"]) == (3, "product_edit")


def test_duplicate_product_code_returns_conflict(client):
    response = client.post("/api/products", json={
        "name": "Duplicate SKU",
        "sku": "AMY-CHG-20W-WHT",
        "price": 100,
    })
    assert response.status_code == 409
    assert "already in use" in response.json["error"]


def test_invalid_product_input_is_rejected(client):
    response = client.post("/api/products", json={
        "name": "Invalid stock",
        "sku": "BAD-STOCK",
        "price": 100,
        "stock": -1,
    })
    assert response.status_code == 400
    assert "non-negative" in response.json["error"]


def test_search_escapes_like_wildcards(client):
    response = client.get("/api/products", query_string={"q": "%"})
    assert response.status_code == 200
    assert response.json["products"] == []
