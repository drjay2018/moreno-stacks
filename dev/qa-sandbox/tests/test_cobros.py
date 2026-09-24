"""
test_cobros.py — Tests for cobros (payments/billing) endpoints.
"""


class TestCobrosEndpoints:
    """Tests for the cobros API."""

    def test_listar_cobros_requires_auth(self, client):
        r = client.get('/api/cobros/cobros?draw=1&start=0&length=5')
        assert r.status_code == 401

    def test_listar_cobros_empty(self, logged_in_client):
        r = logged_in_client.get('/api/cobros/cobros?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data
        assert isinstance(data['data'], list)

    def test_cobros_with_search(self, logged_in_client):
        r = logged_in_client.get('/api/cobros/cobros?draw=1&start=0&length=5&search[value]=test')
        assert r.status_code == 200
