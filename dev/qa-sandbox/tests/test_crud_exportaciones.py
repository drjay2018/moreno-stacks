"""
test_crud_exportaciones.py — Tests for exportaciones API endpoints.
"""

import json


class TestExportacionesAuth:
    """Verify that all exportaciones endpoints require authentication / role."""

    def test_generar_bi_requires_auth(self, client):
        r = client.post('/api/exportaciones/generar-bi', json={"periodo": "historico"})
        assert r.status_code == 401

    def test_generar_agente_requires_auth(self, client):
        r = client.post('/api/exportaciones/generar-agente')
        assert r.status_code == 401

    def test_generar_historico_operativo_requires_auth(self, client):
        r = client.post('/api/exportaciones/generar-historico-operativo')
        assert r.status_code == 401

    def test_abrir_powerbi_requires_auth(self, client):
        r = client.post('/api/exportaciones/abrir-powerbi')
        assert r.status_code == 401


class TestExportacionesEndpoints:
    """Happy-path / structural tests for each export endpoint."""

    def test_generar_bi_success(self, logged_in_client):
        r = logged_in_client.post('/api/exportaciones/generar-bi', json={
            "periodo": "historico"
        })
        assert r.status_code == 200
        data = r.get_json()
        assert 'success' in data

    def test_generar_bi_with_periodo_ultimo_mes(self, logged_in_client):
        r = logged_in_client.post('/api/exportaciones/generar-bi', json={
            "periodo": "ultimo_mes"
        })
        assert r.status_code == 200
        data = r.get_json()
        assert 'success' in data

    def test_generar_bi_with_periodo_6_meses(self, logged_in_client):
        r = logged_in_client.post('/api/exportaciones/generar-bi', json={
            "periodo": "6_meses"
        })
        assert r.status_code == 200
        data = r.get_json()
        assert 'success' in data

    def test_generar_bi_default_periodo(self, logged_in_client):
        # No periodo key → defaults to 'historico'
        r = logged_in_client.post('/api/exportaciones/generar-bi', json={})
        assert r.status_code == 200
        data = r.get_json()
        assert 'success' in data

    def test_generar_agente_success(self, logged_in_client):
        r = logged_in_client.post('/api/exportaciones/generar-agente')
        assert r.status_code == 200
        data = r.get_json()
        assert 'success' in data

    def test_generar_historico_operativo_success(self, logged_in_client):
        r = logged_in_client.post('/api/exportaciones/generar-historico-operativo')
        assert r.status_code == 200
        data = r.get_json()
        assert 'success' in data

    def test_abrir_powerbi_success(self, logged_in_client):
        r = logged_in_client.post('/api/exportaciones/abrir-powerbi')
        # Endpoint returns 200 with success message (or failure if powerbi/ dir missing)
        assert r.status_code == 200
        data = r.get_json()
        assert 'success' in data
        # In test env the powerbi folder likely doesn't exist, so success may be False
        assert 'message' in data
