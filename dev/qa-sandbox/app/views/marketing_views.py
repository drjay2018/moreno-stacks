"""
marketing_views.py — Renderizado de vistas HTML para Campañas de Marketing.
"""

from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

marketing_views_bp = Blueprint("marketing_views", __name__, url_prefix="/marketing")


@marketing_views_bp.route("/")
@requiere_login
def index():
    return render_template("marketing/index.html")
