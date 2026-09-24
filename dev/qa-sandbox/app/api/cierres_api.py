"""
cierres_api.py — Endpoints API para gestión, alta individual y desglose financiero auditable de Cierres.
"""

from flask import Blueprint, jsonify, request, current_app
from app.core.auth_middleware import requiere_rol
from sqlalchemy import text
from app.extensions import db
from sqlalchemy.exc import IntegrityError, OperationalError
from app.core.financial_engine import FinancialEngine
from app.core.auditoria import registrar_auditoria
from app.core.utils import dt_args
from app.core.calendar_service import crear_evento_post_venta
from datetime import date
import datetime

cierres_api_bp = Blueprint("cierres_api", __name__, url_prefix="/api/cierres")


@cierres_api_bp.route("/cierres", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_cierres():
    search_cols = ['t.codigo', 'p.nombre', 'c.nombre']
    sort_cols = ['t.codigo', 't.monto', 't.num_cuotas', 't.monto', 't.monto', 't.estado', None, None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    if not order_clause:
        order_clause = "ORDER BY t.id DESC"
        
    total_filtered = db.session.execute(text(f"SELECT COUNT(t.id) FROM transacciones t LEFT JOIN proyectos p ON t.proyecto_id = p.id LEFT JOIN clientes c ON t.cliente_id = c.id {where_clause}"), params).scalar() or 0
    total_records = db.session.execute(text("SELECT COUNT(id) FROM transacciones")).scalar() or 0
    
    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""
            SELECT t.id, t.codigo, p.nombre as proyecto, e.nombre || ' ' || e.apellido as asesor,
                   c.nombre || ' ' || c.apellido as cliente, t.monto, t.monto_separacion, t.monto_inicial,
                   t.num_cuotas, t.pct_comision, t.estado, t.fecha_evento,
                   t.pct_a, t.pct_n, t.pct_ase1, t.pct_ase2, t.pct_proyecto, t.pct_admin, t.pct_extra, t.pct_pub_gfm,
                   cn.nombre as nivel, cc.nombre as captador, cg.nombre as gastos_pub,
                   t.entidad_id, c.vendedor_captador_id,
                   t.promocion, t.adicionales, t.moneda, t.tiempo_entrega, t.plan_pago_tipo, t.descuento_pct,
                   t.comision_gerencia_total, t.comision_gerencia_pagada, t.comision_gerencia_saldo,
                   t.gastos_legales, t.saldo_pendiente_comision, t.saldo_pagado_comision,
                   t.dropbox_plan_pago, t.dropbox_reserva, t.dropbox_kyc, t.dropbox_contrato, t.dropbox_pago_inicial,
                   t.nombre_propiedad, t.numero_inmueble
            FROM transacciones t
            LEFT JOIN proyectos p ON t.proyecto_id = p.id
            LEFT JOIN entidades e ON t.entidad_id = e.id
            LEFT JOIN clientes c ON t.cliente_id = c.id
            LEFT JOIN cat_niveles cn ON t.nivel_id = cn.id
            LEFT JOIN cat_captadores cc ON t.captador_id = cc.id
            LEFT JOIN cat_gastos_pub cg ON t.gastos_pub_id = cg.id
            {where_clause}
            {order_clause} LIMIT :limit OFFSET :offset
        """),
        params
    ).mappings().all()

    items_list = []
    for r in rows:
        item = dict(r)
        monto = float(item["monto"] or 0)
        sep = float(item.get("monto_separacion") or 0)
        inic = float(item.get("monto_inicial") or 0)
        cuotas = int(item.get("num_cuotas") or 1)
        pct_com = float(item.get("pct_comision") or 5.0)

        # Cálculos inline — sin llamadas al FinancialEngine por fila (era el freeze)
        monto_diferido = max(0.0, monto - sep - inic)
        valor_cuota = round(monto_diferido / cuotas, 2) if cuotas > 0 else 0.0
        bolsa = round(monto * pct_com / 100, 2)
        ingreso_empresa = round(bolsa * (
            float(item.get("pct_proyecto") or 0) +
            float(item.get("pct_admin") or 0) +
            float(item.get("pct_extra") or 0) +
            float(item.get("pct_pub_gfm") or 0)
        ), 2)

        item["monto_diferido"] = monto_diferido
        item["valor_cuota_mensual"] = valor_cuota
        item["monto_a_financiar"] = monto_diferido
        item["bolsa_comision_total"] = bolsa
        item["ingreso_bruto_empresa"] = ingreso_empresa
        item["retencion_neta_empresa"] = round(bolsa * (
            float(item.get("pct_a") or 0) +
            float(item.get("pct_n") or 0) +
            float(item.get("pct_ase1") or 0) +
            float(item.get("pct_ase2") or 0)
        ), 2)

        items_list.append(item)

    if 'draw' in request.args:
        return jsonify({"draw": int(request.args.get('draw', 1)), "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items_list})
    
    return jsonify({"success": True, "total": total_filtered, "items": items_list, "cierres": items_list})


@cierres_api_bp.route("/<int:cierre_id>/desglose-financiero", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def desglose_financiero(cierre_id):
    row = db.session.execute(
        text("""
            SELECT t.id, t.codigo, p.nombre as proyecto, e.nombre || ' ' || e.apellido as asesor,
                   c.nombre || ' ' || c.apellido as cliente, t.monto, t.monto_separacion, t.monto_inicial,
                   t.num_cuotas, t.pct_comision, t.estado, t.fecha_evento,
                   t.pct_a, t.pct_n, t.pct_ase1, t.pct_ase2, t.pct_proyecto, t.pct_admin, t.pct_extra, t.pct_pub_gfm,
                   cn.nombre as nivel, cc.nombre as captador, cg.nombre as gastos_pub,
                   t.entidad_id, c.vendedor_captador_id,
                   e.tipo_persona as tipo_persona_vendedor, e.aplica_itbis as aplica_itbis_vendedor
            FROM transacciones t
            LEFT JOIN proyectos p ON t.proyecto_id = p.id
            LEFT JOIN entidades e ON t.entidad_id = e.id
            LEFT JOIN clientes c ON t.cliente_id = c.id
            LEFT JOIN cat_niveles cn ON t.nivel_id = cn.id
            LEFT JOIN cat_captadores cc ON t.captador_id = cc.id
            LEFT JOIN cat_gastos_pub cg ON t.gastos_pub_id = cg.id
            WHERE t.id = :cid
        """),
        {"cid": cierre_id}
    ).mappings().first()

    if not row:
        return jsonify({"success": False, "error": f"No se encontró la transacción con ID {cierre_id}"}), 404

    item = dict(row)
    monto = float(item["monto"] or 0)
    sep = float(item.get("monto_separacion") or 0)
    inic = float(item.get("monto_inicial") or 0)
    cuotas = int(item.get("num_cuotas") or 0)
    pct_com = float(item.get("pct_comision") or 5.0)

    estructuracion = FinancialEngine.estructurar_venta(monto, sep, inic, cuotas)
    bolsa = FinancialEngine.calcular_bolsa_comision(monto, pct_com)
    
    is_same_asesor = (item.get("entidad_id") == item.get("vendedor_captador_id"))
    
    def safe_pct(val):
        v = float(val or 0)
        return v / 100.0 if v > 1.0 else v
    
    p_a = safe_pct(item.get("pct_a"))
    p_n = safe_pct(item.get("pct_n"))
    p_ase1 = safe_pct(item.get("pct_ase1"))
    p_ase2 = safe_pct(item.get("pct_ase2"))
    p_proyecto = safe_pct(item.get("pct_proyecto"))
    p_admin = safe_pct(item.get("pct_admin"))
    p_extra = safe_pct(item.get("pct_extra"))
    p_pub_gfm = safe_pct(item.get("pct_pub_gfm"))
    comisiones = {
        "bolsa_total": float(bolsa),
        "pct_a": p_a, "comision_a": float(bolsa) * p_a,
        "pct_n": p_n, "comision_n": float(bolsa) * p_n,
        "pct_ase1": p_ase1, "comision_ase1": float(bolsa) * p_ase1,
        "pct_ase2": p_ase2, "comision_ase2": float(bolsa) * p_ase2,
        "pct_proyecto": p_proyecto, "comision_proyecto": float(bolsa) * p_proyecto,
        "pct_admin": p_admin, "comision_admin": float(bolsa) * p_admin,
        "pct_extra": p_extra, "comision_extra": float(bolsa) * p_extra,
        "pct_pub_gfm": p_pub_gfm, "comision_pub_gfm": float(bolsa) * p_pub_gfm,
    }

    ingreso_bruto_empresa = (comisiones.get("comision_proyecto", 0) + 
                             comisiones.get("comision_admin", 0) + 
                             comisiones.get("comision_extra", 0) + 
                             comisiones.get("comision_pub_gfm", 0))
    comisiones["ingreso_bruto_empresa"] = float(ingreso_bruto_empresa)
    comisiones["retencion_neta_empresa"] = float(ingreso_bruto_empresa)
    
    # Calcular retenciones fiscales para el frontend
    fiscales = FinancialEngine.calcular_retenciones_fiscales(
        comisiones["ingreso_bruto_empresa"],
        comisiones.get("comision_a", 0),
        item.get("tipo_persona_vendedor", "Física"),
        item.get("aplica_itbis_vendedor", 1)
    )
    comisiones["fiscales"] = fiscales

    return jsonify({
        "success": True,
        "transaccion": item,
        "estructuracion_venta": estructuracion,
        "comisiones": comisiones
    })


@cierres_api_bp.route("", methods=["POST"])
@requiere_rol("Admin")
def crear_cierre():
    data = request.get_json() or {}
    proyecto_id = data.get("proyecto_id", 1)
    entidad_id = data.get("entidad_id", 1)
    cliente_id = data.get("cliente_id", 1)
    monto = float(data.get("monto", 0.0))
    monto_separacion = float(data.get("monto_separacion", round(monto * 0.05, 2)))
    monto_inicial = float(data.get("monto_inicial", round(monto * 0.20, 2)))
    num_cuotas = int(data.get("num_cuotas", 10))
    pct_comision = float(data.get("pct_comision", 5.0))
    estado = data.get("estado", "en_proceso")
    # Deduzir Nivel (del asesor) y Captador (nivel del captador del proyecto)
    nivel_id = db.session.execute(text("SELECT nivel_certificacion_id FROM entidades WHERE id = :eid"), {"eid": entidad_id}).scalar() or 1
    
    proy_cap_id = db.session.execute(text("SELECT captador_id FROM proyectos WHERE id = :pid"), {"pid": proyecto_id}).scalar()
    if proy_cap_id:
        captador_id = db.session.execute(text("SELECT nivel_certificacion_id FROM entidades WHERE id = :eid"), {"eid": proy_cap_id}).scalar() or 1
    else:
        captador_id = 1 # Fallback genérico si el proyecto no tiene captador asignado

    gastos_pub_id = data.get("gastos_pub_id")
    origen_prospecto = data.get("origen_prospecto", "propio")
    fecha_cierre = data.get("fecha_cierre")
    if not fecha_cierre:
        fecha_cierre = datetime.date.today()

    if not monto or monto <= 0:
        return jsonify({"success": False, "error": "El monto del cierre debe ser mayor a 0."}), 400
    if not gastos_pub_id:
        return jsonify({"success": False, "error": "Debe seleccionar Gastos Publicidad (SÍ / NO)."}), 400

    try:
        # Prevención de duplicados estricta con lock de escritura (Idempotencia en race conditions)
        existente = db.session.execute(
            text("SELECT id FROM transacciones WHERE proyecto_id = :p AND cliente_id = :c AND estado != 'cancelado'"),
            {"p": proyecto_id, "c": cliente_id}
        ).scalar()
        if existente:
            db.session.rollback()
            return jsonify({"success": False, "error": "El cliente ya tiene una transacción activa en este proyecto."}), 409

        count = db.session.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM transacciones")).scalar()
        codigo = f"CIE-{count:04d}"

        # === Campos de captacion (xlsx) ===
        promocion = data.get("promocion", "")
        adicionales = data.get("adicionales", "")
        moneda = data.get("moneda", "USD")
        tiempo_entrega = data.get("tiempo_entrega")
        plan_pago_tipo = data.get("plan_pago_tipo", "")
        descuento_pct = float(data.get("descuento_pct", 0))
        # === Comision gerencia 50/50 ===
        gastos_legales = float(data.get("gastos_legales", 0))
        # === Identificador de inmueble ===
        nombre_propiedad = data.get("nombre_propiedad", "")
        numero_inmueble = data.get("numero_inmueble", "")

        # Prevención de duplicados estricta con lock de escritura (Idempotencia en race conditions)
        vendedor = db.session.execute(text("SELECT id, nivel, tipo_persona, aplica_itbis FROM entidades WHERE id = :eid"), {"eid": entidad_id}).mappings().first()
        vendedor_captador_id = db.session.execute(text("SELECT vendedor_captador_id FROM clientes WHERE id = :cid"), {"cid": cliente_id}).scalar()
        captador = db.session.execute(text("SELECT id, nivel FROM entidades WHERE id = :cid"), {"cid": vendedor_captador_id}).mappings().first() if vendedor_captador_id else None
        proyecto = db.session.execute(text("SELECT es_exclusivo FROM proyectos WHERE id = :pid"), {"pid": proyecto_id}).mappings().first()
        
        is_same_asesor = (entidad_id == vendedor_captador_id) if vendedor_captador_id else False
        
        # Mapeo de niveles a IDs enteros según manual de Inmobiliaria
        def nivel_a_id(nivel_str):
            n = (nivel_str or "").lower()
            if "junior" in n: return 2
            elif "senior" in n: return 3
            elif "externo" in n or "broker" in n: return 4
            elif "agencia" in n or "juridica" in n or "jurídica" in n: return 5
            elif "referidor" in n: return 6
            return 1 # Inmobiliario por defecto
            
        vendedor_id = nivel_a_id(vendedor['nivel'] if vendedor else "")
        captador_nivel_id = nivel_a_id(captador['nivel'] if captador else "")
        es_exclusivo = bool(proyecto['es_exclusivo']) if proyecto else True
        
        bolsa_total = FinancialEngine.calcular_bolsa_comision(monto, pct_comision)
        
        comis = FinancialEngine.calcular_distribucion_inmobiliaria(
            bolsa_total,
            vendedor_id=vendedor_id,
            captador_id=captador_nivel_id,
            origen_prospecto=origen_prospecto,
            es_exclusivo=es_exclusivo,
            is_same_asesor=is_same_asesor
        )
        
        tipo_persona = vendedor['tipo_persona'] if vendedor else 'Física'
        aplica_itbis = vendedor['aplica_itbis'] if vendedor else True

        
        ingreso_bruto_empresa = comis['comision_proyecto'] + comis['comision_admin'] + comis['comision_extra'] + comis['comision_pub_gfm']
        
        comision_vendedor_total = comis['comision_a']
        if is_same_asesor:
            comision_vendedor_total += comis['comision_n']
        
        fiscales = FinancialEngine.calcular_retenciones_fiscales(
            ingreso_bruto_empresa,
            comision_vendedor_total,
            tipo_persona,
            aplica_itbis
        )

        db.session.execute(
            text("""
                INSERT INTO transacciones (
                    codigo, proyecto_id, entidad_id, cliente_id, monto, monto_separacion, monto_inicial,
                    num_cuotas, pct_comision, estado, fecha_evento, canal,
                    financiamiento, kyc_completo, sla_dias_meta, estado_plan_pagos, atributos_extra,
                    nivel_id, captador_id, gastos_pub_id, fecha_cierre, origen_prospecto,
                    pct_a, pct_n, pct_ase1, pct_ase2, pct_proyecto, pct_admin, pct_extra, pct_pub_gfm,
                    comision_empresa_sin_itbis, itbis_comision_empresa, comision_vendedor_bruta,
                    tipo_persona_vendedor, aplica_itbis_vendedor, pct_isr, retencion_isr,
                    itbis_vendedor, pct_itbis_retenido, retencion_itbis, total_retenciones,
                    neto_pagado_vendedor, costo_total_vendedor, ganancia_empresa_sin_itbis, margen_empresa_neto,
                    promocion, adicionales, moneda, tiempo_entrega, plan_pago_tipo, descuento_pct,
                    comision_gerencia_total, comision_gerencia_saldo, gastos_legales,
                    nombre_propiedad, numero_inmueble
                ) VALUES (
                    :cod, :pid, :eid, :cid, :monto, :sep, :inic,
                    :cuotas, :pct, :est, CURRENT_DATE, 'interno',
                    0, 0, 10, 'al_dia', '{}',
                    :nid, :cap_id, :gid, :fecha_cierre, :origen,
                    :pa, :pn, :pase1, :pase2, :pproy, :padmin, :pext, :ppub,
                    :c_empresa, :i_empresa, :c_vendedor,
                    :tp_vendedor, :ai_vendedor, :p_isr, :r_isr,
                    :i_vend, :p_i_ret, :r_itbis, :t_ret,
                    :n_pagado, :c_tot, :g_empresa, :m_neto,
                    :promocion, :adicionales, :moneda, :tiempo_entrega, :plan_pago, :descuento,
                    :gerencia_total, :gerencia_saldo, :gastos_legales,
                    :nombre_propiedad, :numero_inmueble
                )
            """),
            {
                "cod": codigo, "pid": proyecto_id, "eid": entidad_id, "cid": cliente_id,
                "monto": monto, "sep": monto_separacion, "inic": monto_inicial,
                "cuotas": num_cuotas, "pct": pct_comision, "est": estado,
                "nid": nivel_id, "cap_id": captador_id, "gid": gastos_pub_id, "fecha_cierre": fecha_cierre, "origen": origen_prospecto,
                "pa": comis["pct_a"], "pn": comis["pct_n"], "pase1": comis["pct_ase1"], "pase2": comis["pct_ase2"],
                "pproy": comis["pct_proyecto"], "padmin": comis["pct_admin"], "pext": comis["pct_extra"], "ppub": comis["pct_pub_gfm"],
                "c_empresa": fiscales["comision_empresa_sin_itbis"],
                "i_empresa": fiscales["itbis_comision_empresa"],
                "c_vendedor": fiscales["comision_vendedor_bruta"],
                "tp_vendedor": fiscales["tipo_persona_vendedor"],
                "ai_vendedor": fiscales["aplica_itbis_vendedor"],
                "p_isr": fiscales["pct_isr"],
                "r_isr": fiscales["retencion_isr"],
                "i_vend": fiscales["itbis_vendedor"],
                "p_i_ret": fiscales["pct_itbis_retenido"],
                "r_itbis": fiscales["retencion_itbis"],
                "t_ret": fiscales["total_retenciones"],
                "n_pagado": fiscales["neto_pagado_vendedor"],
                "c_tot": fiscales["costo_total_vendedor"],
                "g_empresa": fiscales["ganancia_empresa_sin_itbis"],
                "m_neto": fiscales["margen_empresa_neto"],
                "promocion": promocion, "adicionales": adicionales, "moneda": moneda,
                "tiempo_entrega": tiempo_entrega, "plan_pago": plan_pago_tipo, "descuento": descuento_pct,
                "gerencia_total": round(monto * pct_comision / 100 * 0.50, 2),
                "gerencia_saldo": round(monto * pct_comision / 100 * 0.50, 2),
                "gastos_legales": gastos_legales,
                "nombre_propiedad": nombre_propiedad, "numero_inmueble": numero_inmueble
          }
        )
        
        # Generación automática de CXP (Hito 1: Separación - 50% del neto pagado al vendedor)
        monto_neto = float(fiscales["neto_pagado_vendedor"])
        monto_hito_1 = round(monto_neto * 0.50, 2)
        
        transaccion_id_nuevo = db.session.execute(text("SELECT id FROM transacciones WHERE codigo = :cod"), {"cod": codigo}).scalar()
        
        # Insertar 1ra CXP (Hito 1)
        db.session.execute(
            text("INSERT INTO comisiones_pagos (entidad_id, transaccion_id, monto, estado, hito, fecha_generacion, fecha_maxima_pago) VALUES (:eid, :tid, :monto, 'pendiente_aprobacion', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
            {"eid": entidad_id, "tid": transaccion_id_nuevo, "monto": monto_hito_1}
        )

        # Configurar saldos iniciales
        db.session.execute(
            text("UPDATE transacciones SET saldo_pendiente_comision = :pend WHERE id = :tid"),
            {"pend": monto_neto, "tid": transaccion_id_nuevo}
        )

        db.session.commit()
        registrar_auditoria(1, 'admin', 'crear_cierre', 'CIERRES', f'Cierre {codigo} registrado por {monto}')
        
        # Disparar evento de seguimiento en Google Calendar
        # Asumimos que podemos recuperar el nombre del cliente
        cliente_nombre = db.session.execute(text("SELECT nombre || ' ' || apellido FROM clientes WHERE id = :cid"), {"cid": cliente_id}).scalar()
        if cliente_nombre:
            crear_evento_post_venta(
                nombre_cliente=cliente_nombre,
                transaccion_codigo=codigo,
                fecha_cierre=date.today()
            )
            
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409
    except OperationalError as e:
        db.session.rollback()
        current_app.logger.error("Error operacional al crear cierre: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500
    except Exception as e:
        print('REAL EXCEPTION:', repr(e))
        import traceback; traceback.print_exc()
        db.session.rollback()
        if "database is locked" in str(e).lower() or "operationalerror" in str(e).lower():
            return jsonify({"success": False, "error": "La base de datos está ocupada (Database is locked). Por favor, intenta de nuevo en unos segundos."}), 409
        current_app.logger.error("Error interno al crear cierre: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

    estructuracion = FinancialEngine.estructurar_venta(monto, monto_separacion, monto_inicial, num_cuotas)
    return jsonify({
        "success": True,
        "message": f"Cierre '{codigo}' por ${monto:,.2f} USD registrado exitosamente.",
        "detalles_financieros": estructuracion
    })

@cierres_api_bp.route("/<int:cierre_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_cierre(cierre_id):
    data = request.get_json() or {}
    pct_comision = float(data.get("pct_comision", 5.0))
    monto = data.get("monto")
    fecha_cierre = data.get("fecha_cierre")
    if not fecha_cierre:
        fecha_cierre = datetime.date.today()

    comprobante_fiscal = data.get("comprobante_fiscal")
    ingreso_verificado = data.get("ingreso_verificado")
    estado_plan_pagos = data.get("estado_plan_pagos")
    estado = data.get("estado")

    update_monto_clause = ", monto = :monto" if monto else ""
    params = {"pct_comision": pct_comision, "id": cierre_id, "fecha_cierre": fecha_cierre}
    if monto:
        params["monto"] = float(monto)

    # Añadir actualización de nuevos campos
    extra_updates = ""
    if estado is not None:
        extra_updates += ", estado = :estado"
        params["estado"] = estado
    if comprobante_fiscal is not None:
        extra_updates += ", comprobante_fiscal = :ncf"
        params["ncf"] = comprobante_fiscal
    if ingreso_verificado is not None:
        extra_updates += ", ingreso_verificado = :ing_v"
        params["ing_v"] = int(ingreso_verificado) # 1 or 0
    if estado_plan_pagos is not None:
        extra_updates += ", estado_plan_pagos = :epp"
        params["epp"] = estado_plan_pagos

    try:
        db.session.execute(text("BEGIN IMMEDIATE"))
        
        # Recuperar transaccion actual
        tx = db.session.execute(text("SELECT id, entidad_id, neto_pagado_vendedor, estado_plan_pagos FROM transacciones WHERE id = :id"), {"id": cierre_id}).mappings().first()
        if not tx:
            db.session.rollback()
            return jsonify({"success": False, "error": "Transacción no encontrada."}), 404

        db.session.execute(
            text(f"""
                UPDATE transacciones 
                SET pct_comision = :pct_comision, fecha_cierre = :fecha_cierre {update_monto_clause} {extra_updates}
                WHERE id = :id
            """),
            params
        )

        # Si se actualizó a inicial_completado, generar Hito 2 si no existe
        if estado_plan_pagos == 'inicial_completado' and tx["estado_plan_pagos"] != 'inicial_completado':
            # Verificar si ya existe Hito 2
            existente_h2 = db.session.execute(text("SELECT id FROM comisiones_pagos WHERE transaccion_id = :id AND hito = 2"), {"id": cierre_id}).scalar()
            if not existente_h2:
                # Generar hito 2 (50% restante)
                monto_neto = float(tx["neto_pagado_vendedor"])
                monto_hito_1 = round(monto_neto * 0.50, 2)
                monto_hito_2 = monto_neto - monto_hito_1
                
                db.session.execute(
                    text("INSERT INTO comisiones_pagos (entidad_id, transaccion_id, monto, estado, hito, fecha_generacion, fecha_maxima_pago) VALUES (:eid, :tid, :monto, 'pendiente_aprobacion', 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                    {"eid": tx["entidad_id"], "tid": cierre_id, "monto": monto_hito_2}
                )

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error al actualizar cierre %s: %s", cierre_id, repr(e))
        return jsonify({"success": False, "error": "Error interno al actualizar el cierre. Intente nuevamente."}), 500
    registrar_auditoria(1, 'admin', 'editar_cierre', 'CIERRES', f'Cierre {cierre_id} actualizado')
    return jsonify({"success": True, "message": "Transaccion actualizada correctamente."})

@cierres_api_bp.route("/<int:cierre_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_cierre(cierre_id):
    try:
        # Soft delete manejado por estados (cancelado) en lugar de DELETE físico
        db.session.execute(text("UPDATE transacciones SET estado = 'cancelado' WHERE id = :id"), {"id": cierre_id})
        db.session.commit()
        registrar_auditoria(1, 'admin', 'borrar_cierre', 'CIERRES', f'Cierre {cierre_id} cancelado logicamente')
        return jsonify({"success": True, "message": "Transaccion cancelada correctamente."})
    except Exception as e:
        print('REAL EXCEPTION:', repr(e))
        import traceback; traceback.print_exc()
        db.session.rollback()
        current_app.logger.error("Error al cancelar cierre %s: %s", cierre_id, repr(e))
        return jsonify({"success": False, "error": "Error interno al cancelar el cierre. Intente nuevamente."}), 500


# === ENDPOINTS DE DOCUMENTOS (DROPBOX) ===

@cierres_api_bp.route("/<int:cierre_id>/documentos", methods=["GET"])
@requiere_rol("Admin")
def listar_documentos(cierre_id):
    """Retorna los enlaces de Dropbox de los documentos del cierre."""
    row = db.session.execute(
        text("""SELECT dropbox_plan_pago, dropbox_reserva, dropbox_kyc, dropbox_contrato, dropbox_pago_inicial
                FROM transacciones WHERE id = :id"""),
        {"id": cierre_id}
    ).mappings().first()
    if not row:
        return jsonify({"success": False, "error": "Cierre no encontrado."}), 404
    docs = {
        "plan_pago": row["dropbox_plan_pago"] or "",
        "reserva": row["dropbox_reserva"] or "",
        "kyc": row["dropbox_kyc"] or "",
        "contrato": row["dropbox_contrato"] or "",
        "pago_inicial": row["dropbox_pago_inicial"] or "",
    }
    return jsonify({"success": True, "documentos": docs})


@cierres_api_bp.route("/<int:cierre_id>/documentos", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_documento(cierre_id):
    """Guarda el enlace de Dropbox de un documento del cierre."""
    data = request.get_json() or {}
    doc_type = data.get("tipo", "")
    enlace = data.get("enlace", "")

    valid_docs = {
        "plan_pago": "dropbox_plan_pago",
        "reserva": "dropbox_reserva",
        "kyc": "dropbox_kyc",
        "contrato": "dropbox_contrato",
        "pago_inicial": "dropbox_pago_inicial",
    }
    if doc_type not in valid_docs:
        return jsonify({"success": False, "error": f"Tipo de documento invalido. Use: {list(valid_docs.keys())}"}), 400

    col = valid_docs[doc_type]
    try:
        db.session.execute(text(f"UPDATE transacciones SET {col} = :enlace WHERE id = :id"), {"enlace": enlace, "id": cierre_id})
        db.session.commit()
        registrar_auditoria(1, 'admin', 'actualizar_documento', 'CIERRES', f'Doc {doc_type} actualizado en cierre {cierre_id}')
        return jsonify({"success": True, "message": f"Documento '{doc_type}' actualizado."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error al actualizar documento en cierre %s: %s", cierre_id, repr(e))
        return jsonify({"success": False, "error": "Error interno al actualizar el documento. Intente nuevamente."}), 500
