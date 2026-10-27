"""Product catalog operations for the products screen."""

import sqlite3


class ProductError(ValueError):
    """An invalid product request or catalog conflict."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


_TEXT_LIMITS = {
    "name": 120,
    "brand": 80,
    "category": 80,
    "label": 160,
    "sku": 80,
    "barcode": 80,
}
_NON_NEGATIVE_FIELDS = ("cost", "price", "stock", "reorder_level")


def _normalize(data):
    if not isinstance(data, dict):
        raise ProductError("Product details must be a JSON object.")

    normalized = {}
    for field, limit in _TEXT_LIMITS.items():
        value = data.get(field, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ProductError(f"{field.replace('_', ' ').title()} must be text.")
        value = value.strip()
        if len(value) > limit:
            raise ProductError(f"{field.replace('_', ' ').title()} must be {limit} characters or fewer.")
        normalized[field] = value

    if not normalized["name"]:
        raise ProductError("Product name is required.")
    if not normalized["sku"]:
        raise ProductError("Product code (SKU) is required.")

    for field in _NON_NEGATIVE_FIELDS:
        value = data.get(field, 0)
        if isinstance(value, bool):
            raise ProductError(f"{field.replace('_', ' ').title()} must be a whole number.")
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ProductError(f"{field.replace('_', ' ').title()} must be a whole number.") from None
        if number < 0 or str(number) != str(value).strip():
            raise ProductError(f"{field.replace('_', ' ').title()} must be a non-negative whole number.")
        normalized[field] = number

    return normalized


def _get_or_create_name(db, table, name):
    if not name:
        return None
    db.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (name,))
    row = db.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()
    return row["id"]


def list_products(db, query=""):
    query = query.strip()
    if len(query) > 100:
        raise ProductError("Search text must be 100 characters or fewer.")
    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = db.execute(
        """
        SELECT p.id AS product_id, v.id AS variant_id, p.name, b.name AS brand,
               c.name AS category, v.label, v.sku, v.barcode, v.cost, v.price,
               v.stock, v.reorder_level
        FROM products p
        JOIN variants v ON v.product_id = p.id
        LEFT JOIN brands b ON b.id = p.brand_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.active = 1
          AND (? = '' OR p.name LIKE ? ESCAPE '\\'
               OR v.label LIKE ? ESCAPE '\\'
               OR v.sku LIKE ? ESCAPE '\\'
               OR COALESCE(v.barcode, '') LIKE ? ESCAPE '\\'
               OR COALESCE(b.name, '') LIKE ? ESCAPE '\\'
               OR COALESCE(c.name, '') LIKE ? ESCAPE '\\')
        ORDER BY p.name COLLATE NOCASE, v.sku COLLATE NOCASE
        LIMIT 200
        """,
        (query, pattern, pattern, pattern, pattern, pattern, pattern),
    )
    return [dict(row) for row in rows]


def save_product(db, data, variant_id=None):
    product = _normalize(data)
    try:
        if variant_id is None:
            brand_id = _get_or_create_name(db, "brands", product["brand"])
            category_id = _get_or_create_name(db, "categories", product["category"])
            cursor = db.execute(
                "INSERT INTO products (name, brand_id, category_id) VALUES (?, ?, ?)",
                (product["name"], brand_id, category_id),
            )
            product_id = cursor.lastrowid
            cursor = db.execute(
                """
                INSERT INTO variants
                    (product_id, sku, barcode, label, cost, price, stock, reorder_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id, product["sku"], product["barcode"] or None,
                    product["label"] or product["name"], product["cost"], product["price"],
                    product["stock"], product["reorder_level"],
                ),
            )
            variant_id = cursor.lastrowid
            if product["stock"]:
                db.execute(
                    "INSERT INTO stock_movements (variant_id, qty_change, reason) VALUES (?, ?, ?)",
                    (variant_id, product["stock"], "initial_stock"),
                )
        else:
            existing = db.execute(
                "SELECT product_id, stock FROM variants WHERE id = ?",
                (variant_id,),
            ).fetchone()
            if existing is None:
                raise ProductError("Product was not found.", 404)
            brand_id = _get_or_create_name(db, "brands", product["brand"])
            category_id = _get_or_create_name(db, "categories", product["category"])
            db.execute(
                "UPDATE products SET name = ?, brand_id = ?, category_id = ? WHERE id = ?",
                (product["name"], brand_id, category_id, existing["product_id"]),
            )
            db.execute(
                """
                UPDATE variants
                SET sku = ?, barcode = ?, label = ?, cost = ?, price = ?, stock = ?, reorder_level = ?
                WHERE id = ?
                """,
                (
                    product["sku"], product["barcode"] or None,
                    product["label"] or product["name"], product["cost"], product["price"],
                    product["stock"], product["reorder_level"], variant_id,
                ),
            )
            stock_change = product["stock"] - existing["stock"]
            if stock_change:
                db.execute(
                    "INSERT INTO stock_movements (variant_id, qty_change, reason) VALUES (?, ?, ?)",
                    (variant_id, stock_change, "product_edit"),
                )

        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        message = str(exc)
        if "variants.sku" in message:
            raise ProductError("That product code (SKU) is already in use.", 409) from exc
        if "variants.barcode" in message:
            raise ProductError("That barcode is already in use.", 409) from exc
        raise ProductError("Product could not be saved because it conflicts with existing catalog data.", 409) from exc
    except Exception:
        db.rollback()
        raise

    saved = db.execute(
        """
        SELECT p.id AS product_id, v.id AS variant_id, p.name, b.name AS brand,
               c.name AS category, v.label, v.sku, v.barcode, v.cost, v.price,
               v.stock, v.reorder_level
        FROM products p
        JOIN variants v ON v.product_id = p.id
        LEFT JOIN brands b ON b.id = p.brand_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE v.id = ?
        """,
        (variant_id,),
    ).fetchone()
    return dict(saved)
