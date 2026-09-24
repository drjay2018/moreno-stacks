"""
configuracion_views.py — Renderizado de vistas HTML para Configuración del sistema.
"""

from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

configuracion_views_bp = Blueprint("configuracion_views", __name__, url_prefix="/configuracion")


@configuracion_views_bp.route("/")
@requiere_login
def index():
    return render_template("configuracion/index.html")
