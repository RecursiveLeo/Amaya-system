import os
import sqlite3
import tempfile
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from db import get_db
from routes.auth import login_required
from services.settings import THEMES, get_shop_settings, save_shop_settings

settings_bp = Blueprint("settings", __name__)
MAX_BACKUP_SIZE = 100 * 1024 * 1024
REQUIRED_COLUMNS = {
    "brands": {"id", "name"},
    "categories": {"id", "name"},
    "products": {"id", "name", "brand_id", "category_id", "active"},
    "variants": {
        "id", "product_id", "sku", "barcode", "label", "cost", "price", "stock",
        "reorder_level",
    },
    "stock_movements": {
        "id", "variant_id", "qty_change", "reason", "user_id", "note",
        "ref_type", "ref_id", "created_at",
    },
    "users": {"id", "full_name", "username", "password_hash", "role", "created_at"},
    "shop_settings": {"setting_key", "setting_value"},
    "sales": {
        "id", "shift_id", "customer_id", "user_id", "subtotal", "discount", "total",
        "change_given", "status", "created_at",
    },
    "sale_items": {"id", "sale_id", "variant_id", "qty", "unit_price", "unit_cost"},
    "payments": {"id", "sale_id", "method", "amount", "reference"},
}


def _validate_backup(path):
    try:
        conn = sqlite3.connect(path)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("The uploaded database failed its integrity check.")

            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables != REQUIRED_COLUMNS.keys():
                raise ValueError("This file is not a compatible shop database backup.")

            unsupported_object = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('trigger', 'view') "
                "OR (type = 'index' AND name NOT LIKE 'sqlite_autoindex_%') LIMIT 1"
            ).fetchone()
            if unsupported_object is not None:
                raise ValueError("This backup contains unsupported database objects.")

            for table, expected_columns in REQUIRED_COLUMNS.items():
                columns = {
                    row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
                }
                if not expected_columns.issubset(columns):
                    raise ValueError("This backup is missing required shop data.")

            if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("The uploaded database has invalid data references.")
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("The uploaded file is not a readable SQLite database.") from exc


def _create_backup(path):
    with tempfile.TemporaryDirectory() as folder:
        backup_path = Path(folder) / "shop-backup.sqlite3"
        source = sqlite3.connect(path)
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return backup_path.read_bytes()


@settings_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    if request.method == "POST":
        shop_name = request.form.get("shop_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        theme = request.form.get("theme", "")

        if not shop_name:
            flash("Enter a shop name.", "error")
        elif len(shop_name) > 100 or len(phone) > 40 or len(address) > 200:
            flash("Shop details are too long. Please shorten them and try again.", "error")
        elif theme not in THEMES:
            flash("Choose a valid theme.", "error")
        else:
            save_shop_settings(
                get_db(),
                {"shop_name": shop_name, "phone": phone, "address": address, "theme": theme},
            )
            flash("Settings saved.", "success")
            return redirect(url_for("settings.settings_page"))

    return render_template("settings.html", settings=get_shop_settings(get_db()))


@settings_bp.route("/settings/theme", methods=["POST"])
@login_required
def toggle_theme():
    theme = request.form.get("theme", "")
    if theme not in THEMES:
        flash("Choose a valid theme.", "error")
    else:
        save_shop_settings(get_db(), {"theme": theme})
        flash(f"{theme.title()} mode enabled.", "success")

    next_page = request.form.get("next", "")
    parsed_next = urlsplit(next_page)
    if parsed_next.path.startswith("/") and not parsed_next.netloc and not parsed_next.path.startswith("//"):
        return redirect(next_page)
    return redirect(url_for("settings.settings_page"))


@settings_bp.route("/settings/backup")
@login_required
def download_backup():
    try:
        data = _create_backup(current_app.config["DATABASE"])
    except (OSError, sqlite3.Error):
        current_app.logger.exception("Could not create shop database backup")
        flash("Could not create the database backup. Please try again.", "error")
        return redirect(url_for("settings.settings_page"))

    return send_file(
        BytesIO(data),
        mimetype="application/vnd.sqlite3",
        as_attachment=True,
        download_name=f"shop-backup-{date.today().isoformat()}.sqlite3",
    )


@settings_bp.route("/settings/restore", methods=["POST"])
@login_required
def restore_backup():
    upload = request.files.get("backup_file")
    if request.form.get("confirm_restore") != "yes":
        flash("Confirm that you want to replace the current shop database.", "error")
        return redirect(url_for("settings.settings_page"))
    if upload is None or not upload.filename:
        flash("Choose a database backup file to restore.", "error")
        return redirect(url_for("settings.settings_page"))

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            size = 0
            while True:
                chunk = upload.stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BACKUP_SIZE:
                    raise ValueError("Backup file is larger than the 100 MB limit.")
                temp_file.write(chunk)

        _validate_backup(temp_path)
        source = sqlite3.connect(temp_path)
        destination = get_db()
        try:
            source.backup(destination)
        finally:
            source.close()
        session.clear()
        flash("Database restored successfully. Please log in again.", "success")
        return redirect(url_for("auth.login"))
    except ValueError as exc:
        flash(str(exc), "error")
    except (OSError, sqlite3.Error):
        current_app.logger.exception("Could not restore shop database backup")
        flash("Could not restore that backup. The current database was not changed.", "error")
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    return redirect(url_for("settings.settings_page"))
