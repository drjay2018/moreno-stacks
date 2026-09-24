import threading
import time
import datetime
import os
import json
import logging

from app.core.crypto import ensure_decrypted

logger = logging.getLogger(__name__)

def _run_scheduler(app):
    with app.app_context():
        dias_intervalo = 15
        estado_file = os.path.join(app.root_path, '..', 'data', 'scheduler_state.json')
        
        while True:
            ahora = datetime.datetime.now()

            ultima_ejecucion = None
            estado = {}
            if os.path.exists(estado_file):
                try:
                    with open(estado_file, 'r') as f:
                        estado = json.load(f)
                        ultima_ejecucion = datetime.datetime.fromisoformat(estado['ultima_exportacion'])
                except:
                    pass
            
            ejecutar = False
            if ultima_ejecucion is None:
                ejecutar = True
            else:
                diferencia = ahora - ultima_ejecucion
                if diferencia.days >= dias_intervalo:
                    ejecutar = True
            
            if ejecutar:
                try:
                    with app.test_client() as client:
                        with client.session_transaction() as sess:
                            sess['usuario'] = {
                                'id': 1, 'username': 'scheduler', 'rol': 'Admin',
                                'entidad_id': None, 'acepto_politicas': True,
                                'debo_cambiar_password': False
                            }

                        client.post('/api/exportaciones/generar-bi')
                        client.post('/api/exportaciones/generar-historico-operativo')
                        client.post('/api/exportaciones/generar-agente')

                    estado['ultima_exportacion'] = ahora.isoformat()
                    os.makedirs(os.path.dirname(estado_file), exist_ok=True)
                    with open(estado_file, 'w') as f:
                        json.dump(estado, f)
                        
                    print(f"[{ahora.isoformat()}] Scheduler: Exportaciones automaticas generadas (Regla 15 dias).")
                except Exception as e:
                    print(f"Scheduler Error: {e}")
                    
            
            # Lógica de correos diarios
            ultima_alerta_diaria = estado.get('ultima_alerta_diaria')
            ejecutar_alertas = False
            if not ultima_alerta_diaria:
                ejecutar_alertas = True
            else:
                ultima_fecha_alertas = datetime.datetime.fromisoformat(ultima_alerta_diaria).date()
                if ahora.date() > ultima_fecha_alertas and ahora.hour >= 8: # A partir de las 8am
                    ejecutar_alertas = True
                    
            if ejecutar_alertas:
                try:
                    with app.test_client() as client:
                        with client.session_transaction() as sess:
                            sess['usuario_id'] = 1
                            sess['rol'] = 'Admin'
                        # Create an endpoint for triggering alerts or put the logic here
                        # We will query db directly
                        from sqlalchemy import text
                        from app.extensions import db
                        
                        rows = db.session.execute(text("SELECT clave, valor FROM app_config WHERE clave LIKE 'smtp_%' OR clave = 'email_notificaciones_receptor'")).mappings().all()
                        cfg = {row["clave"]: row["valor"] for row in rows}
                        
                        if cfg.get("smtp_user") and cfg.get("smtp_password"):
                                limite_5_dias = (ahora + datetime.timedelta(days=5)).date().isoformat()
                                hoy_str = ahora.date().isoformat()
                                
                                # Cartera Vencida
                                q_vencidas = db.session.execute(text("""
                                    SELECT cb.id AS cobro_id, cb.monto_total, cb.fecha_vencimiento, cb.concepto,
                                           COALESCE(cl.nombre || ' ' || cl.apellido, 'Sin cliente') AS cliente
                                    FROM cobros cb
                                    LEFT JOIN transacciones t ON cb.transaccion_id = t.id
                                    LEFT JOIN clientes cl ON t.cliente_id = cl.id
                                    WHERE cb.fecha_vencimiento < :hoy
                                      AND cb.monto_total > COALESCE((SELECT SUM(p.monto) FROM pagos p WHERE p.cobro_id = cb.id), 0)
                                    ORDER BY cb.fecha_vencimiento ASC
                                """), {"hoy": hoy_str}).mappings().all()

                                # Proximas a 5 dias
                                q_cuotas = db.session.execute(text("""
                                    SELECT cb.id AS cobro_id, cb.monto_total, cb.fecha_vencimiento, cb.concepto,
                                           COALESCE(cl.nombre || ' ' || cl.apellido, 'Sin cliente') AS cliente
                                    FROM cobros cb
                                    LEFT JOIN transacciones t ON cb.transaccion_id = t.id
                                    LEFT JOIN clientes cl ON t.cliente_id = cl.id
                                    WHERE cb.fecha_vencimiento = :limite
                                      AND cb.monto_total > COALESCE((SELECT SUM(p.monto) FROM pagos p WHERE p.cobro_id = cb.id), 0)
                                """), {"limite": limite_5_dias}).mappings().all()
                                
                                if q_cuotas or q_vencidas:
                                    import smtplib
                                    from email.mime.text import MIMEText
                                    from email.mime.multipart import MIMEMultipart
                                    
                                    server = smtplib.SMTP(cfg.get("smtp_server", "smtp.gmail.com"), int(cfg.get("smtp_port", 587)))
                                    server.starttls()
                                    server.login(cfg.get("smtp_user", ""), ensure_decrypted(cfg.get("smtp_password", "")))
                                    
                                    msg = MIMEMultipart()
                                    msg["Subject"] = f"DLAB CRM - Alertas de Cobros ({len(q_vencidas)} vencidas, {len(q_cuotas)} proximas)"
                                    msg["From"] = cfg.get("smtp_user", "")
                                    receptor = cfg.get("email_notificaciones_receptor", "")
                                    if not receptor: receptor = cfg.get("smtp_user", "")
                                    msg["To"] = receptor
                                    
                                    html = f"""
                                    <div style="font-family: sans-serif; color: #334155; max-width: 800px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                                        <div style="background-color: #0f172a; padding: 20px; text-align: center;">
                                            <h2 style="color: #ffffff; margin: 0;">Resumen Diario de Alertas - DLAB CRM</h2>
                                        </div>
                                        <div style="padding: 20px;">
                                            <p style="font-size: 14px; line-height: 1.6;">Hola,</p>
                                            <p style="font-size: 14px; line-height: 1.6;">Este es tu reporte automatizado de seguimiento de cartera. El propósito de este correo es mantener a la gerencia y a los asesores informados sobre el estatus de los cobros para garantizar un flujo de caja saludable en la empresa.</p>
                                            <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 10px 15px; margin: 15px 0;">
                                                <p style="margin: 0 0 5px 0; font-weight: bold; font-size: 13px;">¿Qué debes hacer?</p>
                                                <ul style="margin: 0; padding-left: 20px; font-size: 13px;">
                                                    <li style="margin-bottom: 3px;">Contactar urgentemente a los clientes en la sección <b>Cartera Vencida</b> para gestionar su regularización.</li>
                                                    <li>Contactar a los clientes de las <b>Cuotas Próximas (5 días)</b> para enviar un recordatorio de pago preventivo.</li>
                                                </ul>
                                            </div>
                                            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 25px 0;">
"""
                                    
                                    html += f"<h3>⚠️ Cartera Vencida ({len(q_vencidas)} cuotas)</h3>"
                                    if q_vencidas:
                                        html += "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; font-family: sans-serif; font-size: 12px; width: 100%;'>"
                                        html += "<tr style='background-color: #f1f5f9;'><th>Cliente</th><th>Concepto</th><th>Vencimiento</th><th>Monto Total</th></tr>"
                                        for v in q_vencidas:
                                            html += f"<tr><td>{v['cliente']}</td><td>{v['concepto']}</td><td style='color: #e11d48; font-weight: bold;'>{v['fecha_vencimiento']}</td><td>${v['monto_total']:,.2f}</td></tr>"
                                        html += "</table>"
                                    else:
                                        html += "<p>No hay cuotas vencidas.</p>"

                                    html += f"<h3>🔔 Próximas a vencer en 5 días ({len(q_cuotas)} cuotas)</h3>"
                                    if q_cuotas:
                                        html += "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; font-family: sans-serif; font-size: 12px; width: 100%;'>"
                                        html += "<tr style='background-color: #f1f5f9;'><th>Cliente</th><th>Concepto</th><th>Vencimiento</th><th>Monto Total</th></tr>"
                                        for p in q_cuotas:
                                            html += f"<tr><td>{p['cliente']}</td><td>{p['concepto']}</td><td style='color: #d97706; font-weight: bold;'>{p['fecha_vencimiento']}</td><td>${p['monto_total']:,.2f}</td></tr>"
                                        html += "</table>"
                                    else:
                                        html += "<p>No hay cuotas programadas para esa fecha.</p>"
                                    html += "</div></div>"
                                    
                                    msg.attach(MIMEText(html, "html"))
                                    server.send_message(msg)
                                    server.quit()
                                    print(f"[{ahora.isoformat()}] Alertas diarias enviadas por correo.")

                    estado['ultima_alerta_diaria'] = ahora.isoformat()
                    os.makedirs(os.path.dirname(estado_file), exist_ok=True)
                    with open(estado_file, 'w') as f:
                        json.dump(estado, f)
                except Exception as e:
                    logger.error(f"Error enviando alertas diarias: {e}", exc_info=True)
            
            time.sleep(3600)

def init_scheduler(app):
    t = threading.Thread(target=_run_scheduler, args=(app,))
    t.daemon = True
    t.start()
