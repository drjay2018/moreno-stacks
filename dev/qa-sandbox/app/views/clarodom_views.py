"""
clarodom_views.py — Renderizado de vistas HTML para el modulo API-ClaroDom.
"""

from flask import Blueprint, render_template

clarodom_views_bp = Blueprint("clarodom_views", __name__, url_prefix="/clarodom")


@clarodom_views_bp.route("/")
def index():
    return render_template("clarodom/index.html")