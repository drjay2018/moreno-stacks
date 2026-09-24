"""
test_crud_google_calendar.py — Tests for Google Calendar API endpoints.
"""

import json
from unittest.mock import patch


def _conectar_google_directo(app, email='demo.asesor@dlabrealty.com'):
    """
    Inserta directamente una fila 'conectada' en google_oauth_tokens.

    Antes estos tests simulaban una conexion via un endpoint OAuth "modo
    demo" (google_calendar_api.oauth_callback generaba tokens falsos como
    "mock_access_token_123" sin contactar a Google realmente). Ese mock fue
    retirado: ahora oauth_callback intercambia un codigo real con Google y
    falla limpiamente si no hay credenciales configuradas. Para probar el
    comportamiento de endpoints que dependen de "ya hay una cuenta
    conectada" (borrar credenciales, desconectar, test-evento), se prepara
    el estado directamente en la base de datos.
    """
    from app.core.google_models import GoogleOAuthToken
    from app.extensions import db

    with app.app_context():
        token_row = db.session.get(GoogleOAuthToken, 1)
        if not token_row:
            token_row = GoogleOAuthToken(id=1)
            db.session.add(token_row)
        token_row.email = email
        token_row.set_access_token('fake-access-token-para-test')
        token_row.set_refresh_token('fake-refresh-token-para-test')
        token_row.conectado = True
        db.session.commit()


class TestGoogleCalendarEstado:
    """GET /api/google/estado"""

    def test_estado_returns_success(self, logged_in_client):
        r = logged_in_client.get('/api/google/estado')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert 'tiene_credenciales' in data
        assert 'conectado' in data
        assert 'email' in data
        assert 'config' in data

    def test_estado_requires_auth(self, client):
        """estado revela el email de la cuenta conectada: requiere sesion.

        Antes estaba exento del gate global de login (junto con oauth_autorizar),
        lo que permitia a cualquier anonimo consultar el estado de conexion.
        Se corrigio en app/__init__.py: ahora solo oauth_callback queda exenta
        (porque Google no reenvia la cookie de sesion en su redireccion).
        """
        r = client.get('/api/google/estado')
        assert r.status_code == 401

    def test_estado_default_not_connected(self, logged_in_client):
        r = logged_in_client.get('/api/google/estado')
        data = r.get_json()
        assert data['conectado'] is False
        assert data['email'] is None


class TestGoogleCalendarCredenciales:
    """POST /api/google/config/credenciales"""

    def test_guardar_credenciales_ok(self, logged_in_client):
        payload = {
            'client_id': '123456789.apps.googleusercontent.com',
            'client_secret': 'GOCSPX-test-secret',
        }
        r = logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

    def test_guardar_credenciales_with_redirect(self, logged_in_client):
        payload = {
            'client_id': '999999999.apps.googleusercontent.com',
            'client_secret': 'secret123',
            'redirect_uri': 'https://example.com/callback',
        }
        r = logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_guardar_credenciales_missing_fields(self, logged_in_client):
        payload = {'client_id': 'only-id.apps.googleusercontent.com'}
        r = logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 400
        data = r.get_json()
        assert data['success'] is False

    def test_guardar_credenciales_bad_client_id_format(self, logged_in_client):
        payload = {
            'client_id': 'bad-format-client-id',
            'client_secret': 'secret',
        }
        r = logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 400
        data = r.get_json()
        assert data['success'] is False
        assert 'apps.googleusercontent.com' in data['error']

    def test_guardar_credenciales_empty_body(self, logged_in_client):
        r = logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert r.status_code == 400

    def test_guardar_credenciales_no_auth(self, client):
        """Requires Admin role — unauthenticated should fail."""
        payload = {
            'client_id': 'test.apps.googleusercontent.com',
            'client_secret': 'secret',
        }
        r = client.post(
            '/api/google/config/credenciales',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code in (302, 401, 403)


class TestGoogleCalendarBorrarCredenciales:
    """POST /api/google/config/credenciales/borrar"""

    def test_borrar_credenciales_ok(self, logged_in_client):
        # First save credentials so there is something to delete
        logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps({
                'client_id': 'test.apps.googleusercontent.com',
                'client_secret': 'secret',
            }),
            content_type='application/json',
        )

        r = logged_in_client.post('/api/google/config/credenciales/borrar')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

        # Verify estado shows no credentials after deletion
        r2 = logged_in_client.get('/api/google/estado')
        estado = r2.get_json()
        assert estado['tiene_credenciales'] is False

    def test_borrar_credenciales_clears_tokens(self, logged_in_client, app):
        """Deleting credentials also resets any existing OAuth tokens."""
        # Preparar una cuenta ya conectada (sin pasar por el flujo OAuth real)
        _conectar_google_directo(app)

        # Verify connected
        r = logged_in_client.get('/api/google/estado')
        assert r.get_json()['conectado'] is True

        # Now delete credentials
        r = logged_in_client.post('/api/google/config/credenciales/borrar')
        assert r.status_code == 200

        # Verify disconnected
        r2 = logged_in_client.get('/api/google/estado')
        estado = r2.get_json()
        assert estado['conectado'] is False
        assert estado['email'] is None

    def test_borrar_credenciales_no_auth(self, client):
        r = client.post('/api/google/config/credenciales/borrar')
        assert r.status_code in (302, 401, 403)


