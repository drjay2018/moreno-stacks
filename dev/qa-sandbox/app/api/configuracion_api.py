"""
configuracion_api.py — Endpoints API para configuracion de KPIs, respaldos y restauracion de base de datos.
Seguridad: auth en todos los endpoints, cifrado de SMTP password, validacion de backups.
"""

import hashlib
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file, session
from app.core.auth_middleware import requiere_rol, requiere_login
from sqlalchemy import text
from app.extensions import db
from app.config import DB_PATH
from app.core.auditoria import registrar_auditoria

configuracion_api_bp = Blueprint("configuracion_api", __name__, url_prefix="/api/configuracion")


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/kpis", methods=["GET"])
@requiere_rol("Admin")
def listar_kpis_config():
    rows = db.session.execute(
        text("SELECT id, kpi_id, nombre, categoria, unidad, meta, umbral_amarillo, umbral_rojo "
             "FROM kpi_config ORDER BY categoria, nombre")
    ).mappings().all()
    return jsonify({"success": True, "items": [dict(r) for r in rows]})


@configuracion_api_bp.route("/kpis", methods=["POST"])
@requiere_rol("Admin")
def actualizar_kpi_config():
    data = request.get_json() or {}
    kpi_id = data.get("kpi_id")
    meta = data.get("meta")
    umbral_amarillo = data.get("umbral_amarillo")
    umbral_rojo = data.get("umbral_rojo")

    if not kpi_id or meta is None or umbral_amarillo is None or umbral_rojo is None:
        return jsonify({"success": False, "error": "Parametros incompletos para actualizar KPI."}), 400

    db.session.execute(
        text("""
            UPDATE kpi_config
            SET meta = :meta, umbral_amarillo = :ua, umbral_rojo = :ur
            WHERE kpi_id = :kpi_id
        """),
        {"meta": float(meta), "ua": float(umbral_amarillo), "ur": float(umbral_rojo), "kpi_id": kpi_id}
    )
    db.session.commit()

    usuario = session.get("usuario", {})
    registrar_auditoria(usuario.get("id"), usuario.get("username", "system"),
                       "actualizar_kpi", "CONFIG", f"KPI '{kpi_id}' actualizado")
    return jsonify({"success": True, "message": f"Metas del KPI '{kpi_id}' actualizadas correctamente."})


# ---------------------------------------------------------------------------
# Empresa (White-label)
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/empresa", methods=["POST"])
@requiere_rol("Admin")
def actualizar_datos_empresa():
    data = request.get_json() or {}
    campos = ["empresa_nombre", "empresa_gerente", "empresa_telefono", "empresa_correo"]

    for c in campos:
        if c in data:
            db.session.execute(
                text("INSERT INTO app_config (clave, valor) VALUES (:c, :v) "
                     "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"),
                {"c": c, "v": data[c]}
            )

    db.session.commit()
    usuario = session.get("usuario", {})
    registrar_auditoria(usuario.get("id"), usuario.get("username", "system"),
                       "actualizar_empresa", "CONFIG", "Datos de empresa white-label actualizados")
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Backup / Restore
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/backup/descargar", methods=["GET"])
@requiere_rol("Admin")
def descargar_backup():
    if not DB_PATH.exists():
        return jsonify({"success": False, "error": "No se encontro el archivo de base de datos."}), 404

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_backup = f"backup_dlab_{fecha_str}.db"

    temp_backup = DB_PATH.parent / filename_backup
    shutil.copy2(DB_PATH, temp_backup)

    usuario = session.get("usuario", {})
    registrar_auditoria(usuario.get("id"), usuario.get("username", "system"),
                       "descargar_backup", "CONFIG", f"Backup descargado: {filename_backup}")

    return send_file(
        temp_backup,
        as_attachment=True,
        download_name=filename_backup,
        mimetype="application/x-sqlite3"
    )


