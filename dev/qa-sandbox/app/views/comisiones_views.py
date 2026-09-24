from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

comisiones_views_bp = Blueprint("comisiones_views", __name__, url_prefix="/comisiones")

@comisiones_views_bp.route("/")
@requiere_login
def index():
    return render_template("comisiones/index.html")