class TestGoogleCalendarAutorizar:
    """GET /api/google/oauth/autorizar"""

    def test_autorizar_sin_credenciales_redirige_con_error(self, logged_in_client):
        """
        Sin Client ID/Secret configurados, ya no se genera una conexion
        falsa (el mock retirado hacia esto): se informa al usuario con
        claridad en vez de fingir una conexion exitosa.
        """
        r = logged_in_client.get('/api/google/oauth/autorizar')
        assert r.status_code == 302
        location = r.headers.get('Location', '')
        assert '/configuracion/' in location
        assert 'google_error' in location

    def test_autorizar_con_credenciales_redirige_a_google(self, logged_in_client):
        """Con credenciales configuradas, debe redirigir a la URL real de consentimiento de Google."""
        logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps({
                'client_id': 'test.apps.googleusercontent.com',
                'client_secret': 'secret',
            }),
            content_type='application/json',
        )

        with patch('app.api.google_calendar_api._get_oauth_flow') as mock_flow:
            mock_flow.return_value.authorization_url.return_value = (
                'https://accounts.google.com/o/oauth2/auth?fake=1', 'fake-state-123'
            )
            r = logged_in_client.get('/api/google/oauth/autorizar')

        assert r.status_code == 302
        assert r.headers.get('Location', '') == 'https://accounts.google.com/o/oauth2/auth?fake=1'
        with logged_in_client.session_transaction() as sess:
            assert sess.get('oauth_state') == 'fake-state-123'

    def test_autorizar_requiere_login(self, client):
        """
        oauth_autorizar escribe estado de sesion y puede iniciar un flujo
        que termina escribiendo en la BD: ya no esta exenta del gate global
        de login (antes lo estaba junto con oauth_callback y estado_conexion,
        lo que permitia a un anonimo con acceso de red iniciar/resetear la
        conexion sin autenticarse).
        """
        r = client.get('/api/google/oauth/autorizar')
        assert r.status_code == 401


class TestGoogleCalendarCallback:
    """GET /api/google/oauth/callback"""

    def test_callback_sin_credenciales_no_conecta(self, logged_in_client):
        """
        Sin credenciales configuradas, el callback ya no genera una conexion
        falsa: responde con error y NO marca la cuenta como conectada.
        """
        with logged_in_client.session_transaction() as sess:
            sess['oauth_state'] = 'test_state'
        r = logged_in_client.get('/api/google/oauth/callback?state=test_state')
        assert r.status_code == 302
        assert 'google_error' in r.headers.get('Location', '')

        r2 = logged_in_client.get('/api/google/estado')
        assert r2.get_json()['conectado'] is False

    def test_callback_con_credenciales_conecta_con_datos_reales(self, logged_in_client, app):
        """Con credenciales configuradas y un intercambio de codigo exitoso, se guardan tokens reales."""
        logged_in_client.post(
            '/api/google/config/credenciales',
            data=json.dumps({
                'client_id': 'test.apps.googleusercontent.com',
                'client_secret': 'secret',
            }),
            content_type='application/json',
        )
        with logged_in_client.session_transaction() as sess:
            sess['oauth_state'] = 'real-state-456'

        with patch('app.api.google_calendar_api._get_oauth_flow') as mock_flow, \
             patch('app.api.google_calendar_api._obtener_email_perfil') as mock_email:
            mock_creds = mock_flow.return_value.credentials
            mock_creds.token = 'access-token-real'
            mock_creds.refresh_token = 'refresh-token-real'
            mock_creds.token_uri = 'https://oauth2.googleapis.com/token'
            mock_creds.client_id = 'test.apps.googleusercontent.com'
            mock_creds.client_secret = 'secret'
            mock_creds.scopes = ['openid']
            mock_creds.expiry = None
            mock_email.return_value = 'asesor.real@ejemplo.com'

            r = logged_in_client.get('/api/google/oauth/callback?state=real-state-456&code=abc123')

        assert r.status_code == 302
        assert 'google_ok=1' in r.headers.get('Location', '')

        r2 = logged_in_client.get('/api/google/estado')
        estado = r2.get_json()
        assert estado['conectado'] is True
        assert estado['email'] == 'asesor.real@ejemplo.com'

    def test_callback_with_invalid_state(self, logged_in_client):
        r = logged_in_client.get('/api/google/oauth/callback?state=wrong_state')
        assert r.status_code == 302
        assert 'google_error' in r.headers.get('Location', '')

    def test_callback_without_session_state(self, logged_in_client):
        r = logged_in_client.get('/api/google/oauth/callback?state=any')
        assert r.status_code == 302
        assert 'google_error' in r.headers.get('Location', '')