@configuracion_api_bp.route("/backup/restaurar", methods=["POST"])
@requiere_rol("Admin")
def restaurar_backup():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No se adjunto ningun archivo de respaldo."}), 400

    file = request.files["file"]
    filename = file.filename or ""

    if not (filename.endswith(".db") or filename.endswith(".sqlite")):
        return jsonify({"success": False, "error": "Formato no valido. Debe ser un archivo .db o .sqlite."}), 400

    # Validar magic bytes SQLite
    file.seek(0)
    header = file.read(16)
    file.seek(0)
    if header[:15] != b"SQLite format 3":
        return jsonify({"success": False, "error": "Archivo no es una base SQLite valida."}), 400

    # Validar tamano maximo (100MB para restore)
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > 100 * 1024 * 1024:
        return jsonify({"success": False, "error": "Archivo demasiado grande (maximo 100MB)."}), 400

    if file_size == 0:
        return jsonify({"success": False, "error": "El archivo esta vacio."}), 400

    try:
        # 1. Crear respaldo preventivo (.bak) de la BD actual
        backup_seguridad = DB_PATH.parent / f"dlab_seguridad_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, backup_seguridad)

        # 2. Calcular hash del backup preventivo
        backup_hash = hashlib.sha256(str(backup_seguridad).encode()).hexdigest()[:16] if backup_seguridad.exists() else "N/A"

        # 3. Desconectar la sesion SQLAlchemy activa
        db.session.remove()

        # 4. Sobreescribir con el archivo subido
        file.save(DB_PATH)

        usuario = session.get("usuario", {})
        registrar_auditoria(
            usuario.get("id"), usuario.get("username", "system"),
            "restaurar_backup", "CONFIG",
            f"DB restaurada desde '{filename}'. Backup previo: {backup_seguridad.name} (hash: {backup_hash})"
        )

        return jsonify({
            "success": True,
            "message": "Base de datos restaurada exitosamente. Se creo un respaldo preventivo de seguridad.",
            "backup_previo": backup_seguridad.name
        })
    except Exception as e:
        return jsonify({"success": False, "error": "Error al restaurar base de datos."}), 500


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/auditoria", methods=["GET"])
@requiere_rol("Admin")
def listar_auditoria():
    rows = db.session.execute(
        text("SELECT id, username_snapshot, accion, modulo, detalle, fecha, "
             "ip_address, user_agent, request_path "
             "FROM auditoria ORDER BY fecha DESC LIMIT 50")
    ).mappings().all()
    return jsonify({"success": True, "items": [dict(r) for r in rows]})


# ---------------------------------------------------------------------------
# Matriz de comisiones
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/matriz_comisiones", methods=["GET"])
@requiere_login
def listar_matriz_comisiones():
    rows = db.session.execute(
        text("""
            SELECT c.id, c.nivel_id, cn.nombre as nivel,
                   c.captador_id, cc.nombre as captador,
                   c.gastos_pub_id, cg.nombre as gastos_pub,
                   c.pct_a, c.pct_n, c.pct_ase1, c.pct_ase2,
                   c.pct_proyecto, c.pct_admin, c.pct_extra, c.pct_pub_gfm
            FROM config_matriz_comisiones c
            JOIN cat_niveles cn ON c.nivel_id = cn.id
            JOIN cat_captadores cc ON c.captador_id = cc.id
            JOIN cat_gastos_pub cg ON c.gastos_pub_id = cg.id
            ORDER BY c.id
        """)
    ).mappings().all()
    return jsonify({"success": True, "items": [dict(r) for r in rows]})


