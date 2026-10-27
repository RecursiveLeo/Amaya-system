import hmac
import sqlite3
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db
from services.sales import SaleError, complete_sale

auth_bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        join_code = request.form.get("join_code", "").strip()
        configured_join_code = current_app.config.get("SHOP_JOIN_CODE", "")

        if not configured_join_code:
            flash("Shop registration is not configured. Set SHOP_JOIN_CODE first.", "error")
        elif not hmac.compare_digest(join_code.encode(), configured_join_code.encode()):
            flash("Wrong shop join code.", "error")
        elif not full_name or not username:
            flash("Enter your full name and a username.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            try:
                get_db().execute(
                    "INSERT INTO users (full_name, username, password_hash) VALUES (?, ?, ?)",
                    (full_name, username, generate_password_hash(password)),
                )
                get_db().commit()
            except sqlite3.IntegrityError:
                flash("That username is already taken.", "error")
            else:
                flash("Account created. Please log in.", "success")
                return redirect(url_for("auth.login"))

    return render_template(
        "auth_form.html",
        mode="register",
        join_code=current_app.config.get("SHOP_JOIN_CODE", ""),
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, full_name, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["full_name"]
            session["role"] = user["role"]
            return redirect(url_for("auth.new_sale"))
        flash("Invalid username or password.", "error")

    return render_template("auth_form.html", mode="login")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/sales/new", methods=["GET", "POST"])
@login_required
def new_sale():
    db = get_db()
    if request.method == "POST":
        product_ids = request.form.getlist("product_id")
        quantities = request.form.getlist("quantity")

        if len(product_ids) != len(quantities):
            flash("Sale items were invalid. Please try again.", "error")
            return redirect(url_for("auth.new_sale"))

        items = []
        total = 0
        for variant_id, raw_quantity in zip(product_ids, quantities):
            try:
                quantity = int(raw_quantity or 0)
            except ValueError:
                flash("Enter a whole-number quantity for each item.", "error")
                return redirect(url_for("auth.new_sale"))
            if quantity <= 0:
                continue

            variant = db.execute(
                """
                SELECT v.id, v.price
                FROM variants v
                JOIN products p ON p.id = v.product_id
                WHERE v.id = ? AND p.active = 1
                """,
                (variant_id,),
            ).fetchone()
            if variant is None:
                flash("Choose an available product.", "error")
                return redirect(url_for("auth.new_sale"))
            items.append({"variant_id": variant["id"], "qty": quantity})
            total += variant["price"] * quantity

        if not items:
            flash("Add at least one item.", "error")
            return redirect(url_for("auth.new_sale"))

        payment_method = request.form.get("payment_method", "cash")
        try:
            if payment_method == "cash":
                raw_amount = request.form.get("cash_amount", str(total))
                payments = [{"method": "cash", "amount": int(raw_amount)}]
            elif payment_method == "mpesa":
                raw_amount = request.form.get("mpesa_amount", str(total))
                payments = [{
                    "method": "mpesa",
                    "amount": int(raw_amount),
                }]
            elif payment_method == "split":
                mpesa_amount = int(request.form.get("mpesa_amount", "0"))
                if mpesa_amount <= 0 or mpesa_amount >= total:
                    raise ValueError
                payments = [
                    {"method": "cash", "amount": total - mpesa_amount},
                    {
                        "method": "mpesa",
                        "amount": mpesa_amount,
                    },
                ]
            else:
                flash("Choose cash, M-Pesa, or a split payment.", "error")
                return redirect(url_for("auth.new_sale"))
        except ValueError:
            flash("Enter valid whole-number amounts for the selected payment method.", "error")
            return redirect(url_for("auth.new_sale"))

        try:
            sale = complete_sale(
                db,
                items=items,
                payments=payments,
                user_id=session["user_id"],
            )
        except SaleError as exc:
            flash(str(exc), "error")
            return redirect(url_for("auth.new_sale"))

        flash(f"Sale #{sale['sale_id']} recorded. Total: KSh {sale['total']:,.2f}", "success")
        return redirect(url_for("auth.my_sales"))

    products = db.execute(
        """
        SELECT v.id, COALESCE(v.label, p.name) AS label, v.sku, v.price, v.stock
        FROM variants v
        JOIN products p ON p.id = v.product_id
        WHERE p.active = 1 AND v.stock > 0
        ORDER BY label
        """
    ).fetchall()
    return render_template("new_sale.html", products=products)


@auth_bp.route("/sales/mine")
@login_required
def my_sales():
    sales = get_db().execute(
        """
        SELECT s.id, s.total, s.status, s.created_at, COUNT(si.id) AS item_count
        FROM sales s
        LEFT JOIN sale_items si ON si.sale_id = s.id
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.created_at DESC, s.id DESC
        """,
        (session["user_id"],),
    ).fetchall()
    return render_template("my_sales.html", sales=sales)