class TestGoogleCalendarDesconectar:
    """POST /api/google/oauth/desconectar"""

    def test_desconectar_ok(self, logged_in_client, app):
        # Preparar una cuenta ya conectada (sin pasar por el flujo OAuth real)
        _conectar_google_directo(app)
        assert logged_in_client.get('/api/google/estado').get_json()['conectado'] is True

        # Now disconnect
        r = logged_in_client.post('/api/google/oauth/desconectar')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

        # Verify disconnected
        r2 = logged_in_client.get('/api/google/estado')
        estado = r2.get_json()
        assert estado['conectado'] is False

    def test_desconectar_when_not_connected(self, logged_in_client):
        """Disconnecting when already disconnected should still succeed."""
        r = logged_in_client.post('/api/google/oauth/desconectar')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_desconectar_no_auth(self, client):
        r = client.post('/api/google/oauth/desconectar')
        assert r.status_code in (302, 401, 403)


class TestGoogleCalendarConfigGuardar:
    """POST /api/google/config/guardar"""

    def test_guardar_config_ok(self, logged_in_client):
        payload = {
            'frecuencia_postventa': 'mensual',
            'antelacion_postventa_dias': 14,
            'dias_contacto_lead': 7,
            'antelacion_cobro_dias': 5,
            'calendar_id': 'my-calendar-id@group.calendar.google.com',
            'timezone': 'America/New_York',
        }
        r = logged_in_client.post(
            '/api/google/config/guardar',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

        # Verify values persisted via estado
        r2 = logged_in_client.get('/api/google/estado')
        cfg = r2.get_json()['config']
        assert cfg['frecuencia_postventa'] == 'mensual'
        assert cfg['antelacion_postventa_dias'] == 14
        assert cfg['dias_contacto_lead'] == 7
        assert cfg['antelacion_cobro_dias'] == 5

    def test_guardar_config_partial(self, logged_in_client):
        """Only updating some fields should leave others unchanged."""
        payload = {'dias_contacto_lead': 10}
        r = logged_in_client.post(
            '/api/google/config/guardar',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 200

        cfg = r.get_json()['config']
        assert cfg['dias_contacto_lead'] == 10

    def test_guardar_config_invalid_frecuencia(self, logged_in_client):
        """Invalid frecuencia value should be ignored."""
        payload = {'frecuencia_postventa': 'invalida'}
        r = logged_in_client.post(
            '/api/google/config/guardar',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 200
        # Default value should remain
        cfg = r.get_json()['config']
        assert cfg['frecuencia_postventa'] in ('mensual', 'semestral', 'anual')

    def test_guardar_config_invalid_ranges(self, logged_in_client):
        """Out-of-range values should be rejected."""
        payload = {
            'antelacion_postventa_dias': 999,
            'dias_contacto_lead': 0,
            'antelacion_cobro_dias': -1,
        }
        r = logged_in_client.post(
            '/api/google/config/guardar',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert r.status_code == 200

        cfg = r.get_json()['config']
        # Out-of-range values should not be applied (defaults preserved)
        assert cfg['antelacion_postventa_dias'] != 999
        assert cfg['dias_contacto_lead'] != 0

    def test_guardar_config_empty_body(self, logged_in_client):
        r = logged_in_client.post(
            '/api/google/config/guardar',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_guardar_config_no_auth(self, client):
        r = client.post(
            '/api/google/config/guardar',
            data=json.dumps({'dias_contacto_lead': 5}),
            content_type='application/json',
        )
        assert r.status_code in (302, 401, 403)


class TestGoogleCalendarTestEvento:
    """POST /api/google/test-evento"""

    def test_test_evento_ok(self, logged_in_client, app):
        # Preparar una cuenta ya conectada (sin pasar por el flujo OAuth real)
        _conectar_google_directo(app)

        # El endpoint crea el evento de forma SINCRONA (a diferencia de las
        # alertas automaticas, que son fire-and-forget); se mockea la llamada
        # real a la API de Google Calendar para no depender de red/credenciales.
        with patch('app.core.calendar_service.crear_evento_prueba') as mock_crear:
            mock_crear.return_value = {'success': True, 'error': None, 'event_id': 'evt_123'}
            r = logged_in_client.post('/api/google/test-evento')

        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

    def test_test_evento_not_connected(self, logged_in_client):
        """Should fail gracefully when no Google account is connected."""
        r = logged_in_client.post('/api/google/test-evento')
        assert r.status_code == 400
        data = r.get_json()
        assert data['success'] is False
        assert 'conectada' in data['error']

    def test_test_evento_no_auth(self, client):
        r = client.post('/api/google/test-evento')
        assert r.status_code in (302, 401, 403)
