"""
test_clarodom.py — Smoke tests for the ClaroDom integration API.
"""


class TestClaroDomConfig:
    def test_status_auth_required(self, client):
        r = client.get('/api/clarodom/status')
        assert r.status_code == 401

    def test_status_sin_configurar(self, logged_in_client):
        r = logged_in_client.get('/api/clarodom/status')
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('success') is True
        assert data.get('has_config') is False
        assert data.get('connected') is False

    def test_save_config_rechaza_base_url_sin_esquema(self, logged_in_client):
        r = logged_in_client.post('/api/clarodom/config', json={
            'base_url': 'no-es-una-url',
        })
        assert r.status_code == 400
        data = r.get_json()
        assert data.get('success') is False

    def test_save_config_rechaza_auth_scheme_invalido(self, logged_in_client):
        r = logged_in_client.post('/api/clarodom/config', json={
            'base_url': 'https://api.clarodom.example',
            'auth_scheme': 'no-valido',
        })
        assert r.status_code == 400
        data = r.get_json()
        assert data.get('success') is False

    def test_save_config_exitoso_actualiza_status(self, logged_in_client):
        r = logged_in_client.post('/api/clarodom/config', json={
            'base_url': 'https://api.clarodom.example',
            'auth_scheme': 'bearer',
            'test_path': '/v1/ping',
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('success') is True

        r = logged_in_client.get('/api/clarodom/status')
        data = r.get_json()
        assert data.get('has_config') is True
        # Sin haber ejecutado /test todavia, la conexion no debe darse por buena
        assert data.get('connected') is False

        r = logged_in_client.get('/api/clarodom/config')
        data = r.get_json()
        assert data.get('config', {}).get('base_url') == 'https://api.clarodom.example'
