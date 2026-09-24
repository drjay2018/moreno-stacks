"""
brute_force.py — Protección contra fuerza bruta y rate limiting por sesión.
Almacena intentos en memoria (se reinicia con el servidor, suficiente para protección básica).
"""

import time
import logging
from functools import wraps
from flask import request, jsonify, session, current_app
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Almacén en memoria: {ip: {"attempts": int, "locked_until": float}}
_login_attempts: dict[str, dict] = {}

MAX_LOGIN_ATTEMPTS = 5  # valor por defecto; ver current_app.config
LOCKOUT_SECONDS = 1800  # valor por defecto; ver current_app.config (30 minutos)
CLEANUP_INTERVAL = 300  # Limpiar cada 5 min


def _max_login_attempts() -> int:
    return current_app.config.get("MAX_LOGIN_ATTEMPTS", MAX_LOGIN_ATTEMPTS)


def _lockout_seconds() -> int:
    return current_app.config.get("LOCKOUT_SECONDS", LOCKOUT_SECONDS)


def _cleanup_old_entries():
    """Elimina entradas expiradas del cache."""
    now = time.time()
    expired = [ip for ip, data in _login_attempts.items()
               if data.get("locked_until", 0) < now and data.get("locked_until", 0) > 0]
    for ip in expired:
        del _login_attempts[ip]


def record_failed_attempt(ip: str) -> dict:
    """
    Registra un intento fallido de login.
    Retorna: {"attempts": int, "locked": bool, "locked_until": float|None}
    """
    _cleanup_old_entries()
    now = time.time()

    if ip not in _login_attempts:
        _login_attempts[ip] = {"attempts": 0, "locked_until": 0}

    entry = _login_attempts[ip]

    # Si está bloqueado, no hacer nada
    if entry.get("locked_until", 0) > now:
        remaining = int(entry["locked_until"] - now)
        return {"attempts": entry["attempts"], "locked": True, "locked_until": entry["locked_until"], "remaining_seconds": remaining}

    entry["attempts"] += 1

    max_attempts = _max_login_attempts()
    lockout_seconds = _lockout_seconds()
    if entry["attempts"] >= max_attempts:
        entry["locked_until"] = now + lockout_seconds
        logger.warning(f"IP {ip} bloqueada por {lockout_seconds}s tras {max_attempts} intentos fallidos.")
        return {"attempts": entry["attempts"], "locked": True, "locked_until": entry["locked_until"], "remaining_seconds": lockout_seconds}

    return {"attempts": entry["attempts"], "locked": False, "locked_until": None, "remaining_seconds": 0}


def record_successful_attempt(ip: str):
    """Limpia los intentos tras un login exitoso."""
    _login_attempts.pop(ip, None)


def is_locked(ip: str) -> dict:
    """
    Verifica si una IP está bloqueada.
    Retorna: {"locked": bool, "remaining_seconds": int}
    """
    _cleanup_old_entries()
    now = time.time()
    entry = _login_attempts.get(ip, {})

    locked_until = entry.get("locked_until", 0)
    if locked_until > now:
        remaining = int(locked_until - now)
        return {"locked": True, "remaining_seconds": remaining}

    return {"locked": False, "remaining_seconds": 0}


def get_client_ip() -> str:
    """
    Obtiene la IP real del cliente.

    No se confía en cabeceras como X-Forwarded-For / X-Real-IP: un atacante
    puede fijarlas libremente en la petición y rotar su valor en cada intento
    para evadir el bloqueo por IP de fuerza bruta. Se usa siempre
    request.remote_addr, que Werkzeug obtiene de la conexión TCP real.

    Si en el futuro la app se despliega detrás de un proxy reverso de
    confianza (nginx, load balancer, etc.), la forma correcta de soportarlo
    es envolver la app con werkzeug.middleware.proxy_fix.ProxyFix en la
    app factory (app/__init__.py), que valida cuántos proxies de confianza
    hay y solo entonces reescribe request.remote_addr — no confiar en las
    cabeceras manualmente aquí.
    """
    return request.remote_addr or "unknown"


def get_failed_attempts(ip: str) -> int:
    """Retorna el número de intentos fallidos recientes de una IP."""
    entry = _login_attempts.get(ip, {})
    now = time.time()
    if entry.get("locked_until", 0) > now:
        return entry.get("attempts", 0)
    return 0
