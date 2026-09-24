from flask import Blueprint, render_template
from app.core.auth_middleware import requiere_login

compras_views_bp = Blueprint("compras_views", __name__, url_prefix="/compras")

@compras_views_bp.route("/")
@requiere_login
def index():
    return render_template("compras/index.html")

@compras_views_bp.route("/facturas")
@requiere_login
def facturas():
    from flask import request
    compra_id = request.args.get("compra_id")
    return render_template("compras/facturas.html", compra_id=compra_id)
