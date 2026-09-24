"""
clarodom_api.py — Endpoint API para gestionar la integracion con ClaroDom.

Endpoints:
    GET  /api/clarodom/status   — Estado de la conexion y configuracion
    GET  /api/clarodom/config   — Obtener configuracion actual (tokens enmascarados)
    POST /api/clarodom/config   — Guardar configuracion
    POST /api/clarodom/test     — Probar conexion y autenticacion
"""

import urllib.parse
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy import text

from app.extensions import db
from app.core.auditoria import registrar_auditoria
from app.core.auth_middleware import requiere_rol
from app.core.logger import log_error

# Valores permitidos para el formato del header Authorization (ver clarodom_client.py)
AUTH_SCHEMES_VALIDOS = ("bearer", "token", "raw")

clarodom_api_bp = Blueprint("clarodom_api", __name__, url_prefix="/api/clarodom")


@clarodom_api_bp.route("/status", methods=["GET"])
@requiere_rol("Admin")
def get_status():
    """Estado de la integracion ClaroDom."""
    try:
        config_rows = db.session.execute(
            text("SELECT clave, valor FROM app_config WHERE clave LIKE 'clarodom_%'")
        ).mappings().all()

        has_config = len(config_rows) > 0

        # Ultimo test/guardado desde auditoria
        last_events = {}
        try:
            rows = db.session.execute(
                text(
                    "SELECT accion, MAX(fecha) as ultima "
                    "FROM auditoria WHERE modulo = 'CLARODOM' "
                    "GROUP BY accion"
                )
            ).fetchall()
            for r in rows:
                last_events[r[0]] = str(r[1])
        except Exception:
            pass

        config_keys_present = [r["clave"] for r in config_rows]
        # No exponer el token en el estado
        safe_keys = [k for k in config_keys_present if "token" not in k and "secret" not in k]

        # El resultado real de conectividad/auth lo guarda el endpoint /test
        # (ultima ejecucion) en app_config bajo el prefijo clarodom_. No basta
        # con "hay configuracion guardada" para pintar el semaforo en verde:
        # eso solo indica que se guardo una base_url, no que la conexion
        # funcione. "connected" solo es true si el ultimo /test fue exitoso.
        from app.core.alterestate_client import load_provider_config_from_db
        cd_config = load_provider_config_from_db("clarodom")
        last_test_ok = cd_config.get("last_test_ok") == "1"
        last_test_at = cd_config.get("last_test_at")
        connected = has_config and last_test_ok

        return jsonify({
            "success": True,
            "has_config": has_config,
            "connected": connected,
            "last_test_ok": last_test_ok,
            "last_test_at": last_test_at,
            "config_keys": safe_keys,
            "last_events": last_events,
        })

    except Exception as e:
        log_error("[CLARODOM_API] Error en status", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@clarodom_api_bp.route("/config", methods=["GET"])
@requiere_rol("Admin")
def get_config():
    """Obtiene la configuracion de ClaroDom (sin exponer tokens)."""
    try:
        from app.core.alterestate_client import load_provider_config_from_db

        config = load_provider_config_from_db("clarodom")

        # Enmascarar tokens y secrets
        safe_config = {}
        for k, v in config.items():
            if "token" in k or "secret" in k:
                safe_config[k] = f"{'*' * 8}{v[-4:]}" if v and len(v) > 4 else "(no configurado)"
            else:
                safe_config[k] = v

        return jsonify({"success": True, "config": safe_config})

    except Exception as e:
        log_error("[CLARODOM_API] Error obteniendo config", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@clarodom_api_bp.route("/config", methods=["POST"])
@requiere_rol("Admin")
def save_config():
    """Guarda la configuracion de ClaroDom."""
    try:
        data = request.get_json() or {}

        required_fields = ["base_url"]
        for field in required_fields:
            if not data.get(field):
                return jsonify({"success": False, "error": f"Campo requerido: {field}"}), 400

        # Validar que base_url tenga un esquema http(s) valido y un host
        parsed_url = urllib.parse.urlparse(data.get("base_url", ""))
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            return jsonify({
                "success": False,
                "error": "base_url invalida: debe incluir esquema http:// o https:// y un host valido",
            }), 400

        # Validar auth_scheme (si se envia) contra los valores soportados por ClaroDomClient
        auth_scheme = data.get("auth_scheme")
        if auth_scheme is not None and auth_scheme not in AUTH_SCHEMES_VALIDOS:
            return jsonify({
                "success": False,
                "error": f"auth_scheme invalido. Valores permitidos: {', '.join(AUTH_SCHEMES_VALIDOS)}",
            }), 400

        from app.core.alterestate_client import save_provider_config_to_db

        save_provider_config_to_db(data, "clarodom")

        usuario = session.get("usuario", {})
        registrar_auditoria(usuario.get("id"), usuario.get("username", "system"),
                           "configurar_clarodom", "CLARODOM",
                           "Configuracion de ClaroDom actualizada")

        return jsonify({"success": True, "message": "Configuracion guardada correctamente."})

    except Exception as e:
        log_error("[CLARODOM_API] Error guardando config", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@clarodom_api_bp.route("/test", methods=["POST"])
@requiere_rol("Admin")
def test_connection():
    """Prueba la conexion y autenticacion con ClaroDom."""
    try:
        from app.core.alterestate_client import load_provider_config_from_db, save_provider_config_to_db
        from app.core.clarodom_client import ClaroDomClient

        config = load_provider_config_from_db("clarodom")
        if not config.get("base_url"):
            return jsonify({"success": False, "error": "No hay configuracion de base_url"}), 400

        # Si el frontend envia un token nuevo en el POST, usarlo
        data = request.get_json() or {}
        if data.get("api_token"):
            config["api_token"] = data["api_token"]

        client = ClaroDomClient(config)

        conn_result = client.test_connection()
        auth_result = client.test_auth()

        test_ok = bool(conn_result.get("connected")) and bool(auth_result.get("authenticated"))
        # Persistir el resultado para que /status pueda reflejar el estado
        # real de la conexion (no solo si hay configuracion guardada).
        try:
            save_provider_config_to_db({
                "last_test_ok": "1" if test_ok else "0",
                "last_test_at": datetime.utcnow().isoformat(),
            }, "clarodom")
        except Exception:
            log_error("[CLARODOM_API] Error guardando resultado de test", exc_info=True)

        usuario = session.get("usuario", {})
        registrar_auditoria(usuario.get("id"), usuario.get("username", "system"),
                           "test_clarodom", "CLARODOM",
                           f"Conexion: {conn_result.get('connected')}, Auth: {auth_result.get('authenticated')}")

        return jsonify({
            "success": True,
            "connection": conn_result,
            "authentication": auth_result,
        })

    except Exception as e:
        log_error("[CLARODOM_API] Error probando conexion", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500