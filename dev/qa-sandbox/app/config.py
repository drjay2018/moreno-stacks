"""
config.py — Configuracion global del servidor Flask con opciones de seguridad avanzadas.
"""

import os
import secrets
from pathlib import Path

import sys
if getattr(sys, 'frozen', False):
    bundle_dir = Path(sys.executable).resolve().parent
    if (bundle_dir / "_internal").exists():
        BASE_DIR = bundle_dir / "_internal"
    else:
        BASE_DIR = bundle_dir
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Guardar base de datos en %APPDATA%\DLAB_CRM\data para que no se borre en actualizaciones
appdata_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
USER_DATA_DIR = Path(appdata_dir) / "DLAB_CRM" / "data"
DB_PATH = USER_DATA_DIR / "dlab.db"

# Ruta de la base de datos plantilla (de donde se copiara en la primera instalacion)
TEMPLATE_DB_PATH = BASE_DIR / "dlab-data" / "data" / "dlab.db"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    # Seguridad de campos cifrados (Fernet/AES) - compatible con Power BI
    FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")

    # Integridad de la DB (HMAC-SHA256)
    DB_INTEGRITY_SECRET = os.environ.get("DB_INTEGRITY_SECRET", "")

    # Rate Limiting
    RATE_LIMIT_STORAGE_URI = os.environ.get("RATE_LIMIT_STORAGE_URI", "memory://")

    # Proteccion de cuentas
    MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_SECONDS = int(os.environ.get("LOCKOUT_SECONDS", "1800"))

    # Limite maximo de tamano de payloads/archivos (16 MB) para prevencion de DoS
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Configuracion defensiva de Cookies de Sesion
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    # Base de Datos
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {
            "timeout": 20,
            "check_same_thread": False
        },
        "pool_pre_ping": True,
    }

    # Google Calendar OAuth2
    GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID",     "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI  = os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "http://127.0.0.1:5000/api/google/oauth/callback"
    )
    OAUTHLIB_INSECURE_TRANSPORT = True


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    OAUTHLIB_INSECURE_TRANSPORT = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    OAUTHLIB_INSECURE_TRANSPORT = False


class TestConfig(Config):
    """Configuracion aislada para la suite de pruebas (base de datos temporal)."""
    TESTING = True
    WTF_CSRF_ENABLED = False
    RATE_LIMIT_ENABLED = False
    DB_INTEGRITY_SECRET = "test-integrity-secret"
    test_db = Path(os.environ.get("TEMP", "/tmp")) / "dlab_test.db"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{test_db}"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False, "timeout": 20},
        "pool_pre_ping": True,
    }
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
