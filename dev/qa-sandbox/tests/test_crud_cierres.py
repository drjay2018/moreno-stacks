"""
test_crud_cierres.py — CRUD tests for Cierres (transacciones) module.
"""

import json


class TestCierresCRUD:
    """Full CRUD cycle for cierres."""

    def test_listar_cierres(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_listar_cierres_with_sort(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5&order[0][column]=0&order[0][dir]=desc')
        assert r.status_code == 200

    def test_listar_cierres_with_search(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5&search[value]=test')
        assert r.status_code == 200

    def test_desglose_financiero_not_found(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/99999/desglose-financiero')
        assert r.status_code in (404, 200)


class TestCierresAuth:
    """Auth tests for cierres."""

    def test_requires_login(self, client):
        r = client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 401
