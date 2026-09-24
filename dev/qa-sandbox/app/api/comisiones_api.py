from flask import Blueprint, jsonify, request, session, current_app
from app.core.auth_middleware import requiere_rol
from sqlalchemy import text
from app.extensions import db
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from app.core.auditoria import registrar_auditoria
from app.core.utils import dt_args
import datetime

comisiones_api_bp = Blueprint("comisiones_api", __name__, url_prefix="/api/comisiones")

@comisiones_api_bp.route("/comisiones", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_comisiones():
    search_cols = ['t.codigo', 'e.nombre', 'cp.estado']
    sort_cols = ['cp.id', 't.codigo', 'e.nombre', 'cp.monto', 'cp.estado', 'cp.fecha_maxima_pago', 'cp.fecha_pago', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    if "WHERE" in where_clause:
        where_clause = where_clause.replace("WHERE ", "WHERE cp.estado != 'cancelado' AND ")
    else:
        where_clause = "WHERE cp.estado != 'cancelado'"
        
    if not order_clause:
        order_clause = "ORDER BY cp.id DESC"
        
    total_records = db.session.execute(text("SELECT COUNT(id) FROM comisiones_pagos")).scalar() or 0
    total_filtered = db.session.execute(text(f"SELECT COUNT(cp.id) FROM comisiones_pagos cp LEFT JOIN transacciones t ON cp.transaccion_id = t.id LEFT JOIN entidades e ON cp.entidad_id = e.id {where_clause}"), params).scalar() or 0
    
    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""
            SELECT cp.id, cp.transaccion_id, t.codigo as transaccion, cp.entidad_id, e.nombre as entidad,
                   'N/A' as rol_comision, cp.monto as monto_comision, cp.estado, 
                   CASE WHEN cp.estado = 'pendiente_aprobacion' THEN 1 ELSE 0 END as requiere_aprobacion_ceo, 
                   cp.fecha_generacion, cp.fecha_pago, cp.fecha_maxima_pago,
                   t.nombre_propiedad, t.numero_inmueble, t.moneda, cp.hito
            FROM comisiones_pagos cp
            LEFT JOIN transacciones t ON cp.transaccion_id = t.id
            LEFT JOIN entidades e ON cp.entidad_id = e.id
            {where_clause}
            {order_clause} LIMIT :limit OFFSET :offset
        """),
        params
    ).mappings().all()

    items_list = []
    for r in rows:
        d = dict(r)
        
        fecha_max_str = d.get('fecha_maxima_pago')
        fecha_max = None
        if fecha_max_str:
            try:
                fecha_max = datetime.datetime.strptime(fecha_max_str.split()[0], '%Y-%m-%d').date()
            except (ValueError, AttributeError):
                fecha_max = None
        hoy = datetime.date.today()
        
        if d['estado'] == 'pagado':
            d['estado_pago'] = 'PAGADA'
        elif fecha_max and hoy > fecha_max:
            d['estado_pago'] = 'VENCIDA'
        else:
            d['estado_pago'] = 'EN FECHA'

        items_list.append(d)
        
    if 'draw' in request.args:
        return jsonify({"draw": int(request.args.get('draw', 1)), "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items_list})

    return jsonify({"success": True, "total": total_filtered, "items": items_list, "comisiones": items_list})

@comisiones_api_bp.route("/<int:comision_id>/aprobar", methods=["POST"])
@requiere_rol("Admin")
def aprobar_comision(comision_id):
    try:
        existe = db.session.execute(
            text("SELECT 1 FROM comisiones_pagos WHERE id = :id"), {"id": comision_id}
        ).first()
        if not existe:
            return jsonify({"success": False, "error": f"Comisión {comision_id} no encontrada."}), 404
        db.session.execute(text("UPDATE comisiones_pagos SET estado = 'aprobado' WHERE id = :id"), {"id": comision_id})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    registrar_auditoria(1, 'ceo', 'aprobar_comision', 'COMISIONES', f'Comision {comision_id} aprobada por CEO')
    return jsonify({"success": True, "message": "Comisión aprobada."})

@comisiones_api_bp.route("/<int:comision_id>/pagar", methods=["POST"])
@requiere_rol("Admin")
def pagar_comision(comision_id):
    try:
        db.session.execute(text("BEGIN IMMEDIATE"))
        comision = db.session.execute(text("SELECT * FROM comisiones_pagos WHERE id = :id"), {"id": comision_id}).mappings().first()
        
        if not comision:
            db.session.rollback()
            return jsonify({"success": False, "error": "Comisión no encontrada."}), 404
            
        if comision["estado"] == "pendiente_aprobacion":
            db.session.rollback()
            return jsonify({"success": False, "error": "Requiere aprobación de CEO antes de pagar."}), 403
            
        if comision["estado"] == "pagado":
            db.session.rollback()
            return jsonify({"success": False, "error": "La comisión ya se encuentra pagada."}), 400

        # Verificaciones obligatorias de la transacción
        transaccion = db.session.execute(text("SELECT * FROM transacciones WHERE id = :tid"), {"tid": comision["transaccion_id"]}).mappings().first()
        if not transaccion:
            db.session.rollback()
            return jsonify({"success": False, "error": "Transacción asociada no encontrada."}), 404

        # REGLA 1: NCF Válido
        if not transaccion.get("comprobante_fiscal"):
            db.session.rollback()
            return jsonify({"success": False, "error": "Operación sin Comprobante Fiscal (NCF). No se puede liquidar el pago sin NCF."}), 403

        # REGLA 2: Ingreso verificado en banco
        if not transaccion.get("ingreso_verificado"):
            db.session.rollback()
            return jsonify({"success": False, "error": "Ingreso no verificado en banco. No se permite anticipar pagos."}), 403

        # REGLA 3: Idempotencia y validación de hito 2
        hito_actual = comision.get("hito", 1)
        if hito_actual == 2:
            # Validar que hito 1 esté pagado
            hito_1 = db.session.execute(
                text("SELECT estado FROM comisiones_pagos WHERE transaccion_id = :tid AND hito = 1"),
                {"tid": transaccion["id"]}
            ).mappings().first()
            if not hito_1 or hito_1["estado"] != "pagado":
                db.session.rollback()
                return jsonify({"success": False, "error": "No se puede liquidar el Hito 2 si el Hito 1 sigue pendiente."}), 403

        # Actualizar la cuenta por pagar (CXP)
        db.session.execute(
            text("UPDATE comisiones_pagos SET estado = 'pagado', fecha_pago = CURRENT_TIMESTAMP WHERE id = :id"), 
            {"id": comision_id}
        )
        
        # REGLA 4: Actualizar saldos y dashboard (rebajar pendiente, aumentar pagado)
        monto_a_pagar = float(comision["monto"])
        
        nuevo_pendiente = max(0.0, float(transaccion.get("saldo_pendiente_comision", 0.0)) - monto_a_pagar)
        nuevo_pagado = float(transaccion.get("saldo_pagado_comision", 0.0)) + monto_a_pagar
        
        # Si es el Hito 2 y quedó pagado, o si saldo_pendiente llegó a 0
        nuevo_estado_operacion = transaccion["estado"]
        if nuevo_pendiente <= 0:
            nuevo_estado_operacion = "Liquidado"
        elif hito_actual == 1:
            nuevo_estado_operacion = "Pago parcial"

        db.session.execute(
            text("""
                UPDATE transacciones 
                SET saldo_pendiente_comision = :pend, 
                    saldo_pagado_comision = :pag,
                    estado = :est
                WHERE id = :tid
            """),
            {"pend": nuevo_pendiente, "pag": nuevo_pagado, "est": nuevo_estado_operacion, "tid": transaccion["id"]}
        )

        db.session.commit()
        registrar_auditoria(1, 'admin', 'pagar_comision', 'COMISIONES', f'Comisión {comision_id} (Hito {hito_actual}) pagada por {monto_a_pagar}')
        return jsonify({"success": True, "message": "Comisión pagada y saldos actualizados correctamente."})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en comisiones_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500
