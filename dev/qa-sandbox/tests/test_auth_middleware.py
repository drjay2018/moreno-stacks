"""
test_auth_middleware.py — Tests for auth middleware decorators.
"""

import re


class TestRequiereLogin:
    """Tests for @requiere_login decorator."""

    def test_redirect_when_not_logged_in(self, client):
        r = client.get('/logout')
        # logout doesn't use requiere_login, but let's test via API
        r = client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 401
        data = r.get_json()
        assert data['success'] is False
        assert 'autenticación' in data['error'].lower()

    def test_allowed_when_logged_in(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 200


class TestRequiereRol:
    """Tests for @requiere_rol decorator."""

    def test_admin_accesses_admin_endpoint(self, logged_in_client):
        # Admin should be able to access any role-restricted endpoint
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 200

    def test_unauthenticated_gets_401(self, client):
        r = client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 401
