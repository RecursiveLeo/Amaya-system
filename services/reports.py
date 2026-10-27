"""Numbers for the dashboard. Money is whole shillings, as everywhere else."""

# Sales are stored in UTC; convert to the computer's local time before comparing days.
_TODAY = "date(s.created_at, 'localtime') = date('now', 'localtime')"


def dashboard_summary(db, user_id=None):
    user_filter = " AND s.user_id = ?" if user_id is not None else ""
    user_params = (user_id,) if user_id is not None else ()
    count, revenue, discounts = db.execute(
        f"SELECT COUNT(*), COALESCE(SUM(s.total), 0), COALESCE(SUM(s.discount), 0) "
        f"FROM sales s WHERE s.status = 'completed' AND {_TODAY}{user_filter}",
        user_params,
    ).fetchone()

    cost, items_sold = db.execute(
        f"SELECT COALESCE(SUM(si.unit_cost * si.qty), 0), COALESCE(SUM(si.qty), 0) "
        f"FROM sale_items si JOIN sales s ON s.id = si.sale_id "
        f"WHERE s.status = 'completed' AND {_TODAY}{user_filter}",
        user_params,
    ).fetchone()

    by_method = {
        r["method"]: r["amount"]
        for r in db.execute(
            f"SELECT p.method, SUM(p.amount) AS amount FROM payments p "
            f"JOIN sales s ON s.id = p.sale_id WHERE s.status = 'completed' AND {_TODAY}{user_filter} "
            f"GROUP BY p.method",
            user_params,
        )
    }

    top_sellers = [dict(r) for r in db.execute(
        f"SELECT v.label, SUM(si.qty) AS qty, SUM(si.unit_price * si.qty) AS amount "
        f"FROM sale_items si JOIN sales s ON s.id = si.sale_id "
        f"JOIN variants v ON v.id = si.variant_id "
        f"WHERE s.status = 'completed' AND {_TODAY}{user_filter} "
        f"GROUP BY v.id ORDER BY qty DESC, amount DESC LIMIT 5",
        user_params,
    )]

    stock_alerts = [dict(r) for r in db.execute(
        "SELECT v.label, v.stock, v.reorder_level, b.name AS brand "
        "FROM variants v JOIN products p ON p.id = v.product_id "
        "LEFT JOIN brands b ON b.id = p.brand_id "
        "WHERE p.active = 1 AND v.stock <= v.reorder_level "
        "ORDER BY v.stock ASC, v.label LIMIT 25"
    )]

    active = "FROM variants v JOIN products p ON p.id = v.product_id WHERE p.active = 1"
    low_stock = db.execute(f"SELECT COUNT(*) {active} AND v.stock > 0 AND v.stock <= v.reorder_level").fetchone()[0]
    out_of_stock = db.execute(f"SELECT COUNT(*) {active} AND v.stock <= 0").fetchone()[0]
    all_count, all_revenue = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(total), 0) FROM sales s "
        f"WHERE s.status = 'completed'{user_filter}",
        user_params,
    ).fetchone()

    return {
        "all_time_sales": all_revenue,
        "all_time_orders": all_count,
        "low_stock": low_stock,
        "sales_count": count,
        "revenue": revenue,
        "discounts": discounts,
        "cost": cost,
        "gross_profit": revenue - cost,
        "items_sold": items_sold,
        "by_method": by_method,
        "top_sellers": top_sellers,
        "stock_alerts": stock_alerts,
        "out_of_stock": out_of_stock,
        "last_7_days": _last_7_days(db, user_id),
        "personal_sales": user_id is not None,
    }


def _last_7_days(db, user_id=None):
    user_filter = " AND s.user_id = ?" if user_id is not None else ""
    user_params = (user_id,) if user_id is not None else ()
    totals = {
        r["day"]: r["total"]
        for r in db.execute(
            "SELECT date(created_at, 'localtime') AS day, SUM(total) AS total FROM sales "
            f"AS s WHERE s.status = 'completed' "
            f"AND date(s.created_at, 'localtime') >= date('now', 'localtime', '-6 days'){user_filter} "
            "GROUP BY day",
            user_params,
        )
    }
    days = []
    for back in range(6, -1, -1):
        day = db.execute("SELECT date('now', 'localtime', ?)", (f"-{back} days",)).fetchone()[0]
        days.append({"day": day, "total": totals.get(day, 0)})
    return days
