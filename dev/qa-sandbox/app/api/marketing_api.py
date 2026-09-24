"""
marketing_api.py — Endpoints API para análisis y alta individual de Campañas de Marketing.
"""

from flask import Blueprint, jsonify, request, session, current_app
from sqlalchemy import text
from app.extensions import db
from sqlalchemy.exc import IntegrityError
from app.core.utils import dt_args
from app.core.auth_middleware import requiere_rol

marketing_api_bp = Blueprint("marketing_api", __name__, url_prefix="/api/marketing")


@marketing_api_bp.route("/campanas", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente General")
def listar_campanas():
    search_cols = ['c.nombre', 'c.canal', 'p.nombre']
    sort_cols = ['c.id', 'c.nombre', 'c.canal', 'p.nombre', 'c.monto_invertido', 'c.fecha_inicio', 'c.activo']
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)

    if not order_clause:
        order_clause = "ORDER BY c.id DESC"

    total_records = db.session.execute(text("SELECT COUNT(id) FROM campanas")).scalar() or 0
    total_filtered = db.session.execute(text(f"SELECT COUNT(c.id) FROM campanas c LEFT JOIN proyectos p ON c.proyecto_id = p.id {where_clause}"), params).scalar() or 0
    
    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""
            SELECT c.id, c.nombre, c.canal, p.nombre as proyecto, c.monto_invertido, c.fecha_inicio, c.fecha_fin, c.activo,
                   c.impresiones, c.clics, c.alcance, c.leads_generados
            FROM campanas c
            LEFT JOIN proyectos p ON c.proyecto_id = p.id
            {where_clause}
            {order_clause} LIMIT :limit OFFSET :offset
        """),
        params
    ).mappings().all()

    items_list = []
    for r in rows:
        d = dict(r)
        monto = float(d.get("monto_invertido") or 0.0)
        leads = int(d.get("leads_generados") or 0)
        d["cpl"] = round(monto / leads, 2) if leads > 0 else 0.0
        impresiones = int(d.get("impresiones") or 0)
        clics = int(d.get("clics") or 0)
        d["ctr"] = round((clics / impresiones) * 100, 2) if impresiones > 0 else 0.0
        items_list.append(d)
    
    if is_dt:
        return jsonify({"draw": draw, "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items_list})
        
    return jsonify({"success": True, "items": items_list, "campanas": items_list})


@marketing_api_bp.route("/campanas", methods=["POST"])
@requiere_rol("Admin")
def crear_campana():
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()
    canal = data.get("canal", "Instagram Ads")
    proyecto_id = data.get("proyecto_id", 1)
    monto_invertido = float(data.get("monto_invertido", 0.0))
    impresiones = int(data.get("impresiones", 0))
    clics = int(data.get("clics", 0))
    leads_generados = int(data.get("leads_generados", 0))
    alcance = int(data.get("alcance", 0))
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")

    if not nombre or monto_invertido <= 0:
        return jsonify({"success": False, "error": "El nombre de la campaña y la inversión deben ser válidos."}), 400

    try:
        db.session.execute(
            text("""
                INSERT INTO campanas (nombre, canal, proyecto_id, fecha_inicio, fecha_fin, monto_invertido, activo, impresiones, clics, alcance, leads_generados)
                VALUES (:nom, :can, :pid, COALESCE(:finicio, CURRENT_DATE), :ffin, :monto, 1, :imp, :cli, :alc, :leads)
            """),
            {"nom": nombre, "can": canal, "pid": proyecto_id, "finicio": fecha_inicio, "ffin": fecha_fin, "monto": monto_invertido, "imp": impresiones, "cli": clics, "alc": alcance, "leads": leads_generados}
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    return jsonify({"success": True, "message": f"Campaña '{nombre}' (${monto_invertido:,.2f} USD) creada exitosamente."})

@marketing_api_bp.route("/campanas/<int:campana_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_campana(campana_id):
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()
    canal = data.get("canal")
    monto_invertido = data.get("monto_invertido")
    impresiones = data.get("impresiones")
    clics = data.get("clics")
    leads_generados = data.get("leads_generados")
    alcance = data.get("alcance")
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")

    if not nombre:
        return jsonify({"success": False, "error": "El nombre de la campaña es requerido."}), 400

    params = {"nombre": nombre, "id": campana_id}
    ALLOWED_COLUMNS = {"nombre", "canal", "monto_invertido", "impresiones", "clics", "leads_generados", "alcance", "fecha_inicio", "fecha_fin"}
    updates = ["nombre = :nombre"]
    
    if canal is not None:
        params["canal"] = canal
        updates.append("canal = :canal")
    if monto_invertido is not None:
        params["monto_invertido"] = float(monto_invertido)
        updates.append("monto_invertido = :monto_invertido")
    if impresiones is not None:
        params["impresiones"] = int(impresiones)
        updates.append("impresiones = :impresiones")
    if clics is not None:
        params["clics"] = int(clics)
        updates.append("clics = :clics")
    if leads_generados is not None:
        params["leads_generados"] = int(leads_generados)
        updates.append("leads_generados = :leads_generados")
    if alcance is not None:
        params["alcance"] = int(alcance)
        updates.append("alcance = :alcance")
    if fecha_inicio is not None:
        params["fecha_inicio"] = fecha_inicio if fecha_inicio else None
        updates.append("fecha_inicio = :fecha_inicio")
    if fecha_fin is not None:
        params["fecha_fin"] = fecha_fin if fecha_fin else None
        updates.append("fecha_fin = :fecha_fin")

    set_clause = ", ".join(updates)

    try:
        existe = db.session.execute(
            text("SELECT 1 FROM campanas WHERE id = :id"), {"id": campana_id}
        ).first()
        if not existe:
            return jsonify({"success": False, "error": f"Campaña {campana_id} no encontrada."}), 404

        db.session.execute(
            text(f"UPDATE campanas SET {set_clause} WHERE id = :id"),
            params
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    return jsonify({"success": True, "message": "Campaña actualizada correctamente."})

@marketing_api_bp.route("/campanas/<int:campana_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_campana(campana_id):
    try:
        existe = db.session.execute(
            text("SELECT 1 FROM campanas WHERE id = :id"), {"id": campana_id}
        ).first()
        if not existe:
            return jsonify({"success": False, "error": f"Campaña {campana_id} no encontrada."}), 404
        db.session.execute(text("UPDATE campanas SET activo = 0 WHERE id = :id"), {"id": campana_id})
        db.session.commit()
        return jsonify({"success": True, "message": "Campaña desactivada correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en marketing_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

