"""
test_crud_comisiones.py — CRUD tests for Comisiones module.
Covers: listar, aprobar, pagar + auth + edge cases.
"""

import json


class TestComisionesListar:
    """Tests for GET /api/comisiones/comisiones."""

    def test_listar_comisiones(self, logged_in_client):
        r = logged_in_client.get('/api/comisiones/comisiones?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_listar_comisiones_without_dt(self, logged_in_client):
        """Non-DataTable request returns items/comisiones keys."""
        r = logged_in_client.get('/api/comisiones/comisiones')
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('success') is True
        assert 'items' in data
        assert 'comisiones' in data

    def test_listar_comisiones_with_search(self, logged_in_client):
        r = logged_in_client.get(
            '/api/comisiones/comisiones?draw=1&start=0&length=5&search[value]=test'
        )
        assert r.status_code == 200

    def test_listar_comisiones_with_sort(self, logged_in_client):
        r = logged_in_client.get(
            '/api/comisiones/comisiones?draw=1&start=0&length=5'
            '&order[0][column]=0&order[0][dir]=desc'
        )
        assert r.status_code == 200

    def test_listar_comisiones_filters_cancelado(self, logged_in_client):
        """Cancelled commissions should be excluded from results."""
        r = logged_in_client.get('/api/comisiones/comisiones?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        for item in data.get('data', []):
            assert item.get('estado') != 'cancelado'


class TestComisionesAprobar:
    """Tests for POST /api/comisiones/<id>/aprobar."""

    def test_aprobar_requiere_rol_admin(self, client):
        """Unauthenticated request must return 401."""
        r = client.post('/api/comisiones/1/aprobar')
        assert r.status_code == 401

    def test_aprobar_comision_no_existente(self, logged_in_client):
        """Approving a non-existent commission returns 404."""
        r = logged_in_client.post('/api/comisiones/99999/aprobar')
        assert r.status_code == 404
        data = r.get_json()
        assert data.get('success') is False


class TestComisionesPagar:
    """Tests for POST /api/comisiones/<id>/pagar."""

    def test_pagar_requiere_auth(self, client):
        """Unauthenticated request must return 401."""
        r = client.post('/api/comisiones/1/pagar')
        assert r.status_code == 401

    def test_pagar_comision_no_encontrada(self, logged_in_client):
        """Paying a non-existent commission returns 404."""
        r = logged_in_client.post('/api/comisiones/99999/pagar')
        assert r.status_code == 404
        data = r.get_json()
        assert data.get('success') is False
        assert 'no encontrada' in data.get('error', '').lower()


class TestComisionesAuth:
    """Auth tests — verify all endpoints reject unauthenticated users."""

    def test_listar_requires_login(self, client):
        r = client.get('/api/comisiones/comisiones?draw=1&start=0&length=5')
        assert r.status_code == 401

    def test_aprobar_requires_login(self, client):
        r = client.post('/api/comisiones/1/aprobar')
        assert r.status_code == 401

    def test_pagar_requires_login(self, client):
        r = client.post('/api/comisiones/1/pagar')
        assert r.status_code == 401


class TestComisionesEdgeCases:
    """Edge cases for comisiones endpoints."""

    def test_listar_draw_parameter_defaults(self, logged_in_client):
        """Missing draw param should still return a valid response."""
        r = logged_in_client.get('/api/comisiones/comisiones')
        assert r.status_code == 200
        data = r.get_json()
        assert 'comisiones' in data

    def test_pagar_comision_invalid_id_returns_404(self, logged_in_client):
        """Paying with a negative or zero ID should not crash."""
        r = logged_in_client.post('/api/comisiones/0/pagar')
        assert r.status_code == 404
        data = r.get_json()
        assert data.get('success') is False

    def test_aprobar_with_get_fails(self, logged_in_client):
        """GET on approve endpoint should return 405 Method Not Allowed."""
        r = logged_in_client.get('/api/comisiones/1/aprobar')
        assert r.status_code == 405

    def test_pagar_with_get_fails(self, logged_in_client):
        """GET on pay endpoint should return 405 Method Not Allowed."""
        r = logged_in_client.get('/api/comisiones/1/pagar')
        assert r.status_code == 405

    def test_pagar_with_non_json_body(self, logged_in_client):
        """Pay endpoint with empty body should still process
        (no request body is needed — it's a state-change action)."""
        r = logged_in_client.post(
            '/api/comisiones/99999/pagar',
            content_type='application/x-www-form-urlencoded',
            data=''
        )
        assert r.status_code == 404
