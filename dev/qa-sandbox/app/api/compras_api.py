from flask import Blueprint, jsonify, request, session, current_app
from app.core.auth_middleware import requiere_rol
from sqlalchemy import text
from app.extensions import db
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from app.core.auditoria import registrar_auditoria
from app.core.utils import dt_args
import datetime

compras_api_bp = Blueprint("compras_api", __name__, url_prefix="/api/compras")

@compras_api_bp.route("/compras", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_compras():
    search_cols = ['c.concepto', 'c.estado', 'c.enlace_dropbox']
    sort_cols = ['c.id', 'c.concepto', 'c.enlace_dropbox', 'c.monto_total', 'total_pagado', 'balance_pendiente', 'c.estado', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    if "WHERE" in where_clause:
        where_clause = where_clause.replace("WHERE ", "WHERE c.estado != 'eliminado' AND ")
    else:
        where_clause = "WHERE c.estado != 'eliminado'"
        
    if not order_clause:
        order_clause = "ORDER BY c.id DESC"
        
    total_records = db.session.execute(text("SELECT COUNT(id) FROM compras")).scalar() or 0
    total_filtered = db.session.execute(text(f"SELECT COUNT(c.id) FROM compras c {where_clause}"), params).scalar() or 0
    
    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""
            SELECT c.id, c.concepto, COALESCE(pv.razon_social, 'N/A') as proveedor, c.enlace_dropbox as enlace_f03, c.monto_total, c.estado, 
                   CASE WHEN c.aprobado_ceo = 0 AND c.monto_total > 50000 THEN 1 ELSE 0 END as requiere_aprobacion_ceo, 
                   c.fecha_solicitud as fecha_creacion, NULL as fecha_vencimiento,
                   COALESCE(SUM(p.monto_pagado), 0) as total_pagado
            FROM compras c
            LEFT JOIN compras_pagos p ON c.id = p.compra_id
            LEFT JOIN proveedores pv ON c.proveedor_id = pv.id
            {where_clause}
            GROUP BY c.id
            {order_clause} LIMIT :limit OFFSET :offset
        """),
        params
    ).mappings().all()

    items_list = []
    for r in rows:
        d = dict(r)
        d['balance_pendiente'] = float((d['monto_total'] or 0) - (d['total_pagado'] or 0))
        
        # Calcular SLA 2 días
        fecha_creacion_str = d.get('fecha_creacion')
        try:
            creado = datetime.datetime.strptime(fecha_creacion_str.split()[0], '%Y-%m-%d').date() if fecha_creacion_str else datetime.date.today()
        except (ValueError, AttributeError):
            creado = datetime.date.today()
        hoy = datetime.date.today()
        dias_abierto = (hoy - creado).days
        
        if d['estado'] == 'pagado':
            d['estado_sla'] = 'OK'
        elif dias_abierto > 2:
            d['estado_sla'] = 'INCUMPLIDO'
        else:
            d['estado_sla'] = 'EN TIEMPO'

        items_list.append(d)

    if 'draw' in request.args:
        return jsonify({"draw": int(request.args.get('draw', 1)), "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items_list})

    return jsonify({"success": True, "total": total_filtered, "items": items_list, "compras": items_list})

@compras_api_bp.route("", methods=["POST"])
@requiere_rol("Admin")
def crear_compra():
    data = request.get_json() or {}
    concepto = data.get("concepto", "").strip()
    proveedor_id = data.get("proveedor_id")
    enlace = data.get("enlace_f03", "").strip()
    monto_str = data.get("monto_total", 0.0)
    fecha_v = data.get("fecha_vencimiento")

    if not concepto or not proveedor_id or not enlace or "dropbox.com" not in enlace.lower():
        return jsonify({"success": False, "error": "Concepto, proveedor y enlace válido de Dropbox (F-03) son requeridos."}), 400

    try:
        monto_total = Decimal(str(monto_str)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return jsonify({"success": False, "error": "El monto tiene un formato inválido."}), 400

    if monto_total <= Decimal('0.00'):
        return jsonify({"success": False, "error": "El monto debe ser positivo."}), 400

    req_aprobacion = 1 if monto_total > Decimal('50000.00') else 0
    estado = 'pendiente_aprobacion' if req_aprobacion else 'aprobado'

    try:
        db.session.execute(
            text("""
                INSERT INTO compras (concepto, proveedor_id, enlace_dropbox, monto_total, aprobado_ceo, estado, fecha_solicitud)
                VALUES (:con, :prov, :enl, :mon, CASE WHEN :req = 1 THEN 0 ELSE 1 END, :est, CURRENT_DATE)
            """),
            {"con": concepto, "prov": proveedor_id, "enl": enlace, "mon": float(monto_total), "req": req_aprobacion, "est": estado}
        )
        compra_id = db.session.execute(text("SELECT last_insert_rowid()")).scalar()
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'admin', 'crear_compra', 'COMPRAS', f'Compra {compra_id} por {monto_total}')
    return jsonify({"success": True, "message": "Compra registrada.", "id": compra_id})

@compras_api_bp.route("/<int:compra_id>/aprobar", methods=["POST"])
@requiere_rol("Admin")
def aprobar_compra(compra_id):
    # Simulando el usuario (idealmente esto usaría session['usuario']['rol'])
    try:
        existe = db.session.execute(text("SELECT id FROM compras WHERE id = :id"), {"id": compra_id}).scalar()
        if not existe:
            db.session.rollback()
            return jsonify({"success": False, "error": "Compra no encontrada."}), 404
        db.session.execute(text("UPDATE compras SET estado = 'aprobado', aprobado_ceo = 1, fecha_aprobacion = CURRENT_DATE WHERE id = :id"), {"id": compra_id})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'ceo', 'aprobar_compra', 'COMPRAS', f'Compra {compra_id} aprobada por CEO')
    return jsonify({"success": True, "message": "Compra aprobada."})


@compras_api_bp.route("/<int:compra_id>/rechazar", methods=["POST"])
@requiere_rol("Admin")
def rechazar_compra(compra_id):
    try:
        existe = db.session.execute(text("SELECT id FROM compras WHERE id = :id"), {"id": compra_id}).scalar()
        if not existe:
            db.session.rollback()
            return jsonify({"success": False, "error": "Compra no encontrada."}), 404
        db.session.execute(text("UPDATE compras SET estado = 'rechazado', aprobado_ceo = 0 WHERE id = :id"), {"id": compra_id})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'ceo', 'rechazar_compra', 'COMPRAS', f'Compra {compra_id} rechazada por CEO')
    return jsonify({"success": True, "message": "Compra rechazada."})

@compras_api_bp.route("/<int:compra_id>/pagar", methods=["POST"])
@requiere_rol("Admin")
def pagar_compra(compra_id):
    
    data = request.get_json() or {}
    monto_str = data.get("monto_pagado", 0.0)

    try:
        monto_pagado = Decimal(str(monto_str)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return jsonify({"success": False, "error": "Formato de monto inválido."}), 400

    if monto_pagado <= Decimal('0.00'):
        return jsonify({"success": False, "error": "El monto debe ser positivo."}), 400

    try:
        db.session.execute(text("BEGIN IMMEDIATE"))
        compra = db.session.execute(text("SELECT monto_total, estado FROM compras WHERE id = :id"), {"id": compra_id}).mappings().first()
        
        if not compra:
            db.session.rollback()
            return jsonify({"success": False, "error": "Compra no encontrada."}), 404
            
        if compra["estado"] == "pendiente_aprobacion":
            db.session.rollback()
            return jsonify({"success": False, "error": "Requiere aprobación de CEO antes de pagar."}), 403

        monto_total_compra = Decimal(str(compra["monto_total"])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        pagado_result = db.session.execute(text("SELECT SUM(monto_pagado) FROM compras_pagos WHERE compra_id = :id"), {"id": compra_id}).scalar()
        pagado = Decimal(str(pagado_result or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        balance_actual = monto_total_compra - pagado

        if monto_pagado > balance_actual:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Sobregiro. Pendiente: {balance_actual}"}), 400

        db.session.execute(
            text("INSERT INTO compras_pagos (compra_id, monto_pagado, fecha_pago, referencia) VALUES (:cid, :mon, :fecha, :ref)"),
            {"cid": compra_id, "mon": float(monto_pagado), "fecha": datetime.date.today(), "ref": data.get("referencia", "")}
        )

        nuevo_balance = balance_actual - monto_pagado
        if nuevo_balance == Decimal('0.00'):
            db.session.execute(text("UPDATE compras SET estado = 'pagado' WHERE id = :id"), {"id": compra_id})

        db.session.commit()
        registrar_auditoria(1, 'admin', 'pagar_compra', 'COMPRAS', f'Pago de {monto_pagado} a compra {compra_id}')
        return jsonify({"success": True, "message": "Pago registrado.", "nuevo_balance": float(nuevo_balance)})

    except IntegrityError as e:
        db.session.rollback()
        msg = str(getattr(e, "orig", None) or e)
        if "UNIQUE" in msg.upper():
            return jsonify({"success": False, "error": "Ya existe un registro con este identificador único."}), 409
        current_app.logger.error("Error de integridad al registrar pago de compra %s: %s", compra_id, msg)
        return jsonify({"success": False, "error": "Error interno al registrar el pago."}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error al registrar pago de compra %s: %s", compra_id, repr(e))
        return jsonify({"success": False, "error": "Error interno al registrar el pago."}), 500

@compras_api_bp.route("/<int:compra_id>", methods=["DELETE"])
@requiere_rol("Admin")
def eliminar_compra(compra_id):
    pagos = db.session.execute(text("SELECT COUNT(id) FROM compras_pagos WHERE compra_id = :id"), {"id": compra_id}).scalar()
    if pagos and pagos > 0:
        return jsonify({"success": False, "error": "No se puede eliminar la compra porque tiene pagos asociados."}), 400
        
    db.session.execute(text("UPDATE compras SET estado = 'eliminado' WHERE id = :id"), {"id": compra_id})
    db.session.commit()
    registrar_auditoria(1, 'admin', 'eliminar_compra', 'COMPRAS', f'Compra {compra_id} eliminada')
    return jsonify({"success": True, "message": "Compra eliminada."})

@compras_api_bp.route("/<int:compra_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_compra(compra_id):
    data = request.get_json() or {}
    monto_total = data.get("monto_total")
    estado = data.get("estado")

    updates = []
    params = {"id": compra_id}

    if monto_total is not None:
        updates.append("monto_total = :mon")
        params["mon"] = float(monto_total)

    ALLOWED_ESTADOS = {"en_proceso", "pendiente_aprobacion", "aprobado", "rechazado", "pagado"}
    if estado and estado in ALLOWED_ESTADOS:
        updates.append("estado = :estado")
        params["estado"] = estado

    if not updates:
        return jsonify({"success": False, "error": "No hay datos para actualizar."}), 400

    set_clause = ", ".join(updates)
    try:
        db.session.execute(text(f"UPDATE compras SET {set_clause} WHERE id = :id"), params)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    
    registrar_auditoria(1, 'admin', 'actualizar_compra', 'COMPRAS', f'Compra {compra_id} actualizada')
    return jsonify({"success": True, "message": "Compra actualizada."})
