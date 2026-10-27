"""Sidebar navigation, plus 'coming soon' pages for screens we haven't built yet."""
from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)

# (label, url, built?)  -- set built=True as each screen is finished
NAV = [
    {"title": "1. Quick Sales", "items": [
        ("Quick sales", "/", True),
        ("New sale", "/sales/new", True),
        ("My sales", "/sales/mine", True),
        ("Sales", "/sales", False),
        ("Shifts", "/shifts", False),
        ("Returns", "/returns", False),
    ]},
    {"title": "2. Catalog and Stock", "items": [
        ("Products", "/products", True),
        ("Categories", "/categories", False),
        ("Quick-pick grid", "/quick-pick", False),
    ]},
    {"title": "3. Supply Chain", "items": [
        ("Supplies", "/suppliers", False),
        ("Receiving", "/receiving", False),
        ("Inventory", "/inventory", True),
    ]},
    {"title": "4. Business", "items": [
        ("Customers", "/customers", False),
        ("Expenses", "/expenses", False),
        ("Reports", "/reports", False),
        ("Settings", "/settings", True),
    ]},
]

DESCRIPTIONS = {
    "sales": "Full sales history with receipts, and a way to open any past sale.",
    "shifts": "Open and close cashier shifts, with an end-of-shift cash count and variance.",
    "returns": "Take back items and refund money, putting stock back correctly.",
    "categories": "Organise accessories into categories such as chargers, cables and earphones.",
    "quick-pick": "A grid of big buttons for your fastest-selling items, so cashiers can sell without scanning.",
    "suppliers": "Your supplier directory with contact details and purchase history.",
    "receiving": "Record purchase orders and receive stock from suppliers.",
    "customers": "Customer directory with contact details and loyalty points.",
    "expenses": "Record shop expenses so reports can show net profit.",
    "reports": "Daily, weekly, monthly and custom-range reports, exportable to PDF and CSV.",
}


def _make_view(slug):
    def view():
        return render_template(
            "coming_soon.html",
            title=slug.replace("-", " ").title(),
            description=DESCRIPTIONS[slug],
        )
    return view


@pages_bp.route("/products")
def products_page():
    return render_template("products.html")


for _slug in DESCRIPTIONS:
    pages_bp.add_url_rule(f"/{_slug}", endpoint=_slug.replace("-", "_"), view_func=_make_view(_slug))
