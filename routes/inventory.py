from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from db import get_db
from routes.auth import login_required
from services.inventory import InventoryError, list_inventory, set_stock_count

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/inventory")
@login_required
def inventory_page():
    try:
        inventory = list_inventory(
            get_db(),
            query=request.args.get("q", ""),
            stock_filter=request.args.get("stock", "all"),
        )
    except InventoryError as exc:
        flash(str(exc), "error")
        return redirect(url_for("inventory.inventory_page"))
    return render_template("inventory.html", inventory=inventory)


@inventory_bp.route("/api/inventory", methods=["GET"])
@login_required
def inventory_list():
    try:
        inventory = list_inventory(
            get_db(),
            query=request.args.get("q", ""),
            stock_filter=request.args.get("stock", "all"),
        )
    except InventoryError as exc:
        return jsonify(error=str(exc)), exc.status
    return jsonify(inventory)


@inventory_bp.route("/inventory/<int:variant_id>/stock", methods=["POST"])
@login_required
def inventory_stocktake(variant_id):
    stock_filter = request.form.get("stock", "all")
    query = request.form.get("q", "")
    try:
        result = set_stock_count(
            get_db(),
            variant_id,
            request.form.get("counted_stock", ""),
            session["user_id"],
            request.form.get("note", ""),
        )
    except InventoryError as exc:
        flash(str(exc), "error")
    else:
        if result["difference"] > 0:
            change = f"increased by {result['difference']}"
        else:
            change = f"decreased by {abs(result['difference'])}"
        flash(f"Stock count saved; {change}.", "success")

    return redirect(url_for("inventory.inventory_page", q=query, stock=stock_filter))
