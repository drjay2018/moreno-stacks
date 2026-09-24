from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

incidentes_views_bp = Blueprint("incidentes_views", __name__, url_prefix="/incidentes")

@incidentes_views_bp.route("/")
@requiere_login
def index():
    return render_template("incidentes/index.html")
