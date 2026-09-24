"""
alterestate_views.py — Renderizado de vistas HTML para el modulo API-AlterState.
"""

from flask import Blueprint, render_template

alterestate_views_bp = Blueprint("alterestate_views", __name__, url_prefix="/api-alterestate")


@alterestate_views_bp.route("/")
def index():
    return render_template("api_alterestate/index.html")
