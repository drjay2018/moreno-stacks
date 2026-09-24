"""
test_crud_compras.py — CRUD tests for Compras (purchases) module.
"""

import json


class TestComprasCRUD:
    """Full CRUD cycle for compras."""

    def test_listar_compras(self, logged_in_client):
        r = logged_in_client.get('/api/compras/compras?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_listar_compras_with_search(self, logged_in_client):
        r = logged_in_client.get('/api/compras/compras?draw=1&start=0&length=5&search[value]=test')
        assert r.status_code == 200

    def test_listar_compras_with_sort(self, logged_in_client):
        r = logged_in_client.get('/api/compras/compras?draw=1&start=0&length=5&order[0][column]=0&order[0][dir]=desc')
        assert r.status_code == 200


class TestComprasAuth:
    """Auth tests for compras."""

    def test_requires_login(self, client):
        r = client.get('/api/compras/compras?draw=1&start=0&length=5')
        assert r.status_code == 401
