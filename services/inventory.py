import sqlite3


class InventoryError(ValueError):
    """An invalid inventory request or stock conflict."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def list_inventory(db, query="", stock_filter="all"):
    query = query.strip()
    if len(query) > 100:
        raise InventoryError("Search text must be 100 characters or fewer.")
    if stock_filter not in {"all", "low", "out"}:
        raise InventoryError("Choose a valid stock filter.")

    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    conditions = ["p.active = 1"]
    params = []
    if query:
        conditions.append(
            "(p.name LIKE ? ESCAPE '\\' OR COALESCE(v.label, '') LIKE ? ESCAPE '\\' "
            "OR v.sku LIKE ? ESCAPE '\\' OR COALESCE(v.barcode, '') LIKE ? ESCAPE '\\' "
            "OR COALESCE(b.name, '') LIKE ? ESCAPE '\\' "
            "OR COALESCE(c.name, '') LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern] * 6)
    if stock_filter == "low":
        conditions.append("v.stock > 0 AND v.stock <= v.reorder_level")
    elif stock_filter == "out":
        conditions.append("v.stock <= 0")

    products = [
        dict(row)
        for row in db.execute(
            """
            SELECT v.id AS variant_id, p.name, b.name AS brand, c.name AS category,
                   COALESCE(v.label, p.name) AS label, v.sku, v.barcode,
                   v.cost, v.stock, v.reorder_level
            FROM variants v
            JOIN products p ON p.id = v.product_id
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE """
            + " AND ".join(conditions)
            + " ORDER BY p.name COLLATE NOCASE, v.sku COLLATE NOCASE LIMIT 500",
            params,
        )
    ]

    summary = db.execute(
        """
        SELECT COUNT(*) AS items,
               COALESCE(SUM(CASE WHEN v.stock > 0 AND v.stock <= v.reorder_level THEN 1 ELSE 0 END), 0) AS low_stock,
               COALESCE(SUM(CASE WHEN v.stock <= 0 THEN 1 ELSE 0 END), 0) AS out_of_stock,
               COALESCE(SUM(v.stock * v.cost), 0) AS stock_cost_value
        FROM variants v JOIN products p ON p.id = v.product_id
        WHERE p.active = 1
        """
    ).fetchone()

    movements = [
        dict(row)
        for row in db.execute(
            """
            SELECT sm.id, sm.qty_change, sm.reason, sm.note, sm.created_at,
                   COALESCE(v.label, p.name) AS label, v.sku,
                   u.full_name AS user_name
            FROM stock_movements sm
            JOIN variants v ON v.id = sm.variant_id
            JOIN products p ON p.id = v.product_id
            LEFT JOIN users u ON u.id = sm.user_id
            ORDER BY sm.created_at DESC, sm.id DESC
            LIMIT 100
            """
        )
    ]
    return {
        "products": products,
        "summary": dict(summary),
        "movements": movements,
        "filter": stock_filter,
        "query": query,
        "truncated": len(products) == 500,
    }


def set_stock_count(db, variant_id, counted_stock, user_id, note=""):
    if isinstance(counted_stock, bool):
        raise InventoryError("Counted stock must be a whole number.")
    try:
        stock = int(counted_stock)
    except (TypeError, ValueError):
        raise InventoryError("Counted stock must be a whole number.") from None
    if str(stock) != str(counted_stock).strip() or stock < 0:
        raise InventoryError("Counted stock must be a non-negative whole number.")

    note = note.strip()
    if len(note) > 200:
        raise InventoryError("Note must be 200 characters or fewer.")

    try:
        with db:
            row = db.execute(
                """
                SELECT v.stock, p.active
                FROM variants v JOIN products p ON p.id = v.product_id
                WHERE v.id = ?
                """,
                (variant_id,),
            ).fetchone()
            if row is None or not row["active"]:
                raise InventoryError("Inventory item was not found.", 404)

            difference = stock - row["stock"]
            if difference == 0:
                raise InventoryError("Count matches current stock; no adjustment was needed.")

            updated = db.execute(
                "UPDATE variants SET stock = ? WHERE id = ? AND stock = ?",
                (stock, variant_id, row["stock"]),
            )
            if updated.rowcount != 1:
                raise InventoryError("Stock changed during this update. Refresh and try again.", 409)

            db.execute(
                """
                INSERT INTO stock_movements (variant_id, qty_change, reason, user_id, note)
                VALUES (?, ?, 'stocktake', ?, ?)
                """,
                (variant_id, difference, user_id, note),
            )
    except sqlite3.IntegrityError as exc:
        raise InventoryError("Stock adjustment could not be saved.", 409) from exc

    return {"previous_stock": row["stock"], "stock": stock, "difference": difference}
