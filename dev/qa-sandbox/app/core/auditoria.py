"""
auditoria.py — Registro de auditoria mejorado con IP, user-agent y HMAC de integridad.
"""

import hashlib
import hmac
import os
from datetime import datetime
from flask import request
from sqlalchemy import text
from app.extensions import db
from app.core.logger import log_info, log_error


def _get_request_context():
    """Extrae contexto del request actual (IP, user-agent, path)."""
    try:
        ip = "unknown"
        if request.headers.get("X-Forwarded-For"):
            ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        elif request.headers.get("X-Real-IP"):
            ip = request.headers["X-Real-IP"]
        elif request.remote_addr:
            ip = request.remote_addr

        return {
            "ip_address": ip[:45],
            "user_agent": (request.headers.get("User-Agent", ""))[:255],
            "request_path": (request.path)[:500],
        }
    except RuntimeError:
        return {"ip_address": None, "user_agent": None, "request_path": None}


def _compute_hmac(record: dict, secret: str) -> str:
    """Calcula HMAC-SHA256 para firmar el registro de auditoria."""
    payload = f"{record.get('uid', '')}|{record.get('acc', '')}|{record.get('mod', '')}|{record.get('fec', '')}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def registrar_auditoria(usuario_id, username_snapshot, accion, modulo, detalle):
    """
    Registra una accion en la tabla de auditoria del sistema.
    Ahora incluye: IP del cliente, user-agent, path de la request y HMAC de integridad.
    """
    try:
        ctx = _get_request_context()
        now = datetime.now()

        secret = os.environ.get("DB_INTEGRITY_SECRET", "")
        record = {
            "uid": usuario_id,
            "acc": accion,
            "mod": modulo,
            "fec": now.isoformat(),
        }
        hash_firma = _compute_hmac(record, secret) if secret else None

        query = text("""
            INSERT INTO auditoria (usuario_id, username_snapshot, accion, modulo, detalle, fecha,
                                   ip_address, user_agent, request_path, hash_firma)
            VALUES (:uid, :uname, :acc, :mod, :det, :fec, :ip, :ua, :rp, :hf)
        """)
        db.session.execute(query, {
            "uid": usuario_id,
            "uname": username_snapshot,
            "acc": accion,
            "mod": modulo,
            "det": detalle[:300] if detalle else None,
            "fec": now,
            "ip": ctx["ip_address"],
            "ua": ctx["user_agent"],
            "rp": ctx["request_path"],
            "hf": hash_firma,
        })
        db.session.commit()
        log_info(modulo, f'[{username_snapshot}] {accion}: {detalle}')
    except Exception as e:
        db.session.rollback()
        print(f"Error registrando auditoria: {e}")
        log_error('AUDITORIA', f'Error registrando auditoria: {e}', exc_info=True)
