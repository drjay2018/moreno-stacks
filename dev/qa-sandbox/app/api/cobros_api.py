"""
cobros_api.py — Endpoints API para consulta y alta individual de Cobros y Morosidad.
"""

from flask import Blueprint, jsonify, request, current_app
from app.core.auth_middleware import requiere_rol
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from app.core.auditoria import registrar_auditoria
from app.core.utils import dt_args

cobros_api_bp = Blueprint("cobros_api", __name__, url_prefix="/api/cobros")


@cobros_api_bp.route("/cobros", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_cobros():
    search_cols = ['c.concepto', 'c.tipo', 't.codigo']
    sort_cols = ['c.id', 't.codigo', 'c.concepto', 'c.tipo', 'c.monto_total', 'total_pagado', 'balance_pendiente', 'c.fecha_vencimiento', None, None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    # Custom where for active state
    if "WHERE" in where_clause:
        where_clause += " AND (c.estado_aging_id IS NULL OR c.estado_aging_id != 99)"
    else:
        where_clause = "WHERE (c.estado_aging_id IS NULL OR c.estado_aging_id != 99)"
    
    if not order_clause:
        order_clause = "ORDER BY c.id DESC"
        
    total_records = db.session.execute(text("SELECT COUNT(id) FROM cobros WHERE estado_aging_id IS NULL OR estado_aging_id != 99")).scalar() or 0
    total_filtered = db.session.execute(text(f"SELECT COUNT(c.id) FROM cobros c LEFT JOIN transacciones t ON c.transaccion_id = t.id {where_clause}"), params).scalar() or 0
    
    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""
            SELECT c.id, c.concepto, c.tipo, c.monto_total, c.fecha_generado, c.fecha_vencimiento,
                   CAST((julianday('now') - julianday(c.fecha_vencimiento)) AS INTEGER) as dias_reales,
                   t.codigo as transaccion, t.nombre_propiedad, t.numero_inmueble, t.moneda,
                   COALESCE(SUM(p.monto), 0) as total_pagado,
                   MAX(p.enlace_dropbox) as enlace_dropbox,
                   MAX(p.referencia) as referencia
            FROM cobros c
            LEFT JOIN transacciones t ON c.transaccion_id = t.id
            LEFT JOIN pagos p ON c.id = p.cobro_id
            {where_clause}
            GROUP BY c.id
            {order_clause} LIMIT :limit OFFSET :offset
        """),
        params
    ).mappings().all()

    items_list = []
    for r in rows:
        d = dict(r)
        d['balance_pendiente'] = float(d['monto_total'] - d['total_pagado'])
        
        dias = d.get('dias_reales') or 0
        d['dias_mora_calculados'] = dias
        
        if d['balance_pendiente'] <= 0:
            d['estado_mora'] = 'PAGADO'
        elif dias > 60:
            d['estado_mora'] = 'CRÍTICO'      # vencido hace más de 60 días
        elif dias > 30:
            d['estado_mora'] = 'ALERTA'       # vencido hace 30-60 días
        elif dias > 0:
            d['estado_mora'] = 'EN MORA'      # vencido (días pasados > 0)
        elif dias >= -7:
            d['estado_mora'] = 'POR VENCER'   # vence en los próximos 7 días
        else:
            d['estado_mora'] = 'AL DÍA'       # vence en más de 7 días
            
        items_list.append(d)
        
    if 'draw' in request.args:
        return jsonify({"draw": int(request.args.get('draw', 1)), "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items_list})

    return jsonify({"success": True, "total": total_filtered, "items": items_list, "cobros": items_list})


@cobros_api_bp.route("", methods=["POST"])
@requiere_rol("Admin")
def crear_cobro():
    data = request.get_json() or {}
    transaccion_id = data.get("transaccion_id", 1)
    tipo = data.get("tipo", "cuota")
    concepto = data.get("concepto", "Pago de Cuota Inicial").strip()
    monto_str = data.get("monto_total", 0.0)

    try:
        monto_total = Decimal(str(monto_str)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return jsonify({"success": False, "error": "El monto_total tiene un formato inválido."}), 400

    if not concepto or monto_total <= Decimal('0.00'):
        return jsonify({"success": False, "error": "El concepto y un monto positivo son requeridos."}), 400

    try:
        db.session.execute(
            text("""
                INSERT INTO cobros (transaccion_id, tipo, concepto, monto_total, fecha_generado, fecha_vencimiento, dias_mora_calculados)
                VALUES (:tid, :tipo, :con, :monto, CURRENT_DATE, CURRENT_DATE, 0)
            """),
            {"tid": transaccion_id, "tipo": tipo, "con": concepto, "monto": float(monto_total)}
        )
        cobro_id = db.session.execute(text("SELECT last_insert_rowid()")).scalar()
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'admin', 'crear_cobro', 'COBROS', f'Cobro manual C-{cobro_id} creado: {concepto} por {monto_total}')
    return jsonify({"success": True, "message": "Cobro creado manualmente.", "id": cobro_id})

@cobros_api_bp.route("/<int:cobro_id>/pagar", methods=["POST"])
@requiere_rol("Admin")
def pagar_cobro(cobro_id):
    data = request.get_json() or {}
    monto_abono_str = data.get("monto_abono")
    
    try:
        monto_abono = Decimal(str(monto_abono_str)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return jsonify({"success": False, "error": "Formato de monto inválido."}), 400

    if monto_abono <= Decimal('0.00'):
        return jsonify({"success": False, "error": "El monto debe ser positivo."}), 400

    try:
        # Bloqueo a nivel base de datos para simular SELECT ... FOR UPDATE en SQLite
        db.session.execute(text("BEGIN IMMEDIATE"))
        
        cobro = db.session.execute(
            text("SELECT transaccion_id, monto_total FROM cobros WHERE id = :id"), 
            {"id": cobro_id}
        ).mappings().first()

        if not cobro:
            db.session.rollback()
            return jsonify({"success": False, "error": "Cobro no encontrado."}), 404

        monto_total_cobro = Decimal(str(cobro["monto_total"])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        pagado_result = db.session.execute(
            text("SELECT SUM(monto) FROM pagos WHERE cobro_id = :id"),
            {"id": cobro_id}
        ).scalar()
        
        pagado = Decimal(str(pagado_result or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        balance_actual = monto_total_cobro - pagado

        if monto_abono > balance_actual:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Sobregiro detectado. El balance pendiente es {balance_actual}."}), 400

        db.session.execute(
            text("""
                INSERT INTO pagos (cobro_id, monto, fecha_pago, metodo, referencia, enlace_dropbox, registrado_en)
                VALUES (:cid, :monto, CURRENT_DATE, :metodo, :ref, :enl, CURRENT_TIMESTAMP)
            """),
            {
                "cid": cobro_id, 
                "monto": float(monto_abono), 
                "metodo": data.get("metodo", "efectivo"), 
                "ref": data.get("referencia", ""),
                "enl": data.get("enlace_dropbox", "")
            }
        )

        nuevo_balance = balance_actual - monto_abono

        if nuevo_balance == Decimal('0.00'):
            # Cambiar estado del cobro a completado. (ID 99 simulado para "Completado")
            db.session.execute(text("UPDATE cobros SET estado_aging_id = 99 WHERE id = :id"), {"id": cobro_id})
            
            # Chequear si la transaccion completa ya fue saldada
            tid = cobro["transaccion_id"]
            total_transaccion = db.session.execute(text("SELECT monto FROM transacciones WHERE id = :tid"), {"tid": tid}).scalar()
            total_pagos_transaccion = db.session.execute(
                text("SELECT SUM(p.monto) FROM pagos p JOIN cobros c ON p.cobro_id = c.id WHERE c.transaccion_id = :tid"),
                {"tid": tid}
            ).scalar()
            
            tt = Decimal(str(total_transaccion or '0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            tpt = Decimal(str(total_pagos_transaccion or '0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            if tt > Decimal('0.00') and tt == tpt:
                db.session.execute(text("UPDATE transacciones SET estado = 'completado' WHERE id = :tid"), {"tid": tid})

        db.session.commit()
        registrar_auditoria(1, 'admin', 'registrar_abono', 'COBROS', f'Abono de {monto_abono} al cobro {cobro_id}')
        return jsonify({"success": True, "message": "Pago registrado exitosamente.", "nuevo_balance": float(nuevo_balance)})

    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    except Exception as e:
        db.session.rollback()
        if "database is locked" in str(e).lower() or "operationalerror" in str(e).lower():
            return jsonify({"success": False, "error": "El recurso está ocupado, reintente la operación."}), 409
        current_app.logger.error("Error al registrar pago: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

@cobros_api_bp.route("/<int:cobro_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_cobro(cobro_id):
    data = request.get_json() or {}
    concepto = data.get("concepto", "").strip()
    monto_total = data.get("monto_total")
    tipo = data.get("tipo")

    if not concepto:
        return jsonify({"success": False, "error": "El concepto es requerido."}), 400

    params = {"concepto": concepto, "id": cobro_id}
    ALLOWED_COLUMNS = {"concepto", "monto_total", "tipo"}
    updates = ["concepto = :concepto"]
    
    if monto_total:
        params["monto_total"] = float(monto_total)
        updates.append("monto_total = :monto_total")
    if tipo:
        params["tipo"] = tipo
        updates.append("tipo = :tipo")

    set_clause = ", ".join(updates)

    try:
        resultado = db.session.execute(
            text(f"UPDATE cobros SET {set_clause} WHERE id = :id"),
            params
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    if resultado.rowcount == 0:
        return jsonify({"success": False, "error": "Cobro no encontrado."}), 404
    registrar_auditoria(1, 'admin', 'editar_cobro', 'COBROS', f'Cobro {cobro_id} actualizado')
    return jsonify({"success": True, "message": "Cobro actualizado correctamente."})

@cobros_api_bp.route("/<int:cobro_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_cobro(cobro_id):
    from sqlalchemy.exc import IntegrityError
    try:
        # Soft delete: update estado to un estado cancelado (ej. 98 o 99, 
        # asumiendo 99 es cancelado/completado o agregar un flag 'activo').
        # En v1.8 no se borran cobros físicamente.
        pagos = db.session.execute(text("SELECT COUNT(id) FROM pagos WHERE cobro_id = :id"), {"id": cobro_id}).scalar()
        if pagos > 0:
            return jsonify({"success": False, "error": "No se puede cancelar un cobro que ya tiene pagos registrados."}), 400
            
        db.session.execute(text("UPDATE cobros SET estado_aging_id = 99, concepto = concepto || ' (CANCELADO)' WHERE id = :id"), {"id": cobro_id})
        db.session.commit()
        registrar_auditoria(1, 'admin', 'borrar_cobro', 'COBROS', f'Cobro {cobro_id} cancelado (soft-delete)')
        return jsonify({"success": True, "message": "Cobro cancelado correctamente."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
