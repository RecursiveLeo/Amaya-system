import sqlite3

import pytest

from db import init_db, seed_demo_data
from services.sales import SaleError, complete_sale

CHARGER, CABLE, EARPHONES = 1, 2, 3  # seeded variants: price 1200 / 500 / 350, stock 25 / 40 / 3


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    seed_demo_data(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def stock(db, variant_id):
    return db.execute("SELECT stock FROM variants WHERE id = ?", (variant_id,)).fetchone()[0]


def count(db, table):
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_cash_sale_reduces_stock_and_gives_change(db):
    result = complete_sale(
        db,
        items=[{"variant_id": CHARGER, "qty": 2}],
        payments=[{"method": "cash", "amount": 3000}],
    )
    assert result["total"] == 2400
    assert result["change"] == 600
    assert stock(db, CHARGER) == 23
    move = db.execute("SELECT qty_change, reason FROM stock_movements").fetchone()
    assert (move["qty_change"], move["reason"]) == (-2, "sale")
    paid = db.execute("SELECT SUM(amount) FROM payments").fetchone()[0]
    assert paid == 2400  # change is not counted as money received


def test_split_payment_cash_and_mpesa(db):
    result = complete_sale(
        db,
        items=[{"variant_id": CHARGER, "qty": 1}, {"variant_id": CABLE, "qty": 1}],
        payments=[
            {"method": "mpesa", "amount": 1000, "reference": "sk12abc34d"},
            {"method": "cash", "amount": 700},
        ],
    )
    assert result["total"] == 1700
    assert result["change"] == 0
    refs = [r[0] for r in db.execute("SELECT reference FROM payments WHERE method='mpesa'")]
    assert refs == ["SK12ABC34D"]


def test_not_enough_stock_saves_nothing(db):
    with pytest.raises(SaleError):
        complete_sale(
            db,
            items=[{"variant_id": CHARGER, "qty": 1}, {"variant_id": EARPHONES, "qty": 4}],
            payments=[{"method": "cash", "amount": 99999}],
        )
    assert stock(db, CHARGER) == 25
    assert stock(db, EARPHONES) == 3
    assert count(db, "sales") == 0
    assert count(db, "stock_movements") == 0


def test_underpayment_is_rejected_and_nothing_changes(db):
    with pytest.raises(SaleError, match="short by KSh 200"):
        complete_sale(
            db,
            items=[{"variant_id": CHARGER, "qty": 1}],
            payments=[{"method": "cash", "amount": 1000}],
        )
    assert stock(db, CHARGER) == 25
    assert count(db, "sales") == 0


def test_mpesa_does_not_require_a_transaction_code(db):
    result = complete_sale(
        db,
        items=[{"variant_id": CABLE, "qty": 1}],
        payments=[{"method": "mpesa", "amount": 500}],
    )
    assert result["total"] == 500
    payment = db.execute("SELECT method, amount, reference FROM payments").fetchone()
    assert tuple(payment) == ("mpesa", 500, None)


def test_mpesa_cannot_exceed_total(db):
    with pytest.raises(SaleError):
        complete_sale(
            db,
            items=[{"variant_id": CABLE, "qty": 1}],
            payments=[{"method": "mpesa", "amount": 800, "reference": "ABC123"}],
        )


def test_discount_reduces_total(db):
    result = complete_sale(
        db,
        items=[{"variant_id": CHARGER, "qty": 1}],
        payments=[{"method": "cash", "amount": 1100}],
        discount=100,
    )
    assert result["total"] == 1100
    assert result["change"] == 0


def test_price_and_cost_are_saved_with_the_sale(db):
    complete_sale(
        db,
        items=[{"variant_id": CHARGER, "qty": 1}],
        payments=[{"method": "cash", "amount": 1200}],
    )
    db.execute("UPDATE variants SET price = 2000, cost = 900 WHERE id = ?", (CHARGER,))
    row = db.execute("SELECT unit_price, unit_cost FROM sale_items").fetchone()
    assert (row["unit_price"], row["unit_cost"]) == (1200, 700)


def test_duplicate_lines_are_combined(db):
    complete_sale(
        db,
        items=[{"variant_id": CABLE, "qty": 1}, {"variant_id": CABLE, "qty": 2}],
        payments=[{"method": "cash", "amount": 1500}],
    )
    assert stock(db, CABLE) == 37
