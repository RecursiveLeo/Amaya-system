import sqlite3
from pathlib import Path

import pytest
from flask import Flask

import app as app_module
from db import close_db, get_db, init_db, seed_demo_data
from routes.auth import auth_bp
from routes.pages import NAV, pages_bp
from routes.pos import pos_bp
from routes.settings import settings_bp


@pytest.fixture
def client(tmp_path):
    path = str(tmp_path / "auth.db")
    app = Flask(__name__, root_path=str(Path(__file__).parent.parent))
    app.config.update(
        DATABASE=path,
        SECRET_KEY="test-secret",
        SHOP_JOIN_CODE="shop-code",
    )
    init_db(path)
    seed_demo_data(path)
    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(settings_bp)
    app.context_processor(lambda: {"nav": NAV})
    return app.test_client()


def register(client, username="cashier"):
    return client.post(
        "/register",
        data={
            "full_name": "Test Cashier",
            "username": username,
            "password": "secret123",
            "join_code": "shop-code",
        },
        follow_redirects=True,
    )


def login(client, username="cashier"):
    return client.post(
        "/login",
        data={"username": username, "password": "secret123"},
        follow_redirects=True,
    )


def test_registration_requires_join_code_and_creates_hashed_user(client):
    registration_page = client.get("/register")
    assert b'value="shop-code"' in registration_page.data

    bad_code = client.post(
        "/register",
        data={
            "full_name": "Test Cashier",
            "username": "cashier",
            "password": "secret123",
            "join_code": "wrong",
        },
        follow_redirects=True,
    )
    assert b"Wrong shop join code" in bad_code.data

    response = register(client)
    assert response.status_code == 200
    assert b"Account created. Please log in." in response.data
    with client.application.app_context():
        user = get_db().execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            ("cashier",),
        ).fetchone()
    assert user["username"] == "cashier"
    assert user["password_hash"] != "secret123"
    assert user["role"] == "cashier"


def test_registration_ignores_extra_spaces_around_join_code(client):
    response = client.post(
        "/register",
        data={
            "full_name": "Test Cashier",
            "username": "cashier",
            "password": "secret123",
            "join_code": "  shop-code  ",
        },
        follow_redirects=True,
    )

    assert b"Account created. Please log in." in response.data


def test_login_logout_and_duplicate_registration(client):
    register(client)
    duplicate = register(client)
    assert b"That username is already taken." in duplicate.data

    response = login(client)
    assert b"My sales" in response.data
    client.get("/logout")
    assert client.get("/sales/mine").status_code == 302
    assert "/login" in client.get("/sales/mine").headers["Location"]


def test_sales_routes_require_login(client):
    assert client.get("/sales/new").status_code == 302
    assert client.get("/sales/mine").status_code == 302


def test_sale_uses_variants_records_cashier_and_reduces_stock(client):
    register(client)
    login(client)

    response = client.post(
        "/sales/new",
        data={"product_id": ["1"], "quantity": ["2"]},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Sale #1 recorded" in response.data
    assert b"KSh 2,400.00" in response.data

    with client.application.app_context():
        sale = get_db().execute("SELECT user_id, total FROM sales").fetchone()
        stock = get_db().execute("SELECT stock FROM variants WHERE id = 1").fetchone()[0]
    assert sale["user_id"] == 1
    assert sale["total"] == 2400
    assert stock == 23


def test_sale_rejects_insufficient_stock_without_recording_sale(client):
    register(client)
    login(client)

    response = client.post(
        "/sales/new",
        data={"product_id": ["3"], "quantity": ["4"]},
        follow_redirects=True,
    )
    assert b"Not enough stock" in response.data
    with client.application.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
        assert get_db().execute("SELECT stock FROM variants WHERE id = 3").fetchone()[0] == 3


def test_new_sale_accepts_cash_and_mpesa_split(client):
    register(client)
    login(client)

    response = client.post(
        "/sales/new",
        data={
            "product_id": ["2"],
            "quantity": ["3"],
            "payment_method": "split",
            "mpesa_amount": "500",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Sale #1 recorded" in response.data
    assert b"KSh 1,500.00" in response.data
    with client.application.app_context():
        payments = get_db().execute(
            "SELECT method, amount, reference FROM payments ORDER BY method"
        ).fetchall()
    assert [tuple(payment) for payment in payments] == [
        ("cash", 1000, None),
        ("mpesa", 500, None),
    ]


def test_new_sale_accepts_m_pesa_only(client):
    register(client)
    login(client)

    response = client.post(
        "/sales/new",
        data={
            "product_id": ["2"],
            "quantity": ["1"],
            "payment_method": "mpesa",
            "mpesa_amount": "500",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.application.app_context():
        payment = get_db().execute(
            "SELECT method, amount, reference FROM payments"
        ).fetchone()
    assert tuple(payment) == ("mpesa", 500, None)


def test_registration_requires_configured_shop_join_code(tmp_path):
    app = Flask(__name__, root_path=str(Path(__file__).parent.parent))
    path = str(tmp_path / "unconfigured.db")
    app.config.update(DATABASE=path, SECRET_KEY="test-secret", SHOP_JOIN_CODE="")
    init_db(path)
    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.context_processor(lambda: {"nav": NAV})

    response = app.test_client().post(
        "/register",
        data={
            "full_name": "Test Cashier",
            "username": "cashier",
            "password": "secret123",
            "join_code": "anything",
        },
        follow_redirects=True,
    )
    assert b"Shop registration is not configured" in response.data


def test_init_db_adds_user_id_to_existing_sales_table(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE sales (id INTEGER PRIMARY KEY, subtotal INTEGER NOT NULL, "
        "discount INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL, "
        "change_given INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'completed', "
        "created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()
    conn.close()

    init_db(path)

    conn = sqlite3.connect(path)
    column_names = {row[1] for row in conn.execute("PRAGMA table_info(sales)")}
    conn.close()
    assert "user_id" in column_names


def test_app_uses_leothuku_join_code_even_if_environment_is_set(monkeypatch, tmp_path):
    monkeypatch.setenv("SHOP_JOIN_CODE", "Shop4821")
    monkeypatch.setattr(app_module, "get_db_path", lambda: tmp_path / "app.db")

    app = app_module.create_app()

    assert app.config["SHOP_JOIN_CODE"] == "leothuku"