@configuracion_api_bp.route("/matriz_comisiones", methods=["POST"])
@requiere_rol("Admin")
def crear_matriz_comisiones():
    data = request.get_json() or {}
    nivel_id = data.get("nivel_id")
    captador_id = data.get("captador_id")
    gastos_pub_id = data.get("gastos_pub_id")

    if not nivel_id or not captador_id or not gastos_pub_id:
        return jsonify({"success": False, "error": "Todos los catalogos son requeridos."}), 400

    existe = db.session.execute(
        text("SELECT id FROM config_matriz_comisiones WHERE nivel_id=:n AND captador_id=:c AND gastos_pub_id=:g"),
        {"n": nivel_id, "c": captador_id, "g": gastos_pub_id}
    ).scalar()

    if existe:
        return jsonify({"success": False, "error": "Esta regla ya existe en la matriz."}), 400

    db.session.execute(
        text("""
            INSERT INTO config_matriz_comisiones (nivel_id, captador_id, gastos_pub_id, pct_a, pct_n, pct_ase1, pct_ase2, pct_proyecto, pct_admin, pct_extra, pct_pub_gfm)
            VALUES (:n, :c, :g, 0, 0, 0, 0, 0, 0, 0, 0)
        """),
        {"n": nivel_id, "c": captador_id, "g": gastos_pub_id}
    )
    db.session.commit()

    usuario = session.get("usuario", {})
    registrar_auditoria(usuario.get("id"), usuario.get("username", "system"),
                       "crear_regla_comision", "CONFIG", "Nueva regla de comision anadida")
    return jsonify({"success": True, "message": "Regla anadida con exito. Configura los porcentajes ahora."})


@configuracion_api_bp.route("/matriz_comisiones/<int:regla_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_matriz_comisiones(regla_id):
    from decimal import Decimal, ROUND_HALF_UP
    data = request.get_json() or {}

    pcts = {
        "pct_a": data.get("pct_a", 0.0),
        "pct_n": data.get("pct_n", 0.0),
        "pct_ase1": data.get("pct_ase1", 0.0),
        "pct_ase2": data.get("pct_ase2", 0.0),
        "pct_proyecto": data.get("pct_proyecto", 0.0),
        "pct_admin": data.get("pct_admin", 0.0),
        "pct_extra": data.get("pct_extra", 0.0),
        "pct_pub_gfm": data.get("pct_pub_gfm", 0.0)
    }

    total = sum(float(v) for v in pcts.values())
    total_decimal = Decimal(str(total)).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)

    if total_decimal != Decimal('1.00'):
        return jsonify({"success": False, "error": f"Error de Integridad: La sumatoria de comisiones es {total_decimal}, debe ser exactamente 1.00 (100%)."}), 400

    db.session.execute(
        text("""
            UPDATE config_matriz_comisiones
            SET pct_a = :pct_a, pct_n = :pct_n, pct_ase1 = :pct_ase1, pct_ase2 = :pct_ase2,
                pct_proyecto = :pct_proyecto, pct_admin = :pct_admin, pct_extra = :pct_extra, pct_pub_gfm = :pct_pub_gfm
            WHERE id = :id
        """),
        {**pcts, "id": regla_id}
    )
    db.session.commit()
    return jsonify({"success": True, "message": "Regla de comision actualizada correctamente."})


# ---------------------------------------------------------------------------
# Logs recientes
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/logs/recientes", methods=["GET"])
@requiere_rol("Admin")
def logs_recientes():
    import os
    from datetime import date
    from app.core.logger import get_log_path

    logs_dir = get_log_path()
    log_filename = f'app_{date.today().strftime("%Y-%m-%d")}.log'
    log_file = os.path.join(logs_dir, log_filename)

    if not os.path.isfile(log_file):
        return jsonify({
            "success": True,
            "lines": [],
            "log_file": log_file,
            "warning": "El archivo de log del dia aun no existe o no se ha generado."
        })

    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        last_200 = [line.rstrip('\n') for line in all_lines[-200:]]

        return jsonify({
            "success": True,
            "lines": last_200,
            "log_file": log_file,
            "total_lines": len(all_lines)
        })
    except Exception:
        return jsonify({
            "success": False,
            "error": "Error al leer el archivo de log."
        }), 500


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/smtp", methods=["GET"])
@requiere_rol("Admin")
def obtener_smtp_config():
    rows = db.session.execute(
        text("SELECT clave, valor FROM app_config "
             "WHERE clave LIKE 'smtp_%' OR clave = 'email_notificaciones_receptor'")
    ).mappings().all()
    data = {row["clave"]: row["valor"] for row in rows}

    # Descifrar password SMTP para verificar si existe
    if "smtp_password" in data and data["smtp_password"]:
        data["smtp_password_is_set"] = True
        data.pop("smtp_password", None)
    else:
        data["smtp_password_is_set"] = False
        data.pop("smtp_password", None)

    return jsonify({"success": True, "config": data})


