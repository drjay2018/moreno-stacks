"""
kpis_api.py — Endpoints JSON optimizados para consumo asíncrono de KPIs.
"""

from flask import Blueprint, jsonify, request, current_app
from app.core.auth_middleware import requiere_rol
from sqlalchemy import select, func, text
from app.extensions import db

kpis_api_bp = Blueprint("kpis_api", __name__, url_prefix="/api/kpis")


@kpis_api_bp.route("/resumen", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def obtener_resumen_kpis():
    periodo = request.args.get("periodo", "Este mes")
    
    # Construir filtro de fecha
    date_filter_t = ""
    date_filter_cb = ""
    date_filter_cp = ""
    date_filter_c = ""
    
    if periodo == "Este mes":
        date_filter_t = " AND strftime('%Y-%m', t.fecha_evento) = strftime('%Y-%m', 'now')"
        date_filter_cb = " AND strftime('%Y-%m', cb.fecha_vencimiento) = strftime('%Y-%m', 'now')"
        date_filter_cp = " AND strftime('%Y-%m', cp.fecha_pago) = strftime('%Y-%m', 'now')"
        date_filter_c = " AND strftime('%Y-%m', c.fecha_solicitud) = strftime('%Y-%m', 'now')"
    elif periodo == "Mes anterior":
        date_filter_t = " AND strftime('%Y-%m', t.fecha_evento) = strftime('%Y-%m', 'now', '-1 month')"
        date_filter_cb = " AND strftime('%Y-%m', cb.fecha_vencimiento) = strftime('%Y-%m', 'now', '-1 month')"
        date_filter_cp = " AND strftime('%Y-%m', cp.fecha_pago) = strftime('%Y-%m', 'now', '-1 month')"
        date_filter_c = " AND strftime('%Y-%m', c.fecha_solicitud) = strftime('%Y-%m', 'now', '-1 month')"
    elif periodo == "Trimestre":
        date_filter_t = " AND t.fecha_evento >= date('now', '-3 months')"
        date_filter_cb = " AND cb.fecha_vencimiento >= date('now', '-3 months')"
        date_filter_cp = " AND cp.fecha_pago >= date('now', '-3 months')"
        date_filter_c = " AND c.fecha_solicitud >= date('now', '-3 months')"
    elif periodo == "Año":
        date_filter_t = " AND strftime('%Y', t.fecha_evento) = strftime('%Y', 'now')"
        date_filter_cb = " AND strftime('%Y', cb.fecha_vencimiento) = strftime('%Y', 'now')"
        date_filter_cp = " AND strftime('%Y', cp.fecha_pago) = strftime('%Y', 'now')"
        date_filter_c = " AND strftime('%Y', c.fecha_solicitud) = strftime('%Y', 'now')"

    # 1. Total Ventas (Volumen)
    total_ventas = db.session.execute(text(f"SELECT COALESCE(SUM(monto), 0) FROM transacciones t WHERE estado = 'aprobado'{date_filter_t}")).scalar() or 0.0

    # 1b. Total Ventas mes anterior (para delta comparativo)
    ventas_anterior = 0.0
    if periodo in ("Este mes", "Mes anterior"):
        ventas_anterior = db.session.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM transacciones t WHERE estado = 'aprobado'"
            " AND strftime('%Y-%m', t.fecha_evento) = strftime('%Y-%m', 'now', '-1 month')"
        )).scalar() or 0.0

    # 2. Total Cierres
    total_cierres = db.session.execute(text(f"SELECT COUNT(id) FROM transacciones t WHERE estado = 'aprobado'{date_filter_t}")).scalar() or 0

    # 2b. Total Cierres mes anterior
    cierres_anterior = 0
    if periodo in ("Este mes", "Mes anterior"):
        cierres_anterior = db.session.execute(text(
            "SELECT COUNT(id) FROM transacciones t WHERE estado = 'aprobado'"
            " AND strftime('%Y-%m', t.fecha_evento) = strftime('%Y-%m', 'now', '-1 month')"
        )).scalar() or 0

    # 3. Mora Crítica (> 60 días) (la mora crítica suele verse completa sin filtro de periodo, pero aplicamos por coherencia)
    mora_critica = db.session.execute(text(f"""
        SELECT COALESCE(SUM(cb.monto_total - COALESCE((SELECT SUM(monto) FROM pagos p WHERE p.cobro_id = cb.id), 0)), 0)
        FROM cobros cb WHERE cb.fecha_vencimiento <= date('now', '-60 days')
    """)).scalar() or 0.0

    # 4. Incidentes Abiertos
    incidentes_abiertos = db.session.execute(text("SELECT COUNT(id) FROM incidentes WHERE fecha_cierre IS NULL")).scalar() or 0

    # 5. Total Clientes (Cartera)
    total_clientes = db.session.execute(text("SELECT COUNT(id) FROM clientes WHERE activo = 1")).scalar() or 0

    # 6. Total Proyectos (Inventario)
    total_proyectos = db.session.execute(text("SELECT COUNT(id) FROM proyectos")).scalar() or 0

    # 7. Total Inmobiliarias/Contrapartes (Alianzas)
    total_inmobiliarias = db.session.execute(text("SELECT COUNT(id) FROM contrapartes WHERE activo = 1")).scalar() or 0

    # 8. Total Asesores Activos (Fuerza de Ventas)
    total_asesores = db.session.execute(text("SELECT COUNT(id) FROM entidades WHERE activo = 1")).scalar() or 0

    # 9. Comisiones Pagadas (Retención/Gastos)
    # NOTA: comisiones_api.pagar_comision() guarda estado = 'pagado' (masculino,
    # concuerda con "el pago"/"la comision_pago" como registro). Este query
    # comparaba contra 'pagada' (femenino) y nunca coincidia: la KPI marcaba
    # siempre $0 pagado, y la de pendientes nunca bajaba aunque todo estuviera
    # liquidado.
    comisiones_pagadas = db.session.execute(text(f"SELECT COALESCE(SUM(monto), 0) FROM comisiones_pagos cp WHERE estado = 'pagado'{date_filter_cp}")).scalar() or 0.0

    # 10. Comisiones Pendientes (Pasivo) (Sin filtro para ver el total, o filtramos creación? Filtramos fecha_pago no aplica. Mejor sin filtro para pasivo global)
    comisiones_pendientes = db.session.execute(text("SELECT COALESCE(SUM(monto), 0) FROM comisiones_pagos WHERE estado != 'pagado'")).scalar() or 0.0

    # 11. Compras Aprobadas (Operaciones)
    compras_aprobadas = db.session.execute(text(f"SELECT COALESCE(SUM(monto_total), 0) FROM compras c WHERE estado = 'aprobado'{date_filter_c}")).scalar() or 0.0

    # 12. Pagos de Compras Realizados (Flujo de Caja) (asumimos global si no hay fecha en pagos, o podríamos joinear)
    pagos_compras = db.session.execute(text("SELECT COALESCE(SUM(monto_pagado), 0) FROM compras_pagos")).scalar() or 0.0

    # 13. Cierres Fuera de SLA (> 10 días en proceso)
    cierres_sla_incumplidos = db.session.execute(text("SELECT COUNT(id) FROM transacciones WHERE estado = 'en_proceso' AND julianday('now') - julianday(fecha_evento) > sla_dias_meta")).scalar() or 0

    # Load thresholds from kpi_config
    kpi_configs = {}
    try:
        cfg_rows = db.session.execute(text("SELECT kpi_id, meta, umbral_amarillo, umbral_rojo, mayor_es_mejor FROM kpi_config")).mappings().all()
        for row in cfg_rows:
            kpi_configs[row['kpi_id']] = dict(row)
    except Exception:
        pass

    def get_estado(kpi_id, valor_numerico):
        cfg = kpi_configs.get(kpi_id)
        if not cfg:
            return 'en_meta'
        meta = float(cfg.get('meta', 0) or 0)
        ua = float(cfg.get('umbral_amarillo', 0) or 0)  # warning threshold
        ur = float(cfg.get('umbral_rojo', 0) or 0)  # critical threshold
        mayor_es_mejor = bool(cfg.get('mayor_es_mejor', 1))
        v = float(valor_numerico or 0)
        if mayor_es_mejor:
            if v >= meta: return 'en_meta'
            elif v >= ua: return 'alerta'
            else: return 'critico'
        else:
            # Lower is better (e.g., mora, incidentes)
            if v <= meta: return 'en_meta'
            elif v <= ua: return 'alerta'
            else: return 'critico'

    def get_meta_str(kpi_id, default):
        cfg = kpi_configs.get(kpi_id)
        if cfg and cfg.get('meta') is not None:
            return str(cfg.get('meta'))
        return default

    def delta_pct(actual, anterior):
        if anterior is None or anterior <= 0:
            return ("+100%" if actual and actual > 0 else "0")
        cambio = (actual - anterior) / anterior * 100
        return f"{'+' if cambio >= 0 else ''}{cambio:.0f}%"

    def delta_n(actual, anterior):
        if anterior is None:
            return "0"
        cambio = actual - anterior
        return f"{'+' if cambio >= 0 else ''}{cambio}"

    kpis = [
        {
            "id": "volumen_ventas", "categoria": "Comercial", "nombre": "Volumen de Ventas",
            "valor": f"US$ {total_ventas:,.0f}", "meta": get_meta_str("volumen_ventas", "US$ 10M"), "delta": delta_pct(total_ventas, ventas_anterior), "estado": get_estado("volumen_ventas", total_ventas)
        },
        {
            "id": "total_cierres", "categoria": "Transacciones", "nombre": "Cierres Aprobados",
            "valor": str(total_cierres), "meta": get_meta_str("total_cierres", "20"), "delta": delta_n(total_cierres, cierres_anterior), "estado": get_estado("total_cierres", total_cierres)
        },
        {
            "id": "mora_critica", "categoria": "Cobros", "nombre": "Mora Crítica (>60 d)",
            "valor": f"US$ {mora_critica:,.0f}", "meta": get_meta_str("mora_critica", "0"), "delta": "crítico", "estado": get_estado("mora_critica", mora_critica)
        },
        {
            "id": "incidentes_abiertos", "categoria": "Cumplimiento", "nombre": "Incidentes Abiertos",
            "valor": str(incidentes_abiertos), "meta": get_meta_str("incidentes_abiertos", "0"), "delta": "0", "estado": get_estado("incidentes_abiertos", incidentes_abiertos)
        },
        {
            "id": "total_clientes", "categoria": "Cartera", "nombre": "Clientes Activos",
            "valor": str(total_clientes), "meta": get_meta_str("total_clientes", "Crecimiento"), "delta": "Activos", "estado": get_estado("total_clientes", total_clientes)
        },
        {
            "id": "total_proyectos", "categoria": "Inventario", "nombre": "Proyectos Activos",
            "valor": str(total_proyectos), "meta": get_meta_str("total_proyectos", "Mantenimiento"), "delta": "Activos", "estado": get_estado("total_proyectos", total_proyectos)
        },
        {
            "id": "total_inmobiliarias", "categoria": "Alianzas", "nombre": "Contrapartes Activas",
            "valor": str(total_inmobiliarias), "meta": get_meta_str("total_inmobiliarias", "Crecimiento"), "delta": "Activos", "estado": "en_meta"
        },
        {
            "id": "total_asesores", "categoria": "Fuerza de Ventas", "nombre": "Asesores Activos",
            "valor": str(total_asesores), "meta": get_meta_str("total_asesores", "Crecimiento"), "delta": "Activos", "estado": "en_meta"
        },
        {
            "id": "comisiones_pagadas", "categoria": "Comisiones", "nombre": "Comisiones Pagadas",
            "valor": f"US$ {comisiones_pagadas:,.0f}", "meta": get_meta_str("comisiones_pagadas", "Control"), "delta": "-", "estado": "en_meta"
        },
        {
            "id": "comisiones_pendientes", "categoria": "Comisiones", "nombre": "Comisiones Pendientes",
            "valor": f"US$ {comisiones_pendientes:,.0f}", "meta": get_meta_str("comisiones_pendientes", "Control"), "delta": "-", "estado": get_estado("comisiones_pendientes", comisiones_pendientes)
        },
        {
            "id": "compras_aprobadas", "categoria": "Operaciones", "nombre": "Compras Aprobadas",
            "valor": f"US$ {compras_aprobadas:,.0f}", "meta": get_meta_str("compras_aprobadas", "Presupuesto"), "delta": "-", "estado": "en_meta"
        },
        {
            "id": "pagos_compras", "categoria": "Operaciones", "nombre": "Pagos a Proveedores",
            "valor": f"US$ {pagos_compras:,.0f}", "meta": get_meta_str("pagos_compras", "Flujo"), "delta": "-", "estado": "en_meta"
        },
        {
            "id": "cierres_sla", "categoria": "Cumplimiento", "nombre": "Cierres Fuera SLA",
            "valor": str(cierres_sla_incumplidos), "meta": get_meta_str("cierres_sla", "0"), "delta": "crítico", "estado": get_estado("cierres_sla", cierres_sla_incumplidos)
        }
    ]

    return jsonify({"success": True, "kpis": kpis, "periodo": periodo})

@kpis_api_bp.route("/evaluar_leads", methods=["POST"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente General")
def evaluar_leads():
    try:
        from app.core.leads_engine import LeadsEngine
        resultados = LeadsEngine.evaluar_y_recategorizar_asesores()
        return jsonify({"success": True, "resultados": resultados})
    except Exception as e:
        current_app.logger.error("Error evaluando leads: %s", repr(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno al evaluar los leads."}), 500
