from flask import Blueprint, jsonify, request

from db import get_db
from services.products import ProductError, list_products, save_product

products_bp = Blueprint("products", __name__)


@products_bp.route("/api/products", methods=["GET"])
def products_list():
    try:
        products = list_products(get_db(), request.args.get("q", ""))
    except ProductError as exc:
        return jsonify(error=str(exc)), exc.status
    return jsonify(products=products)


@products_bp.route("/api/products", methods=["POST"])
def products_create():
    try:
        product = save_product(get_db(), request.get_json(silent=True))
    except ProductError as exc:
        return jsonify(error=str(exc)), exc.status
    return jsonify(product=product), 201


@products_bp.route("/api/products/<int:variant_id>", methods=["PUT"])
def products_update(variant_id):
    try:
        product = save_product(get_db(), request.get_json(silent=True), variant_id)
    except ProductError as exc:
        return jsonify(error=str(exc)), exc.status
    return jsonify(product=product)
