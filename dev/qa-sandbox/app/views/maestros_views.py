"""
maestros_views.py — Vistas HTML para navegación de Datos Maestros.
"""

from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

maestros_views_bp = Blueprint("maestros_views", __name__, url_prefix="/maestros")


@maestros_views_bp.route("/")
@maestros_views_bp.route("/catálogo")
@requiere_login
def index():
    return render_template("maestros/index.html")


@maestros_views_bp.route("/cliente-wizard")
@requiere_login
def cliente_wizard():
    return render_template("maestros/wizard_cliente.html")
