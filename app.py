import os
import secrets
import socket
import threading

import webview  # pywebview
from flask import Flask

from db import close_db, get_db, get_db_path, init_db, seed_demo_data
from routes.auth import auth_bp
from routes.inventory import inventory_bp
from routes.pages import NAV, pages_bp
from routes.pos import pos_bp
from routes.products import products_bp
from routes.reports import reports_bp
from routes.settings import MAX_BACKUP_SIZE, settings_bp
from services.settings import get_shop_settings


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SHOP_SECRET_KEY") or secrets.token_hex(32)
    app.config["SHOP_JOIN_CODE"] = "leothuku"
    app.config["DATABASE"] = str(get_db_path())
    app.config["MAX_CONTENT_LENGTH"] = MAX_BACKUP_SIZE + 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    init_db(app.config["DATABASE"])
    seed_demo_data(app.config["DATABASE"])  # remove once you add real products

    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(pages_bp)

    @app.context_processor
    def inject_nav():
        settings = get_shop_settings(get_db())
        return {
            "nav": NAV,
            "shop_name": settings["shop_name"],
            "theme": settings["theme"],
        }
    return app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    app = create_app()
    port = free_port()

    # Run Flask in the background, local only (not reachable from other computers)
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    ).start()

    # Open the desktop window pointing at Flask
    webview.create_window("Accessories POS", f"http://127.0.0.1:{port}", width=1200, height=800)
    webview.start()
