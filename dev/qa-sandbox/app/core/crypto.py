"""
crypto.py — Cifrado simétrico de campos sensibles (Fernet/AES-128-CBC).
Compatible con Power BI: la DB permanece legible, pero los secrets están cifrados.
"""

import os
import logging

logger = logging.getLogger(__name__)

_field_key = os.environ.get("FIELD_ENCRYPTION_KEY", "")
_fernet = None

try:
    from cryptography.fernet import Fernet, InvalidToken
    if _field_key:
        _fernet = Fernet(_field_key.encode() if isinstance(_field_key, str) else _field_key)
except ImportError:
    logger.critical("cryptography no instalado. Cifrado de campos deshabilitado. Instala con: pip install cryptography")
except Exception as e:
    # FIELD_ENCRYPTION_KEY esta presente pero es invalida (longitud/formato incorrecto).
    # NO degradar en silencio a texto plano: eso hizo que instalaciones creadas con una
    # version antigua de setup_windows.ps1 guardaran tokens y passwords SIN cifrar
    # mientras la UI y la documentacion afirmaban que si lo estaban.
    if os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY invalida: no se puede inicializar el cifrado de campos. "
            "Genera una clave valida con: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\" y actualiza tu .env. "
            f"Error original: {e}"
        ) from e
    logger.critical(
        f"FIELD_ENCRYPTION_KEY invalida ({e}). El cifrado de campos esta DESACTIVADO: "
        "tokens y contrasenas se guardaran SIN CIFRAR mientras esto no se corrija."
    )

if _fernet is None and not _field_key:
    # No hay clave en absoluto (no es un error de formato, simplemente falta).
    if os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY no esta configurada. En produccion es obligatoria: "
            "genera una con python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\" y defínela en .env."
        )
    logger.critical(
        "FIELD_ENCRYPTION_KEY no configurada. El cifrado de campos esta DESACTIVADO: "
        "tokens y contrasenas se guardaran SIN CIFRAR."
    )


def encrypt_field(plaintext: str) -> str:
    if not _fernet or not plaintext:
        return plaintext
    try:
        return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Error cifrando campo: {e}")
        return plaintext


def decrypt_field(ciphertext: str) -> str:
    if not _fernet or not ciphertext:
        return ciphertext
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("Token de cifrado inválido o dato no cifrado. Retornando valor original.")
        return ciphertext
    except Exception as e:
        logger.error(f"Error descifrando campo: {e}")
        return ciphertext


def is_encrypted(value: str) -> bool:
    """Verifica si un valor fue cifrado con Fernet (empieza con gAAAAA)."""
    return isinstance(value, str) and value.startswith("gAAAAA")


def ensure_encrypted(value: str) -> str:
    """Cifra solo si no está ya cifrado."""
    if not value or is_encrypted(value):
        return value
    return encrypt_field(value)


def ensure_decrypted(value: str) -> str:
    """Descifra solo si está cifrado."""
    if not value or not is_encrypted(value):
        return value
    return decrypt_field(value)
