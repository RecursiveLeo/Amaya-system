import io
import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from db import close_db, get_db, init_db, seed_demo_data
from routes.auth import auth_bp
from routes.pages import NAV, pages_bp
from routes.settings import settings_bp
from services.settings import get_shop_settings


@pytest.fixture
def client(tmp_path):
    database = str(tmp_path / "settings.db")
    app = Flask(__name__, root_path=str(Path(__file__).parent.parent))
    app.config.update(DATABASE=database, SECRET_KEY="settings-test")
    init_db(database)
    seed_demo_data(database)
    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(pages_bp)

    @app.context_processor
    def inject_template_settings():
        return {
            "nav": NAV,
            "shop_name": get_shop_settings(get_db())["shop_name"],
            "theme": get_shop_settings(get_db())["theme"],
        }

    test_client = app.test_client()
    with test_client.session_transaction() as browser_session:
        browser_session["user_id"] = 1
        browser_session["name"] = "Test Cashier"
    return test_client


def test_settings_page_is_protected(client):
    with client.session_transaction() as browser_session:
        browser_session.clear()

    response = client.get("/settings")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_shop_details_and_theme_are_saved(client):
    response = client.post(
        "/settings",
        data={
            "shop_name": "Leo's Shop",
            "phone": "+254700000000",
            "address": "Nairobi",
            "theme": "dark",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Settings saved." in response.data
    assert b"Leo&#39;s Shop" in response.data
    assert b'data-theme="dark"' in response.data
    assert b"Switch to light mode" in response.data
    with client.application.app_context():
        settings = get_shop_settings(get_db())
    assert settings == {
        "shop_name": "Leo's Shop",
        "phone": "+254700000000",
        "address": "Nairobi",
        "theme": "dark",
    }


def test_invalid_settings_are_not_saved(client):
    response = client.post(
        "/settings",
        data={"shop_name": " ", "theme": "neon"},
        follow_redirects=True,
    )

    assert b"Enter a shop name." in response.data
    with client.application.app_context():
        assert get_shop_settings(get_db())["shop_name"] == "Accessories POS"


def test_header_theme_switch_saves_preference_and_returns_to_page(client):
    response = client.post(
        "/settings/theme",
        data={"theme": "dark", "next": "/settings"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/settings"
    with client.application.app_context():
        assert get_shop_settings(get_db())["theme"] == "dark"


def test_header_theme_switch_rejects_external_redirect(client):
    response = client.post(
        "/settings/theme",
        data={"theme": "light", "next": "https://example.com"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/settings"
    with client.application.app_context():
        assert get_shop_settings(get_db())["theme"] == "light"


def test_backup_download_is_a_readable_sqlite_copy(client, tmp_path):
    client.post(
        "/settings",
        data={"shop_name": "Backup Shop", "theme": "light"},
    )

    response = client.get("/settings/backup")

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.sqlite3"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    backup_path = tmp_path / "download.sqlite3"
    backup_path.write_bytes(response.data)
    connection = sqlite3.connect(backup_path)
    assert connection.execute(
        "SELECT setting_value FROM shop_settings WHERE setting_key = 'shop_name'"
    ).fetchone()[0] == "Backup Shop"
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()


def test_restore_replaces_database_only_after_confirmation(client):
    client.post(
        "/settings",
        data={"shop_name": "Restored Shop", "theme": "dark"},
    )
    backup = client.get("/settings/backup").data
    client.post(
        "/settings",
        data={"shop_name": "Current Shop", "theme": "light"},
    )

    response = client.post(
        "/settings/restore",
        data={
            "backup_file": (io.BytesIO(backup), "shop.sqlite3"),
            "confirm_restore": "yes",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Database restored successfully." in response.data
    assert b"Restored Shop" in response.data
    with client.application.app_context():
        assert get_shop_settings(get_db())["theme"] == "dark"


def test_invalid_restore_does_not_change_database(client):
    response = client.post(
        "/settings/restore",
        data={
            "backup_file": (io.BytesIO(b"not a database"), "invalid.sqlite3"),
            "confirm_restore": "yes",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"not a readable SQLite database" in response.data
    with client.application.app_context():
        assert get_shop_settings(get_db())["shop_name"] == "Accessories POS"


def test_restore_requires_explicit_confirmation(client):
    response = client.post(
        "/settings/restore",
        data={"backup_file": (io.BytesIO(b"backup"), "shop.sqlite3")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert b"Confirm that you want to replace" in response.data