@configuracion_api_bp.route("/smtp", methods=["POST"])
@requiere_rol("Admin")
def actualizar_smtp_config():
    from app.core.crypto import ensure_encrypted

    data = request.get_json() or {}
    campos = ["smtp_server", "smtp_port", "smtp_user", "smtp_password", "email_notificaciones_receptor"]

    for c in campos:
        if c in data:
            if c == "smtp_password" and data[c] == "":
                continue
            valor = data[c]
            # Cifrar password SMTP antes de guardar
            if c == "smtp_password":
                valor = ensure_encrypted(valor)
            db.session.execute(
                text("INSERT INTO app_config (clave, valor) VALUES (:c, :v) "
                     "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"),
                {"c": c, "v": valor}
            )

    db.session.commit()
    usuario = session.get("usuario", {})
    registrar_auditoria(usuario.get("id"), usuario.get("username", "system"),
                       "actualizar_smtp", "CONFIGURACION", "Credenciales SMTP actualizadas")
    return jsonify({"success": True, "message": "Configuracion SMTP actualizada con exito."})


@configuracion_api_bp.route("/smtp/probar", methods=["POST"])
@requiere_rol("Admin")
def probar_smtp_config():
    from app.core.crypto import ensure_decrypted
    try:
        cfg = request.json or {}
        if not cfg.get("smtp_user"):
            rows = db.session.execute(
                text("SELECT clave, valor FROM app_config "
                     "WHERE clave LIKE 'smtp_%' OR clave = 'email_notificaciones_receptor'")
            ).mappings().all()
            cfg = {row["clave"]: row["valor"] for row in rows}

        # Descifrar password SMTP para la conexion
        smtp_password = cfg.get("smtp_password", "")
        if smtp_password:
            smtp_password = ensure_decrypted(smtp_password)

        import smtplib
        from email.mime.text import MIMEText

        server = smtplib.SMTP(cfg.get("smtp_server", "smtp.gmail.com"), int(cfg.get("smtp_port", 587)))
        server.starttls()
        server.login(cfg.get("smtp_user", ""), smtp_password)

        msg = MIMEText("Esta es una prueba de configuracion SMTP desde tu CRM DLAB.")
        msg["Subject"] = "DLAB CRM - Prueba de Conexion SMTP"
        msg["From"] = cfg.get("smtp_user", "")
        receptor = cfg.get("email_notificaciones_receptor", "")
        if not receptor:
            receptor = cfg.get("smtp_user", "")
        msg["To"] = receptor

        server.send_message(msg)
        server.quit()

        return jsonify({"success": True, "message": "Correo de prueba enviado con exito."})
    except Exception as e:
        return jsonify({"success": False, "error": "Error SMTP: Verifica las credenciales."}), 500


# ---------------------------------------------------------------------------
# VERSION Y UPDATES
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/version", methods=["GET"])
@requiere_login
def obtener_version():
    """Retorna la version actual de la aplicacion."""
    from app.version import get_version_dict
    import platform
    info = get_version_dict()
    info["os"] = f"{platform.system()} {platform.release()}"
    info["python"] = platform.python_version()
    return jsonify({"success": True, "version": info})


