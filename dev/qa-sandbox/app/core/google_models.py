"""
google_models.py — Modelos SQLAlchemy para tokens OAuth2 de Google y configuraciones del sistema.
Tokens sensibles cifrados con Fernet (compatible con Power BI: DB sigue legible).
"""

from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.extensions import db


class FrecuenciaEnum(str, enum.Enum):
    """Frecuencia de seguimiento post-venta."""
    MENSUAL   = "mensual"
    SEMESTRAL = "semestral"
    ANUAL     = "anual"


class GoogleOAuthToken(db.Model):
    """
    Almacena los tokens de acceso y refresco de Google OAuth2.
    Solo existe un registro (singleton id=1).
    Los campos sensibles (access_token, refresh_token, client_secret) se cifran al guardar.
    """
    __tablename__ = "google_oauth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None]         = mapped_column(String(120), nullable=True)
    access_token: Mapped[str | None]  = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_uri: Mapped[str | None]     = mapped_column(String(255), nullable=True)
    client_id: Mapped[str | None]     = mapped_column(String(255), nullable=True)
    client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes: Mapped[str | None]        = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conectado: Mapped[bool]           = mapped_column(Boolean, default=False)
    fecha_conexion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def set_access_token(self, value: str):
        from app.core.crypto import ensure_encrypted
        self.access_token = ensure_encrypted(value) if value else value

    def set_refresh_token(self, value: str):
        from app.core.crypto import ensure_encrypted
        self.refresh_token = ensure_encrypted(value) if value else value

    def set_client_secret(self, value: str):
        from app.core.crypto import ensure_encrypted
        self.client_secret = ensure_encrypted(value) if value else value

    def get_access_token(self) -> str:
        from app.core.crypto import ensure_decrypted
        return ensure_decrypted(self.access_token) if self.access_token else ""

    def get_refresh_token(self) -> str:
        from app.core.crypto import ensure_decrypted
        return ensure_decrypted(self.refresh_token) if self.refresh_token else ""

    def get_client_secret(self) -> str:
        from app.core.crypto import ensure_decrypted
        return ensure_decrypted(self.client_secret) if self.client_secret else ""

    def to_credentials_dict(self) -> dict:
        """Reconstruye el dict que espera google.oauth2.credentials.Credentials."""
        import json
        return {
            "token":         self.get_access_token(),
            "refresh_token": self.get_refresh_token(),
            "token_uri":     self.token_uri or "https://oauth2.googleapis.com/token",
            "client_id":     self.client_id,
            "client_secret": self.get_client_secret(),
            "scopes":        json.loads(self.scopes) if self.scopes else [],
        }


class ConfiguracionSistema(db.Model):
    """
    Parametros editables de tiempo, comportamiento y credenciales de Google.
    Singleton (id=1). Las credenciales de Google se guardan aqui para que
    el administrador las configure desde la UI sin tocar archivos del sistema.
    """
    __tablename__ = "configuracion_sistema"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Credenciales Google (ingresadas por el admin desde la UI)
    google_client_id:     Mapped[str | None] = mapped_column(Text, nullable=True)
    google_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_redirect_uri:  Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        default="http://127.0.0.1:5000/api/google/oauth/callback"
    )

    # Seguimiento Post-Venta
    frecuencia_postventa: Mapped[str] = mapped_column(
        SAEnum(FrecuenciaEnum), default=FrecuenciaEnum.ANUAL
    )
    antelacion_postventa_dias: Mapped[int] = mapped_column(Integer, default=7)

    # Leads de Campanas
    dias_contacto_lead: Mapped[int] = mapped_column(Integer, default=3)

    # Alertas de Cobros
    antelacion_cobro_dias: Mapped[int] = mapped_column(Integer, default=3)

    # Calendario
    calendar_id: Mapped[str] = mapped_column(String(255), default="primary")
    timezone: Mapped[str]    = mapped_column(String(80), default="America/Santo_Domingo")

    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def tiene_credenciales(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    def set_google_client_secret(self, value: str):
        from app.core.crypto import ensure_encrypted
        self.google_client_secret = ensure_encrypted(value) if value else value

    def get_google_client_secret(self) -> str:
        from app.core.crypto import ensure_decrypted
        return ensure_decrypted(self.google_client_secret) if self.google_client_secret else ""

    def to_dict(self) -> dict:
        return {
            "id":                        self.id,
            "tiene_credenciales":        self.tiene_credenciales,
            "google_redirect_uri":       self.google_redirect_uri
                                         or "http://127.0.0.1:5000/api/google/oauth/callback",
            "frecuencia_postventa":      self.frecuencia_postventa,
            "antelacion_postventa_dias": self.antelacion_postventa_dias,
            "dias_contacto_lead":        self.dias_contacto_lead,
            "antelacion_cobro_dias":     self.antelacion_cobro_dias,
            "calendar_id":               self.calendar_id,
            "timezone":                  self.timezone,
            "fecha_actualizacion":       str(self.fecha_actualizacion),
        }
