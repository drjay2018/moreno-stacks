"""
test_cierres.py — Tests for cierres (transacciones) endpoints.
"""


class TestCierresEndpoints:
    """Tests for the cierres API."""

    def test_listar_cierres_requires_auth(self, client):
        r = client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 401

    def test_listar_cierres_empty(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data
        assert isinstance(data['data'], list)

    def test_listar_cierres_with_filters(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5&search[value]=test')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_cierres_sort_columns(self, logged_in_client):
        r = logged_in_client.get('/api/cierres/cierres?draw=1&start=0&length=5&order[0][column]=0&order[0][dir]=asc')
        assert r.status_code == 200
