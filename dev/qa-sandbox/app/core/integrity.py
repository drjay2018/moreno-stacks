"""
integrity.py — Verificación de integridad de la base de datos.
Calcula HMAC-SHA256 del archivo .db para detectar modificaciones externas.
Compatible con Power BI: no modifica la estructura de la DB.
"""

import hashlib
import hmac
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_db_hash(db_path: str | Path, secret: str) -> str:
    """Calcula HMAC-SHA256 del archivo de base de datos."""
    h = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    with open(db_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def store_db_hash(db_path: str | Path, secret: str, db_session) -> str:
    """Calcula y almacena el hash de integridad en app_config."""
    from sqlalchemy import text
    db_hash = compute_db_hash(db_path, secret)
    db_session.execute(
        text("INSERT INTO app_config (clave, valor) VALUES ('db_integrity_hash', :h) "
             "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"),
        {"h": db_hash}
    )
    db_session.commit()
    return db_hash


def verify_db_integrity(db_path: str | Path, secret: str, db_session) -> dict:
    """
    Verifica integridad de la DB contra hash almacenado.
    Retorna: {"valid": bool, "current_hash": str, "stored_hash": str|None, "message": str}
    """
    from sqlalchemy import text
    stored = db_session.execute(
        text("SELECT valor FROM app_config WHERE clave='db_integrity_hash'")
    ).scalar()

    if not stored:
        return {
            "valid": True,
            "current_hash": compute_db_hash(db_path, secret),
            "stored_hash": None,
            "message": "Primera ejecución. Hash calculado y almacenado."
        }

    current = compute_db_hash(db_path, secret)
    valid = hmac.compare_digest(stored, current)

    return {
        "valid": valid,
        "current_hash": current,
        "stored_hash": stored,
        "message": "Integridad verificada." if valid else "ALERTA: La base de datos fue modificada externamente."
    }


def verify_before_restore(db_path: str | Path, uploaded_file, secret: str) -> dict:
    """
    Verifica integridad del archivo subido antes de restaurar.
    Retorna: {"valid": bool, "size": int, "magic_valid": bool, "message": str}
    """
    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    uploaded_file.seek(0)

    magic_valid = header[:15] == b"SQLite format 3"

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        uploaded_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        file_size = os.path.getsize(tmp_path)
        file_hash = compute_db_hash(tmp_path, secret)
    finally:
        os.unlink(tmp_path)

    valid = magic_valid and file_size > 0

    return {
        "valid": valid,
        "size": file_size,
        "magic_valid": magic_valid,
        "hash": file_hash,
        "message": "Archivo válido." if valid else "Archivo inválido: no es una base SQLite válida."
    }
