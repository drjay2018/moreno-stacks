"""
exportaciones_views.py — Renderizado de vistas HTML para Reportería.
"""

from flask import Blueprint, render_template

exportaciones_views_bp = Blueprint("exportaciones_views", __name__, url_prefix="/exportaciones")


@exportaciones_views_bp.route("/")
def index():
    return render_template("exportaciones/index.html")
