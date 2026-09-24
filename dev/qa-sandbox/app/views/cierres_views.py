"""
cierres_views.py — Renderizado de vistas HTML para Cierres / Transacciones.
"""

from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

cierres_views_bp = Blueprint("cierres_views", __name__, url_prefix="/cierres")


@cierres_views_bp.route("/")
@requiere_login
def index():
    return render_template("cierres/index.html")
