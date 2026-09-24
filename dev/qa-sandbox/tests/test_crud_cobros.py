"""
test_crud_cobros.py — CRUD tests for Cobros (payments/billing) module.
"""

import json


class TestCobrosCRUD:
    """Full CRUD cycle for cobros."""

    def test_listar_cobros(self, logged_in_client):
        r = logged_in_client.get('/api/cobros/cobros?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_listar_cobros_with_search(self, logged_in_client):
        r = logged_in_client.get('/api/cobros/cobros?draw=1&start=0&length=5&search[value]=test')
        assert r.status_code == 200

    def test_listar_cobros_with_sort(self, logged_in_client):
        r = logged_in_client.get('/api/cobros/cobros?draw=1&start=0&length=5&order[0][column]=0&order[0][dir]=desc')
        assert r.status_code == 200


class TestCobrosAuth:
    """Auth tests for cobros."""

    def test_requires_login(self, client):
        r = client.get('/api/cobros/cobros?draw=1&start=0&length=5')
        assert r.status_code == 401
