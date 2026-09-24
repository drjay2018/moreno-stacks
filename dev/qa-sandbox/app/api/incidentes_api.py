from flask import Blueprint, jsonify, request, session
from app.core.auth_middleware import requiere_rol, requiere_login
from sqlalchemy import text
from app.extensions import db
from sqlalchemy.exc import IntegrityError
from app.core.auditoria import registrar_auditoria
from app.core.utils import dt_args
import datetime

incidentes_api_bp = Blueprint("incidentes_api", __name__, url_prefix="/api/incidentes")

@incidentes_api_bp.route("/incidentes", methods=["GET"])
@requiere_login
def listar_incidentes():
    search_cols = ['i.tipo', 'i.descripcion', 'i.area_responsable']
    sort_cols = ['i.id', 'i.tipo', 'i.descripcion', 'i.area_responsable', 'i.severidad', 'i.fecha_reporte', 'i.fecha_cierre', None]
    is_dt, draw, where_dt, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    usuario = session.get("usuario", {})
    rol = usuario.get("rol", "").upper()
    
    where_clause = "1=1"
    # Privacidad: Incidentes nivel 3 y 4 solo visibles para DIRECTIVO (CEO, ADMIN)
    if rol not in ["ADMIN", "GERENTE GENERAL", "CEO", "GERENTE FINANCIERA"]:
        where_clause = "i.nivel < 3"
        
    if "WHERE" in where_dt:
        where_combined = where_dt.replace("WHERE ", f"WHERE ({where_clause}) AND ")
    else:
        where_combined = f"WHERE {where_clause}"

    if not order_clause:
        order_clause = "ORDER BY i.fecha_reporte DESC"

    total_records = db.session.execute(text(f"SELECT COUNT(id) FROM incidentes i WHERE {where_clause}")).scalar() or 0
    total_filtered = db.session.execute(text(f"SELECT COUNT(i.id) FROM incidentes i {where_combined}"), params).scalar() or 0
    
    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""
            SELECT i.id, i.tipo, i.descripcion, i.fecha_reporte, i.severidad, i.fecha_cierre,
                   i.nivel, i.area_responsable, i.enlace_f05, i.fecha_resolucion, i.comentario_resolucion
            FROM incidentes i
            {where_combined}
            {order_clause} LIMIT :limit OFFSET :offset
        """),
        params
    ).mappings().all()

    items_list = []
    for r in rows:
        d = dict(r)
        
        # Calcular SLA de resolución (Abiertos con más de 7 días)
        if not d.get('fecha_cierre'):
            fecha_rep_str = d.get('fecha_reporte', '')
            try:
                fecha_rep = datetime.datetime.strptime(fecha_rep_str.split()[0], '%Y-%m-%d').date()
                dias_abierto = (datetime.date.today() - fecha_rep).days
            except (ValueError, AttributeError):
                dias_abierto = 0
            d['estado_sla'] = 'CRÍTICO' if dias_abierto > 7 else 'EN PROCESO'
        else:
            d['estado_sla'] = 'RESUELTO'

        items_list.append(d)
        
    if 'draw' in request.args:
        return jsonify({"draw": int(request.args.get('draw', 1)), "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items_list})

    return jsonify({"success": True, "total": total_filtered, "items": items_list, "incidentes": items_list})

@incidentes_api_bp.route("", methods=["POST"])
@requiere_rol("Admin")
def crear_incidente():
    data = request.get_json() or {}
    tipo = data.get("tipo", "").strip()
    descripcion = data.get("descripcion", "").strip()
    severidad = data.get("severidad", "media").strip()
    nivel = int(data.get("nivel", 1))
    area_responsable = data.get("area_responsable", "").strip()
    enlace_f05 = data.get("enlace_f05", "").strip()
    
    if not tipo or not descripcion:
        return jsonify({"success": False, "error": "Tipo y descripción son requeridos."}), 400
        
    if nivel in [3, 4] and not enlace_f05:
        return jsonify({"success": False, "error": "Incidentes Nivel 3/4 requieren un enlace válido (F-05)."}), 400

    try:
        db.session.execute(
            text("""
                INSERT INTO incidentes (tipo, descripcion, fecha_reporte, severidad, nivel, area_responsable, enlace_f05)
                VALUES (:tipo, :desc, CURRENT_DATE, :sev, :niv, :area, :enl)
            """),
            {"tipo": tipo, "desc": descripcion, "sev": severidad, "niv": nivel, "area": area_responsable, "enl": enlace_f05}
        )
        inc_id = db.session.execute(text("SELECT last_insert_rowid()")).scalar()
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'admin', 'crear_incidente', 'INCIDENTES', f'Incidente Nivel {nivel} reportado')
    return jsonify({"success": True, "message": "Incidente registrado.", "id": inc_id})

@incidentes_api_bp.route("/<int:inc_id>", methods=["PUT"])
@requiere_rol("Admin")
def editar_incidente(inc_id):
    data = request.get_json() or {}
    tipo = data.get("tipo", "").strip()
    descripcion = data.get("descripcion", "").strip()
    severidad = data.get("severidad", "media").strip()
    nivel = int(data.get("nivel", 1))
    area_responsable = data.get("area_responsable", "").strip()
    enlace_f05 = data.get("enlace_f05", "").strip()
    
    if not tipo or not descripcion:
        return jsonify({"success": False, "error": "Tipo y descripción son requeridos."}), 400
        
    if nivel in [3, 4] and not enlace_f05:
        return jsonify({"success": False, "error": "Incidentes Nivel 3/4 requieren un enlace válido (F-05)."}), 400

    try:
        existe = db.session.execute(
            text("SELECT 1 FROM incidentes WHERE id = :id"), {"id": inc_id}
        ).first()
        if not existe:
            return jsonify({"success": False, "error": f"Incidente {inc_id} no encontrado."}), 404

        db.session.execute(
            text("""
                UPDATE incidentes 
                SET tipo=:tipo, descripcion=:desc, severidad=:sev, nivel=:niv, area_responsable=:area, enlace_f05=:enl
                WHERE id=:id
            """),
            {"tipo": tipo, "desc": descripcion, "sev": severidad, "niv": nivel, "area": area_responsable, "enl": enlace_f05, "id": inc_id}
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'admin', 'editar_incidente', 'INCIDENTES', f'Incidente {inc_id} editado')
    return jsonify({"success": True, "message": "Incidente actualizado."})

@incidentes_api_bp.route("/<int:inc_id>/cerrar", methods=["POST"])
@requiere_rol("Admin")
def cerrar_incidente(inc_id):
    data = request.get_json() or {}
    fecha_resolucion = data.get("fecha_resolucion")
    comentario_resolucion = data.get("comentario_resolucion")

    if not fecha_resolucion or not comentario_resolucion:
        return jsonify({"success": False, "error": "Fecha y comentario de resolución son obligatorios."}), 400

    try:
        existe = db.session.execute(
            text("SELECT 1 FROM incidentes WHERE id = :id"), {"id": inc_id}
        ).first()
        if not existe:
            return jsonify({"success": False, "error": f"Incidente {inc_id} no encontrado."}), 404

        db.session.execute(
            text("UPDATE incidentes SET fecha_cierre = :fecha, fecha_resolucion = :fecha, comentario_resolucion = :coment WHERE id = :id"), 
            {"id": inc_id, "fecha": fecha_resolucion, "coment": comentario_resolucion}
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'admin', 'cerrar_incidente', 'INCIDENTES', f'Incidente {inc_id} cerrado')
    return jsonify({"success": True, "message": "Incidente cerrado correctamente."})
