"""
dashboard_views.py — Renderizado de plantillas HTML para el Dashboard.
"""

from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

dashboard_views_bp = Blueprint("dashboard_views", __name__)


@dashboard_views_bp.route("/")
@dashboard_views_bp.route("/dashboard")
@requiere_login
def dashboard():
    return render_template("dashboard.html")
