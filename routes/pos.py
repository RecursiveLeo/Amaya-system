from flask import Blueprint, jsonify, render_template, request, session

from db import get_db
from services.sales import SaleError, complete_sale

pos_bp = Blueprint("pos", __name__)


@pos_bp.route("/")
def pos_screen():
    return render_template("pos.html")


@pos_bp.route("/pos/scan", methods=["POST"])
def scan():
    """Look up a barcode (or SKU) and return the item for the cart."""
    code = (request.get_json(silent=True) or {}).get("barcode", "").strip()
    if not code:
        return jsonify(error="No barcode received"), 400

    row = get_db().execute(
        """
        SELECT v.id, v.label, v.price, v.stock, b.name AS brand
        FROM variants v
        JOIN products p ON p.id = v.product_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE (v.barcode = ? OR v.sku = ?) AND p.active = 1
        """,
        (code, code),
    ).fetchone()

    if row is None:
        return jsonify(error=f"Item not found: {code}"), 404
    if row["stock"] <= 0:
        return jsonify(error=f"Out of stock: {row['label']}"), 409

    return jsonify(
        id=row["id"], label=row["label"], brand=row["brand"],
        price=row["price"], stock=row["stock"],
    )


@pos_bp.route("/pos/checkout", methods=["POST"])
def checkout():
    """Save the sale: items, payments, and stock changes in one go."""
    data = request.get_json(silent=True) or {}
    try:
        result = complete_sale(
            get_db(),
            items=data.get("items"),
            payments=data.get("payments"),
            discount=data.get("discount", 0),
            user_id=session.get("user_id"),
        )
    except SaleError as e:
        return jsonify(error=str(e)), 400
    return jsonify(result), 201