@configuracion_api_bp.route("/update/check", methods=["GET"])
@requiere_rol("Admin")
def check_update():
    """Verifica si hay una nueva version disponible en GitHub Releases."""
    from app.core.updater import check_for_updates
    result = check_for_updates()

    if result.get("error") is not None:
        # No se pudo consultar el release (repo privado, sin conexion, etc.)
        return jsonify({
            "success": False,
            "disponible": False,
            "mensaje": result.get("mensaje", "No se pudieron comprobar las actualizaciones."),
        }), 502

    return jsonify({"success": True, **result})


@configuracion_api_bp.route("/update/status", methods=["GET"])
@requiere_rol("Admin")
def update_status():
    """Estado actual del sistema de actualizacion."""
    from app.core.updater import get_update_status
    return jsonify({"success": True, "status": get_update_status()})


@configuracion_api_bp.route("/update/apply", methods=["POST"])
@requiere_rol("Admin")
def apply_update():
    """Descarga y aplica una actualizacion sin reinstalar (updater auxiliar)."""
    from app.core.updater import check_for_updates, download_and_apply, launch_updater, prepare_update
    import os
    import threading
    import time

    update_info = check_for_updates()
    if update_info.get("error") is not None:
        # No se pudo consultar el release: responder claro sin bloquear la app
        return jsonify({
            "success": False,
            "disponible": False,
            "error": "No se pudo preparar la actualizacion.",
            "mensaje": update_info.get("mensaje", "No se pudieron comprobar las actualizaciones."),
        }), 502
    if not update_info.get("available"):
        return jsonify({"success": False, "disponible": False, "error": "No hay actualizaciones disponibles."}), 400

    # Aplicar en background: descargar, lanzar updater.exe y cerrar la app
    def _run():
        result = prepare_update(update_info)
        if not result.get("success"):
            return

        launched = launch_updater(result["zip_path"], result.get("checksum"))
        if not launched:
            # Entorno sin updater.exe (dev/instalacion antigua): aplicar en sitio
            download_and_apply(update_info)
            return

        time.sleep(3)  # garantiza que la respuesta HTTP llegue al cliente
        os._exit(0)    # cierra la app para que updater.exe reemplace los archivos

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return jsonify({
        "success": True,
        "message": "Actualizacion en progreso. La app se cerrara y reiniciara automaticamente.",
    })


# ---------------------------------------------------------------------------
# SOPORTE Y DIAGNOSTICOS
# ---------------------------------------------------------------------------

@configuracion_api_bp.route("/diagnostics", methods=["GET"])
@requiere_rol("Admin")
def diagnostics():
    """Retorna diagnosticos completos del sistema."""
    from app.core.diagnostics import get_system_info, get_db_info
    return jsonify({
        "success": True,
        "system": get_system_info(),
        "database": get_db_info(),
    })


@configuracion_api_bp.route("/diagnostics/report", methods=["POST"])
@requiere_rol("Admin")
def generate_report():
    """Genera un reporte de soporte para copiar y pegar en WhatsApp/Telegram."""
    from app.core.diagnostics import generate_support_report
    data = request.get_json() or {}
    description = data.get("description", "Problema no especificado.")
    include_logs = data.get("include_logs", True)
    include_db = data.get("include_db_info", True)

    report = generate_support_report(description, include_logs, include_db)
    return jsonify({"success": True, "report": report})


@configuracion_api_bp.route("/instalaciones", methods=["GET"])
@requiere_rol("Admin")
def listar_instalaciones():
    """Retorna informacion de las instalaciones registradas."""
    try:
        rows = db.session.execute(
            text("SELECT clave, valor FROM app_config "
                 "WHERE clave IN ('client_id', 'app_version', 'app_build', "
                 "'last_startup', 'os_info')")
        ).mappings().all()
        data = {row["clave"]: row["valor"] for row in rows}
        return jsonify({"success": True, "instalacion": data})
    except Exception:
        return jsonify({"success": False, "error": "Error obteniendo info de instalacion."}), 500
