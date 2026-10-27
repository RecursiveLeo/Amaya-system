from flask import Blueprint, jsonify, render_template, session

from db import get_db
from routes.auth import login_required
from services.reports import dashboard_summary

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@reports_bp.route("/api/dashboard")
@login_required
def dashboard_data():
    return jsonify(dashboard_summary(get_db(), user_id=session["user_id"]))
