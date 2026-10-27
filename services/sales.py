"""All checkout rules live here, so they can be tested without a browser."""

PAYMENT_METHODS = {"cash", "card", "mpesa"}


class SaleError(Exception):
    """A problem the cashier should be told about (shown as a message)."""


def _to_int(value, what):
    if isinstance(value, bool) or not isinstance(value, int):
        raise SaleError(f"{what} must be a whole number")
    return value


def _merge_items(items):
    """Combine duplicate lines: [{variant_id, qty}, ...] -> {variant_id: qty}."""
    if not items:
        raise SaleError("The cart is empty")
    merged = {}
    for it in items:
        variant_id = _to_int(it.get("variant_id"), "Item")
        qty = _to_int(it.get("qty"), "Quantity")
        if qty <= 0:
            raise SaleError("Quantity must be at least 1")
        merged[variant_id] = merged.get(variant_id, 0) + qty
    return merged


def _clean_payments(payments):
    cleaned = []
    for p in payments or []:
        method = p.get("method")
        if method not in PAYMENT_METHODS:
            raise SaleError(f"Unknown payment method: {method}")
        amount = _to_int(p.get("amount"), "Payment amount")
        if amount <= 0:
            raise SaleError("Payment amount must be more than zero")
        reference = (p.get("reference") or "").strip().upper() or None
        cleaned.append({"method": method, "amount": amount, "reference": reference})
    return cleaned


def _apply_payments(payments, total):
    """Work out what each payment covers, and the change owed in cash."""
    non_cash = [p for p in payments if p["method"] != "cash"]
    cash_paid = sum(p["amount"] for p in payments if p["method"] == "cash")

    non_cash_total = sum(p["amount"] for p in non_cash)
    if non_cash_total > total:
        raise SaleError("Card/M-Pesa payments are more than the total")

    cash_due = total - non_cash_total
    if cash_paid < cash_due:
        raise SaleError(f"Payment is short by KSh {cash_due - cash_paid}")

    applied = list(non_cash)
    if cash_due > 0:
        applied.append({"method": "cash", "amount": cash_due, "reference": None})
    return applied, cash_paid - cash_due


def complete_sale(
    db, items, payments, discount=0, customer_id=None, shift_id=None, user_id=None
):
    """Record a sale. Everything succeeds together or nothing is saved."""
    wanted = _merge_items(items)
    payments = _clean_payments(payments)
    discount = _to_int(discount, "Discount")
    if discount < 0:
        raise SaleError("Discount cannot be negative")

    with db:  # one transaction: commits on success, rolls back on any error
        lines, subtotal = [], 0
        for variant_id, qty in wanted.items():
            v = db.execute(
                "SELECT id, label, price, cost, stock FROM variants WHERE id = ?",
                (variant_id,),
            ).fetchone()
            if v is None:
                raise SaleError("Item not found")
            if v["stock"] < qty:
                raise SaleError(f"Not enough stock for {v['label']}: {v['stock']} left")
            lines.append((v, qty))
            subtotal += v["price"] * qty  # price comes from the DB, never the browser

        if discount > subtotal:
            raise SaleError("Discount is more than the subtotal")
        total = subtotal - discount

        applied, change = _apply_payments(payments, total)

        sale_id = db.execute(
            "INSERT INTO sales "
            "(shift_id, customer_id, user_id, subtotal, discount, total, change_given) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (shift_id, customer_id, user_id, subtotal, discount, total, change),
        ).lastrowid

        for v, qty in lines:
            # The "stock >= ?" guard means stock can never go negative
            cur = db.execute(
                "UPDATE variants SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (qty, v["id"], qty),
            )
            if cur.rowcount != 1:
                raise SaleError(f"Not enough stock for {v['label']}")
            db.execute(
                "INSERT INTO sale_items (sale_id, variant_id, qty, unit_price, unit_cost) "
                "VALUES (?, ?, ?, ?, ?)",
                (sale_id, v["id"], qty, v["price"], v["cost"]),
            )
            db.execute(
                "INSERT INTO stock_movements "
                "(variant_id, qty_change, reason, user_id, ref_type, ref_id) "
                "VALUES (?, ?, 'sale', ?, 'sale', ?)",
                (v["id"], -qty, user_id, sale_id),
            )

        for p in applied:
            db.execute(
                "INSERT INTO payments (sale_id, method, amount, reference) VALUES (?, ?, ?, ?)",
                (sale_id, p["method"], p["amount"], p["reference"]),
            )

    return {"sale_id": sale_id, "subtotal": subtotal, "discount": discount,
            "total": total, "change": change}
