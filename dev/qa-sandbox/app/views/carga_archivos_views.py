"""
carga_archivos_views.py — Renderizado de vistas HTML para Carga Masiva de Archivos CSV.
"""

from flask import Blueprint, render_template

carga_archivos_views_bp = Blueprint("carga_archivos_views", __name__, url_prefix="/carga-archivos")


@carga_archivos_views_bp.route("/")
def index():
    return render_template("carga_archivos/index.html")
