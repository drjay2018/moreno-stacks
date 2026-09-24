"""
alertas_api.py — Motor de Alertas y Semáforo del Dashboard.

Reglas de Rendimiento:
- Todo filtrado de fechas ocurre en la capa SQL (no en Python/memoria).
- Solo se seleccionan las columnas estrictamente necesarias.
- Resultados limitados con LIMIT directamente en la consulta.
"""

from datetime import date, timedelta
from flask import Blueprint, jsonify
from app.core.auth_middleware import requiere_rol
from sqlalchemy import text
from app.extensions import db

alertas_api_bp = Blueprint("alertas_api", __name__, url_prefix="/api/alertas")


@alertas_api_bp.route("/dashboard", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def alertas_dashboard():
    hoy = date.today()
    limite_advertencia = hoy + timedelta(days=7)
    limite_acuerdos = hoy + timedelta(days=30)
    
    # CRITICO: Cobros > 60 días (escalar a CEO)
    q_cobros_60 = db.session.execute(text("""
        SELECT cb.id AS cobro_id, cb.monto_total, cb.fecha_vencimiento, 
               CAST(julianday('now') - julianday(cb.fecha_vencimiento) AS INTEGER) AS dias_atraso
        FROM cobros cb
        WHERE cb.fecha_vencimiento <= date('now', '-60 days')
          AND cb.monto_total > COALESCE((SELECT SUM(p.monto) FROM pagos p WHERE p.cobro_id = cb.id), 0)
        LIMIT 5
    """)).mappings().all()

    # CRITICO: Cuotas vencidas normales
    q_critico_cuotas = db.session.execute(text("""
        SELECT cb.id AS cobro_id, cb.monto_total, cb.fecha_vencimiento, cb.concepto,
               CAST(julianday('now') - julianday(cb.fecha_vencimiento) AS INTEGER) AS dias_atraso,
               COALESCE(cl.nombre || ' ' || cl.apellido, 'Sin cliente') AS cliente,
               COALESCE(t.codigo, '') AS codigo_transaccion,
               COALESCE(t.id, 0) AS transaccion_id
        FROM cobros cb
        LEFT JOIN transacciones t ON cb.transaccion_id = t.id
        LEFT JOIN clientes cl ON t.cliente_id = cl.id
        WHERE cb.fecha_vencimiento < :hoy AND cb.fecha_vencimiento > date('now', '-60 days')
          AND cb.monto_total > COALESCE((SELECT SUM(p.monto) FROM pagos p WHERE p.cobro_id = cb.id), 0)
        LIMIT 5
    """), {"hoy": hoy.isoformat()}).mappings().all()

    # ADVERTENCIA: Cuotas próximas a vencer
    q_advertencia_cuotas = db.session.execute(text("""
        SELECT cb.id AS cobro_id, cb.monto_total, cb.fecha_vencimiento, cb.concepto,
               CAST(julianday(cb.fecha_vencimiento) - julianday('now') AS INTEGER) AS dias_para_vencer,
               COALESCE(cl.nombre || ' ' || cl.apellido, 'Sin cliente') AS cliente,
               COALESCE(t.codigo, '') AS codigo_transaccion,
               COALESCE(t.id, 0) AS transaccion_id
        FROM cobros cb
        LEFT JOIN transacciones t ON cb.transaccion_id = t.id
        LEFT JOIN clientes cl ON t.cliente_id = cl.id
        WHERE cb.fecha_vencimiento BETWEEN :hoy AND :limite
          AND cb.monto_total > COALESCE((SELECT SUM(p.monto) FROM pagos p WHERE p.cobro_id = cb.id), 0)
        LIMIT 5
    """), {"hoy": hoy.isoformat(), "limite": limite_advertencia.isoformat()}).mappings().all()

    # CRITICO: Comisiones de asesores vencidas
    q_comisiones_vencidas = db.session.execute(text("""
        SELECT id, entidad_id, monto, fecha_maxima_pago 
        FROM comisiones_pagos 
        WHERE fecha_maxima_pago < :hoy AND estado != 'pagado'
        LIMIT 5
    """), {"hoy": hoy.isoformat()}).mappings().all()

    # CRITICO: Compromisos vencidos
    q_compromisos_vencidos = db.session.execute(text("""
        SELECT cp.id, cp.categoria, cp.valor_pactado_pct,
               CAST(julianday('now') - julianday(cp.fecha_vencimiento) AS INTEGER) AS dias_atraso,
               COALESCE(co.nombre, 'Sin contraparte') AS contraparte,
               COALESCE(p.nombre, 'Sin proyecto') AS proyecto
        FROM compromisos cp
        LEFT JOIN contrapartes co ON cp.contraparte_id = co.id
        LEFT JOIN proyectos p ON cp.proyecto_id = p.id
        WHERE cp.fecha_vencimiento < :hoy
        ORDER BY cp.fecha_vencimiento ASC
        LIMIT 5
    """), {"hoy": hoy.isoformat()}).mappings().all()

    # ADVERTENCIA: Acuerdos por vencer (<= 30 días) o vencidos
    q_acuerdos = db.session.execute(text("""
        SELECT id, categoria, fecha_vencimiento,
               CAST(julianday(fecha_vencimiento) - julianday('now') AS INTEGER) AS dias
        FROM compromisos 
        WHERE fecha_vencimiento <= :limite_acuerdos
        ORDER BY fecha_vencimiento ASC
        LIMIT 5
    """), {"limite_acuerdos": limite_acuerdos.isoformat()}).mappings().all()

    # CRITICO: Asesores con AEI vencida
    q_aei = db.session.execute(text("""
        SELECT id, nombre, apellido, fecha_vencimiento_aei 
        FROM entidades 
        WHERE activo=1 AND fecha_vencimiento_aei < :hoy
        LIMIT 5
    """), {"hoy": hoy.isoformat()}).mappings().all()

    # CRITICO: Incidentes abiertos Nivel 3 y 4
    q_incidentes = db.session.execute(text("""
        SELECT id, tipo, nivel, fecha_reporte 
        FROM incidentes 
        WHERE fecha_cierre IS NULL AND nivel IN (3, 4)
        LIMIT 5
    """)).mappings().all()

    # ADVERTENCIA: Compras fuera de SLA (> 2 días)
    q_compras_sla = db.session.execute(text("""
        SELECT id, concepto, fecha_solicitud 
        FROM compras 
        WHERE estado='pendiente' AND aprobado_ceo=0 AND julianday('now') - julianday(fecha_solicitud) > 2
        LIMIT 5
    """)).mappings().all()

    # ADVERTENCIA: Cierres fuera de SLA (> 10 días)
    q_cierres_sla = db.session.execute(text("""
        SELECT id, codigo, fecha_evento 
        FROM transacciones 
        WHERE estado='en_proceso' AND julianday('now') - julianday(fecha_evento) > sla_dias_meta
        LIMIT 5
    """)).mappings().all()

    # INFORMATIVO: métricas del mes
    from datetime import datetime
    mes_inicio = date.today().replace(day=1).isoformat()

    cierres_mes = db.session.execute(text("""
        SELECT COUNT(id) FROM transacciones
        WHERE estado NOT IN ('Caida','Perdida')
          AND fecha_evento >= :inicio
    """), {"inicio": mes_inicio}).scalar() or 0

    volumen_mes = db.session.execute(text("""
        SELECT COALESCE(SUM(monto), 0) FROM transacciones
        WHERE estado NOT IN ('Caida','Perdida')
          AND fecha_evento >= :inicio
    """), {"inicio": mes_inicio}).scalar() or 0

    clientes_mes = db.session.execute(text("""
        SELECT COUNT(id) FROM clientes WHERE fecha_captacion >= :inicio
    """), {"inicio": mes_inicio}).scalar() or 0

    def _row(r):
        return {k: (str(v) if hasattr(v, 'isoformat') else v) for k, v in r.items()}

    return jsonify({
        "success": True,
        "fecha_consulta": hoy.isoformat(),
        "critico": {
            "cobros_mas_60_dias": [_row(r) for r in q_cobros_60],
            "cuotas_vencidas":    [_row(r) for r in q_critico_cuotas],
            "compromisos_vencidos": [_row(r) for r in q_compromisos_vencidos],
            "comisiones_vencidas": [_row(r) for r in q_comisiones_vencidas],
            "aei_vencida":        [_row(r) for r in q_aei],
            "incidentes_n3_n4":   [_row(r) for r in q_incidentes]
        },
        "advertencia": {
            "cuotas_proximas":    [_row(r) for r in q_advertencia_cuotas],
            "acuerdos_por_vencer": [_row(r) for r in q_acuerdos],
            "compras_fuera_sla": [_row(r) for r in q_compras_sla],
            "cierres_fuera_sla": [_row(r) for r in q_cierres_sla]
        },
        "informativo": {
            "cierres_este_mes":      cierres_mes,
            "volumen_ventas_mes":    float(volumen_mes),
            "clientes_captados_mes": clientes_mes
        }
    })

