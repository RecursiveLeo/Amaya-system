import pytest
from flask import Flask

from db import close_db, get_db, init_db, seed_demo_data
from routes.auth import auth_bp
from routes.inventory import inventory_bp
from routes.pages import NAV, pages_bp
from routes.pos import pos_bp
from routes.products import products_bp
from routes.reports import reports_bp
from routes.settings import settings_bp


@pytest.fixture
def client(tmp_path):
    path = str(tmp_path / "t.db")
    app = Flask(__name__, root_path=str(__import__("pathlib").Path(__file__).parent.parent))
    app.config["DATABASE"] = path
    init_db(path)
    seed_demo_data(path)
    app.teardown_appcontext(close_db)
    app.config.update(SECRET_KEY="test-secret", SHOP_JOIN_CODE="test-code")
    for bp in (
        auth_bp, inventory_bp, pos_bp, products_bp, reports_bp, settings_bp, pages_bp
    ):
        app.register_blueprint(bp)
    app.context_processor(lambda: {"nav": NAV})
    with app.app_context():
        get_db().execute(
            "INSERT INTO users (full_name, username, password_hash) "
            "VALUES ('Test Cashier', 'test-cashier', 'hash')"
        )
        get_db().commit()
    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["user_id"] = 1
        browser_session["name"] = "Test Cashier"
    return client


def test_every_sidebar_link_opens(client):
    hrefs = ["/dashboard"] + [href for g in NAV for _, href, _ in g["items"]]
    for href in hrefs:
        assert client.get(href, follow_redirects=True).status_code == 200, href


def test_sidebar_shows_all_groups(client):
    html = client.get("/dashboard").get_data(as_text=True)
    for text in ["1. Quick Sales", "Quick sales", "Sales", "Shifts", "Returns",
                 "2. Catalog and Stock", "Products", "Categories", "Quick-pick grid",
                 "3. Supply Chain", "Supplies", "Receiving", "Inventory",
                 "4. Business", "Customers", "Expenses", "Reports", "Settings"]:
        assert text in html


def test_dashboard_shows_requested_summary_metrics(client):
    html = client.get("/dashboard").get_data(as_text=True)
    for text in ["dashboard-root", "dist/app.css", "dist/app.js"]:
        assert text in html


def test_dashboard_api_returns_metrics_and_chart_data(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.get_json()
    assert data["revenue"] == 0
    assert data["sales_count"] == 0
    assert data["low_stock"] == 1
    assert data["out_of_stock"] == 0
    assert len(data["last_7_days"]) == 7


def test_dashboard_requires_login(client):
    with client.session_transaction() as browser_session:
        browser_session.clear()

    assert client.get("/dashboard").status_code == 302
    assert client.get("/api/dashboard").status_code == 302


def test_quick_sales_uses_shared_sidebar(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Accessories POS" in html
    assert "4. Business" in html
    assert 'id="scan"' in html
    assert 'id="checkout"' in html
    assert 'id="payment-method"' in html
    assert "Cash + M-Pesa (split)" in html
    assert "M-Pesa transaction code" not in html
    assert "/pos/checkout" in html


def test_quick_checkout_records_cash_mpesa_split(client):
    response = client.post(
        "/pos/checkout",
        json={
            "items": [{"variant_id": 1, "qty": 1}, {"variant_id": 2, "qty": 1}],
            "payments": [
                {"method": "cash", "amount": 1000},
                {"method": "mpesa", "amount": 700},
            ],
        },
    )

    assert response.status_code == 201
    assert response.json["total"] == 1700
    with client.application.app_context():
        payments = get_db().execute(
            "SELECT method, amount FROM payments ORDER BY method"
        ).fetchall()
    assert [tuple(payment) for payment in payments] == [
        ("cash", 1000),
        ("mpesa", 700),
    ]


def test_quick_sale_checkout_records_sale_and_updates_dashboard(client):
    response = client.post(
        "/pos/checkout",
        json={
            "items": [{"variant_id": 1, "qty": 1}],
            "payments": [{"method": "cash", "amount": 1200}],
        },
    )
    assert response.status_code == 201
    assert response.json["total"] == 1200

    dashboard = client.get("/api/dashboard").get_json()
    assert dashboard["sales_count"] == 1
    assert dashboard["all_time_orders"] == 1


def test_dashboard_only_shows_the_signed_in_cashiers_sales(client):
    with client.application.app_context():
        get_db().execute(
            "INSERT INTO users (full_name, username, password_hash) "
            "VALUES ('Second Cashier', 'second-cashier', 'hash')"
        )
        get_db().commit()

    for variant_id, amount in [(1, 1200), (2, 500)]:
        response = client.post(
            "/pos/checkout",
            json={
                "items": [{"variant_id": variant_id, "qty": 1}],
                "payments": [{"method": "cash", "amount": amount}],
            },
        )
        assert response.status_code == 201
        if variant_id == 1:
            with client.session_transaction() as browser_session:
                browser_session["user_id"] = 2
                browser_session["name"] = "Second Cashier"

    dashboard = client.get("/api/dashboard").get_json()

    assert dashboard["personal_sales"] is True
    assert dashboard["sales_count"] == 1
    assert dashboard["revenue"] == 500
    assert dashboard["all_time_orders"] == 1
    assert dashboard["all_time_sales"] == 500
    assert dashboard["by_method"] == {"cash": 500}
    assert dashboard["top_sellers"][0]["label"] == "Amaya USB-C Cable 1m"
    assert dashboard["last_7_days"][-1]["total"] == 500
