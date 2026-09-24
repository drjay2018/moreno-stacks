"""
google_calendar_api.py — Blueprint Flask para:
  - Flujo OAuth2 de Google (autorizar / callback / desconectar)
  - Guardado de credenciales desde la UI (no edicion de archivos)
  - Guardado de configuraciones de tiempo via Fetch API
  - Endpoint de estado de la conexion
Seguridad: Tokens y credenciales cifrados con Fernet antes de guardar en BD.
"""

import json
import logging
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, redirect, request, session
from app.core.auth_middleware import requiere_rol
from app.extensions import db

logger = logging.getLogger(__name__)

google_calendar_api_bp = Blueprint(
    "google_calendar_api", __name__, url_prefix="/api/google"
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _get_cfg():
    """Obtiene (o crea) el singleton de ConfiguracionSistema."""
    from app.core.google_models import ConfiguracionSistema
    cfg = db.session.get(ConfiguracionSistema, 1)
    if not cfg:
        cfg = ConfiguracionSistema(id=1)
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _get_oauth_flow(state=None):
    """Construye el flujo OAuth2 leyendo credenciales desde la BD (descifradas)."""
    from google_auth_oauthlib.flow import Flow

    cfg = _get_cfg()
    if not cfg.tiene_credenciales:
        raise ValueError("Credenciales de Google no configuradas. Completa el paso 1 primero.")

    redirect_uri = cfg.google_redirect_uri or "http://127.0.0.1:5000/api/google/oauth/callback"

    client_config = {
        "web": {
            "client_id":     cfg.google_client_id,
            "client_secret": cfg.get_google_client_secret(),
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = redirect_uri
    return flow


def _obtener_email_perfil(credentials) -> str:
    """Obtiene el email del usuario autenticado a partir de credenciales OAuth ya obtenidas."""
    from googleapiclient.discovery import build

    oauth2_service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
    perfil = oauth2_service.userinfo().get().execute()
    return perfil.get("email", "") or ""


# ---------------------------------------------------------------------------
# GUARDAR CREDENCIALES (Paso 1 del wizard - solo admin)
# ---------------------------------------------------------------------------

@google_calendar_api_bp.route("/config/credenciales", methods=["POST"])
@requiere_rol("Admin")
def guardar_credenciales():
    """Guarda Client ID y Client Secret cifrados en la BD."""
    data = request.get_json() or {}
    client_id     = str(data.get("client_id", "")).strip()
    client_secret = str(data.get("client_secret", "")).strip()
    redirect_uri  = str(data.get("redirect_uri", "")).strip()

    if not client_id or not client_secret:
        return jsonify({"success": False, "error": "Debes proporcionar Client ID y Client Secret."}), 400

    if not client_id.endswith(".apps.googleusercontent.com"):
        return jsonify({
            "success": False,
            "error": "El Client ID debe terminar en '.apps.googleusercontent.com'. Verifica que lo copiaste correctamente."
        }), 400

    cfg = _get_cfg()
    cfg.google_client_id = client_id
    cfg.set_google_client_secret(client_secret)  # Cifrado antes de guardar
    if redirect_uri:
        cfg.google_redirect_uri = redirect_uri
    cfg.fecha_actualizacion = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Credenciales guardadas correctamente. Ahora puedes conectar tu cuenta de Google.",
    })


@google_calendar_api_bp.route("/config/credenciales/borrar", methods=["POST"])
@requiere_rol("Admin")
def borrar_credenciales():
    """Elimina credenciales y tokens (resetea la conexion)."""
    from app.core.google_models import GoogleOAuthToken

    cfg = _get_cfg()
    cfg.google_client_id     = None
    cfg.google_client_secret = None

    token_row = db.session.get(GoogleOAuthToken, 1)
    if token_row:
        token_row.access_token  = None
        token_row.refresh_token = None
        token_row.conectado     = False
        token_row.email         = None

    db.session.commit()
    return jsonify({"success": True, "message": "Credenciales y tokens eliminados."})


# ---------------------------------------------------------------------------
# RUTAS OAUTH2
# ---------------------------------------------------------------------------

@google_calendar_api_bp.route("/oauth/autorizar")
def oauth_autorizar():
    """Redirige al usuario a la pantalla de consentimiento REAL de Google.

    Requiere que el administrador haya configurado Client ID y Client Secret
    reales (paso 1 del wizard). Si no hay credenciales, no se genera ninguna
    conexion falsa: se informa claramente al usuario.
    """
    cfg = _get_cfg()
    if not cfg.tiene_credenciales:
        error_msg = quote("Integracion con Google Calendar no configurada. Contacta al administrador.")
        return redirect(f"/configuracion/?google_error={error_msg}&tab=calendar")

    try:
        flow = _get_oauth_flow()
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
    except Exception as exc:
        logger.error("Error generando URL de autorizacion de Google: %s", exc)
        error_msg = quote(str(exc)[:160])
        return redirect(f"/configuracion/?google_error={error_msg}&tab=calendar")

    session["oauth_state"] = state
    return redirect(auth_url)


@google_calendar_api_bp.route("/oauth/callback")
def oauth_callback():
    """Google redirige aqui tras el consentimiento. Intercambia el codigo real por tokens reales."""
    from app.core.google_models import GoogleOAuthToken

    state = session.get("oauth_state")
    if not state or request.args.get("state") != state:
        return redirect("/configuracion/?google_error=Verificacion+de+seguridad+fallida.+Intenta+de+nuevo.&tab=calendar")

    cfg = _get_cfg()
    if not cfg.tiene_credenciales:
        error_msg = quote("Integracion con Google Calendar no configurada. Contacta al administrador.")
        return redirect(f"/configuracion/?google_error={error_msg}&tab=calendar")

    codigo = request.args.get("code")
    if not codigo:
        error_msg = quote("Google no devolvio un codigo de autorizacion.")
        return redirect(f"/configuracion/?google_error={error_msg}&tab=calendar")

    try:
        flow = _get_oauth_flow(state=state)
        flow.fetch_token(code=codigo)
        credentials = flow.credentials

        email = _obtener_email_perfil(credentials)

        token_row = db.session.get(GoogleOAuthToken, 1)
        if not token_row:
            token_row = GoogleOAuthToken(id=1)
            db.session.add(token_row)

        token_row.email     = email
        token_row.set_access_token(credentials.token)
        if credentials.refresh_token:
            token_row.set_refresh_token(credentials.refresh_token)
        token_row.token_uri = credentials.token_uri or "https://oauth2.googleapis.com/token"
        token_row.client_id = credentials.client_id
        token_row.set_client_secret(credentials.client_secret)
        token_row.scopes    = json.dumps(list(credentials.scopes) if credentials.scopes else SCOPES)

        token_row.expires_at     = credentials.expiry
        token_row.conectado      = True
        token_row.fecha_conexion = datetime.utcnow()
        db.session.commit()

        session.pop("oauth_state", None)

        logger.info("Google Calendar conectado para: %s", email)
        return redirect(f"/configuracion/?google_ok=1&email={quote(email)}&tab=calendar")

    except Exception as exc:
        logger.error("Error en OAuth callback: %s", exc)
        error_msg = quote(str(exc)[:160])
        return redirect(f"/configuracion/?google_error={error_msg}&tab=calendar")


@google_calendar_api_bp.route("/oauth/desconectar", methods=["POST"])
@requiere_rol("Admin")
def oauth_desconectar():
    """Desconecta la cuenta (elimina tokens, conserva credenciales de app)."""
    from app.core.google_models import GoogleOAuthToken

    token_row = db.session.get(GoogleOAuthToken, 1)
    if token_row:
        token_row.access_token  = None
        token_row.refresh_token = None
        token_row.conectado     = False
        token_row.email         = None
        db.session.commit()

    return jsonify({"success": True, "message": "Cuenta de Google desconectada."})


# ---------------------------------------------------------------------------
# ESTADO Y CONFIGURACION
# ---------------------------------------------------------------------------

@google_calendar_api_bp.route("/estado", methods=["GET"])
def estado_conexion():
    """Retorna el estado completo de la conexion con Google Calendar."""
    from app.core.google_models import GoogleOAuthToken

    token_row = db.session.get(GoogleOAuthToken, 1)
    cfg       = _get_cfg()

    conectado = bool(token_row and token_row.conectado)
    email     = token_row.email if conectado else None

    return jsonify({
        "success":           True,
        "tiene_credenciales": cfg.tiene_credenciales,
        "conectado":          conectado,
        "email":              email,
        "config":             cfg.to_dict(),
    })


@google_calendar_api_bp.route("/config/guardar", methods=["POST"])
@requiere_rol("Admin")
def guardar_config():
    """Guarda preferencias de tiempo."""
    data = request.get_json() or {}
    cfg  = _get_cfg()

    frecuencia = data.get("frecuencia_postventa")
    if frecuencia in ("mensual", "semestral", "anual"):
        cfg.frecuencia_postventa = frecuencia

    ant_pv = data.get("antelacion_postventa_dias")
    if isinstance(ant_pv, int) and 1 <= ant_pv <= 90:
        cfg.antelacion_postventa_dias = ant_pv

    dias_lead = data.get("dias_contacto_lead")
    if isinstance(dias_lead, int) and 1 <= dias_lead <= 30:
        cfg.dias_contacto_lead = dias_lead

    ant_cobro = data.get("antelacion_cobro_dias")
    if isinstance(ant_cobro, int) and 1 <= ant_cobro <= 30:
        cfg.antelacion_cobro_dias = ant_cobro

    calendar_id = data.get("calendar_id")
    if calendar_id:
        cfg.calendar_id = str(calendar_id)[:255]

    timezone = data.get("timezone")
    if timezone:
        cfg.timezone = str(timezone)[:80]

    cfg.fecha_actualizacion = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Configuracion guardada correctamente.",
        "config":  cfg.to_dict(),
    })


# ---------------------------------------------------------------------------
# ENDPOINT DE PRUEBA
# ---------------------------------------------------------------------------

@google_calendar_api_bp.route("/test-evento", methods=["POST"])
@requiere_rol("Admin")
def test_evento():
    """Crea un evento de prueba en el calendario de forma SINCRONA y reporta el resultado real.

    A diferencia de las alertas automaticas (post-venta, leads, cobros), que siguen
    siendo fire-and-forget en un thread para no bloquear a Flask, este endpoint lo
    dispara el usuario a proposito para verificar la conexion: por eso se espera
    el resultado real de Google Calendar antes de responder.
    """
    from app.core.calendar_service import crear_evento_prueba
    from app.core.google_models import GoogleOAuthToken

    token_row = db.session.get(GoogleOAuthToken, 1)
    if not token_row or not token_row.conectado:
        return jsonify({"success": False, "error": "No hay cuenta de Google conectada."}), 400

    resultado = crear_evento_prueba()

    if not resultado.get("success"):
        return jsonify({
            "success": False,
            "error": resultado.get("error") or "No se pudo crear el evento de prueba.",
        }), 502

    return jsonify({
        "success": True,
        "message": "Evento de prueba creado correctamente. Verifica tu Google Calendar.",
    })
