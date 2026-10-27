import sqlite3

import pytest

from db import init_db, seed_demo_data
from services.reports import dashboard_summary
from services.sales import complete_sale


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    seed_demo_data(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_empty_dashboard_is_all_zeros(db):
    d = dashboard_summary(db)
    assert (d["revenue"], d["gross_profit"], d["sales_count"]) == (0, 0, 0)
    assert len(d["last_7_days"]) == 7


def test_profit_is_revenue_minus_cost_after_discount(db):
    # 2 chargers: price 1200, cost 700 each; discount 100
    complete_sale(db, [{"variant_id": 1, "qty": 2}],
                  [{"method": "cash", "amount": 2300}], discount=100)
    d = dashboard_summary(db)
    assert d["revenue"] == 2300
    assert d["cost"] == 1400
    assert d["gross_profit"] == 900
    assert d["items_sold"] == 2
    assert d["by_method"] == {"cash": 2300}
    assert d["top_sellers"][0]["qty"] == 2
    assert d["last_7_days"][-1]["total"] == 2300


def test_old_sales_are_not_counted_today(db):
    complete_sale(db, [{"variant_id": 2, "qty": 1}], [{"method": "cash", "amount": 500}])
    db.execute("UPDATE sales SET created_at = datetime('now', '-3 days')")
    db.commit()
    d = dashboard_summary(db)
    assert d["revenue"] == 0
    assert sum(x["total"] for x in d["last_7_days"]) == 500


def test_stock_alerts_flag_low_and_out_of_stock(db):
    # earphones: stock 3, reorder level 5 -> low. Sell all 3 -> out.
    assert [a["label"] for a in dashboard_summary(db)["stock_alerts"]] == ["Generic Wired Earphones"]
    complete_sale(db, [{"variant_id": 3, "qty": 3}], [{"method": "cash", "amount": 1050}])
    d = dashboard_summary(db)
    assert d["out_of_stock"] == 1
    assert d["stock_alerts"][0]["stock"] == 0


def test_low_and_out_of_stock_counts(db):
    d = dashboard_summary(db)
    assert (d["low_stock"], d["out_of_stock"]) == (1, 0)  # earphones: 3 left, reorder at 5
    complete_sale(db, [{"variant_id": 3, "qty": 3}], [{"method": "cash", "amount": 1050}])
    d = dashboard_summary(db)
    assert (d["low_stock"], d["out_of_stock"]) == (0, 1)
    assert d["all_time_orders"] == 1 and d["all_time_sales"] == 1050


def test_dashboard_sales_metrics_are_scoped_to_cashier(db):
    db.execute(
        "INSERT INTO users (full_name, username, password_hash) VALUES "
        "('Cashier One', 'cashier-one', 'hash'), ('Cashier Two', 'cashier-two', 'hash')"
    )
    complete_sale(
        db,
        [{"variant_id": 1, "qty": 1}],
        [{"method": "cash", "amount": 1200}],
        user_id=1,
    )
    complete_sale(
        db,
        [{"variant_id": 2, "qty": 1}],
        [{"method": "mpesa", "amount": 500, "reference": "ABC123"}],
        user_id=2,
    )

    first_cashier = dashboard_summary(db, user_id=1)
    second_cashier = dashboard_summary(db, user_id=2)

    assert first_cashier["personal_sales"] is True
    assert first_cashier["sales_count"] == 1
    assert first_cashier["revenue"] == 1200
    assert first_cashier["all_time_orders"] == 1
    assert first_cashier["all_time_sales"] == 1200
    assert first_cashier["by_method"] == {"cash": 1200}
    assert first_cashier["top_sellers"][0]["label"] == "Amaya 20W Charger / White"
    assert first_cashier["last_7_days"][-1]["total"] == 1200

    assert second_cashier["sales_count"] == 1
    assert second_cashier["revenue"] == 500
    assert second_cashier["all_time_sales"] == 500
    assert second_cashier["by_method"] == {"mpesa": 500}
    assert second_cashier["top_sellers"][0]["label"] == "Amaya USB-C Cable 1m"
    assert second_cashier["last_7_days"][-1]["total"] == 500

    shop_summary = dashboard_summary(db)
    assert shop_summary["personal_sales"] is False
    assert shop_summary["all_time_orders"] == 2
    assert shop_summary["all_time_sales"] == 1700
