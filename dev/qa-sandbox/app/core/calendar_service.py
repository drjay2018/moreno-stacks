"""
calendar_service.py — Servicio de integracion con Google Calendar.
Parte 2/4 del modulo de Google Calendar.
Seguridad: Tokens cifrados con Fernet, compatible con Power BI.

ARQUITECTURA DE RENDIMIENTO:
- Toda llamada a la Google Calendar API se ejecuta en un Thread secundario
  para NO bloquear el hilo principal de Flask.
- El hilo principal retorna inmediatamente al cliente; el evento se crea
  en segundo plano (fire-and-forget con log de errores).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _get_credentials():
    """
    Obtiene credenciales de Google desde la BD (descifradas) y las refresca si es necesario.
    Retorna None si no hay token o si el token no es valido.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from app.core.google_models import GoogleOAuthToken
        from app.extensions import db

        token_row = db.session.get(GoogleOAuthToken, 1)
        if not token_row or not token_row.conectado:
            logger.warning("Google Calendar: No hay cuenta conectada.")
            return None

        # to_credentials_dict() ya usa get_*() que descifran automaticamente
        creds = Credentials(**token_row.to_credentials_dict())

        # Refrescar si expiro
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Persistir el token actualizado (cifrado)
            token_row.set_access_token(creds.token)
            token_row.expires_at = creds.expiry
            db.session.commit()

        return creds
    except Exception as exc:
        logger.error("Error obteniendo credenciales de Google: %s", exc)
        return None


