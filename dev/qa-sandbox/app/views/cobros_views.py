"""
cobros_views.py — Renderizado de vistas HTML para Cobros Bancarios.
"""

from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

cobros_views_bp = Blueprint("cobros_views", __name__, url_prefix="/cobros")


@cobros_views_bp.route("/")
@requiere_login
def index():
    return render_template("cobros/index.html")