def _build_service():
    """Construye el cliente de Google Calendar API v3."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _crear_evento_en_thread(event_body: dict, calendar_id: str = "primary"):
    """Funcion interna ejecutada en Thread secundario."""
    def _run():
        try:
            service = _build_service()
            if not service:
                return
            resultado = service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()
            logger.info(
                "Evento Google Calendar creado: %s (ID: %s)",
                event_body.get("summary"),
                resultado.get("id")
            )
        except Exception as exc:
            logger.error("Error creando evento en Google Calendar: %s", exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _get_config():
    """Obtiene la fila de ConfiguracionSistema (singleton id=1)."""
    try:
        from app.core.google_models import ConfiguracionSistema
        from app.extensions import db
        cfg = db.session.get(ConfiguracionSistema, 1)
        return cfg
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API PUBLICA DEL SERVICIO
# ---------------------------------------------------------------------------

def crear_evento_prueba() -> dict:
    """
    TRIGGER: Boton "Probar Evento" en Configuracion (accion manual del usuario).
    A diferencia de las demas funciones de este modulo, esta se ejecuta de forma
    SINCRONA (no fire-and-forget): el llamador necesita conocer el resultado real
    para poder informarle al usuario si la conexion realmente funciona.
    Retorna {"success": bool, "error": str | None, "event_id": str | None}.
    """
    cfg = _get_config()
    calendar_id = cfg.calendar_id if cfg else "primary"
    timezone    = cfg.timezone    if cfg else "America/Santo_Domingo"

    hoy = date.today()
    event_body = {
        "summary":     "Evento de Prueba - CRM DLAB",
        "description": (
            "Este es un evento de prueba generado desde Configuracion para validar "
            "la conexion con Google Calendar. Puedes eliminarlo con confianza."
        ),
        "start": {"date": hoy.isoformat(),                          "timeZone": timezone},
        "end":   {"date": (hoy + timedelta(days=1)).isoformat(),    "timeZone": timezone},
    }

    try:
        service = _build_service()
        if not service:
            return {
                "success": False,
                "error": "No hay una conexion valida con Google Calendar. Revisa las credenciales y reconecta la cuenta.",
                "event_id": None,
            }
        resultado = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        logger.info("Evento de prueba creado en Google Calendar: %s", resultado.get("id"))
        return {"success": True, "error": None, "event_id": resultado.get("id")}
    except Exception as exc:
        logger.error("Error creando evento de prueba en Google Calendar: %s", exc)
        return {"success": False, "error": str(exc), "event_id": None}

def crear_evento_post_venta(
    nombre_cliente: str,
    transaccion_codigo: str,
    fecha_cierre: date,
    frecuencia: str = "anual"
) -> None:
    """
    TRIGGER: Al cerrar una transaccion.
    Crea recordatorios recurrentes de seguimiento de fidelizacion al cliente.
    Se ejecuta en Thread secundario (no bloquea Flask).
    """
    cfg = _get_config()
    frecuencia_cfg = cfg.frecuencia_postventa if cfg else frecuencia
    calendar_id = cfg.calendar_id if cfg else "primary"
    timezone    = cfg.timezone    if cfg else "America/Santo_Domingo"

    if frecuencia_cfg == "mensual":
        fecha_seguimiento = fecha_cierre + timedelta(days=30)
        recurrencia = ["RRULE:FREQ=MONTHLY"]
    elif frecuencia_cfg == "semestral":
        fecha_seguimiento = fecha_cierre + timedelta(days=180)
        recurrencia = ["RRULE:FREQ=YEARLY;BYMONTH=6"]
    else:
        fecha_seguimiento = fecha_cierre + timedelta(days=365)
        recurrencia = ["RRULE:FREQ=YEARLY"]

    event_body = {
        "summary":     f"Seguimiento Post-Venta: {nombre_cliente}",
        "description": (
            f"Recordatorio de fidelizacion para el cliente {nombre_cliente}.\n"
            f"Transaccion: {transaccion_codigo}\n"
            f"Fecha de cierre original: {fecha_cierre.isoformat()}\n\n"
            "Acciones sugeridas: Llamada de satisfaccion, oferta de referidos, "
            "actualizacion de estado del inmueble."
        ),
        "start": {"date": fecha_seguimiento.isoformat(), "timeZone": timezone},
        "end":   {"date": (fecha_seguimiento + timedelta(days=1)).isoformat(), "timeZone": timezone},
        "recurrence": recurrencia,
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": 24 * 60},
                {"method": "popup",  "minutes": 60},
            ],
        },
        "colorId": "2",
    }

    _crear_evento_en_thread(event_body, calendar_id)


def crear_evento_contacto_lead(
    nombre_lead: str,
    campana: str,
    email_lead: Optional[str] = None,
    telefono_lead: Optional[str] = None,
    fecha_registro: Optional[date] = None
) -> None:
    """
    TRIGGER: Al registrar un prospecto nuevo proveniente de campana de marketing.
    Agenda un evento de contacto inicial en X dias (configurable).
    Se ejecuta en Thread secundario.
    """
    cfg = _get_config()
    dias_contacto = cfg.dias_contacto_lead if cfg else 3
    calendar_id   = cfg.calendar_id        if cfg else "primary"
    timezone      = cfg.timezone           if cfg else "America/Santo_Domingo"

    base = fecha_registro or date.today()
    fecha_contacto = base + timedelta(days=dias_contacto)

    attendees = []
    if email_lead:
        attendees.append({"email": email_lead})

    event_body = {
        "summary":     f"Contacto Inicial Lead: {nombre_lead}",
        "description": (
            f"Lead registrado desde campana: {campana}\n"
            f"Nombre: {nombre_lead}\n"
            f"Telefono: {telefono_lead or 'No registrado'}\n"
            f"Email: {email_lead or 'No registrado'}\n\n"
            "Acciones: Llamada de calificacion, envio de brochure, "
            "agendamiento de visita al proyecto."
        ),
        "start": {
            "dateTime": f"{fecha_contacto.isoformat()}T09:00:00",
            "timeZone": timezone,
        },
        "end": {
            "dateTime": f"{fecha_contacto.isoformat()}T09:30:00",
            "timeZone": timezone,
        },
        "attendees": attendees,
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
                {"method": "email", "minutes": 60},
            ],
        },
        "colorId": "5",
    }

    _crear_evento_en_thread(event_body, calendar_id)


def crear_evento_alerta_cobro(
    nombre_cliente: str,
    transaccion_codigo: str,
    monto: float,
    fecha_vencimiento: date,
    cobro_id: int
) -> None:
    """
    TRIGGER: Cuando el sistema detecta proximidad de un pago (aging).
    Crea un evento/recordatorio de cobro proximo en el calendario.
    Se ejecuta en Thread secundario.
    """
    cfg = _get_config()
    antelacion    = cfg.antelacion_cobro_dias if cfg else 3
    calendar_id   = cfg.calendar_id           if cfg else "primary"
    timezone      = cfg.timezone              if cfg else "America/Santo_Domingo"

    fecha_evento = fecha_vencimiento - timedelta(days=antelacion)
    if fecha_evento < date.today():
        fecha_evento = date.today()

    monto_fmt = f"${monto:,.2f} USD"

    event_body = {
        "summary":     f"Cobro Proximo: {nombre_cliente} - {monto_fmt}",
        "description": (
            f"Alerta de cobro proximo a vencer.\n"
            f"Cliente: {nombre_cliente}\n"
            f"Transaccion: {transaccion_codigo}\n"
            f"Monto pendiente: {monto_fmt}\n"
            f"Fecha de vencimiento: {fecha_vencimiento.isoformat()}\n"
            f"ID de Cobro: #{cobro_id}\n\n"
            "Acciones: Contactar al cliente, registrar pago en el sistema, "
            "actualizar estado de morosidad."
        ),
        "start": {"date": fecha_evento.isoformat(),                              "timeZone": timezone},
        "end":   {"date": (fecha_evento + timedelta(days=1)).isoformat(),         "timeZone": timezone},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "email", "minutes": 24 * 60},
            ],
        },
        "colorId": "11",
    }

    _crear_evento_en_thread(event_body, calendar_id)
