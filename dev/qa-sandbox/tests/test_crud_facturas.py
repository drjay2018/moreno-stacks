"""
test_crud_facturas.py — Tests for facturas API endpoints.
"""

import io


class TestFacturasList:
    """Tests for GET /api/facturas/ listing."""

    def test_listar_facturas_requires_auth(self, client):
        r = client.get('/api/facturas/')
        assert r.status_code == 401

    def test_listar_facturas_datatables_format(self, logged_in_client):
        r = logged_in_client.get('/api/facturas/?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_listar_facturas_empty_list(self, logged_in_client):
        r = logged_in_client.get('/api/facturas/')
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('success') is True
        assert isinstance(data.get('items', []), list)


class TestFacturasUpload:
    """Tests for POST /api/facturas/upload."""

    def test_upload_requires_auth(self, client):
        r = client.post('/api/facturas/upload')
        assert r.status_code == 401

    def test_upload_no_file(self, logged_in_client):
        r = logged_in_client.post('/api/facturas/upload')
        assert r.status_code == 400
        data = r.get_json()
        assert data.get('success') is False

    def test_upload_empty_filename(self, logged_in_client):
        data = {
            'file': (io.BytesIO(b''), ''),
            'compra_id': '1',
            'numero_factura': 'FAC-001',
        }
        r = logged_in_client.post('/api/facturas/upload', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 400

    def test_upload_non_pdf_rejected(self, logged_in_client):
        data = {
            'file': (io.BytesIO(b'not a pdf'), 'test.txt'),
            'compra_id': '1',
            'numero_factura': 'FAC-001',
        }
        r = logged_in_client.post('/api/facturas/upload', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 400
        result = r.get_json()
        assert 'PDF' in result.get('error', '')

    def test_upload_no_compra_id(self, logged_in_client):
        data = {
            'file': (io.BytesIO(b'%PDF-1.4 fake'), 'factura.pdf'),
            'numero_factura': 'FAC-001',
        }
        r = logged_in_client.post('/api/facturas/upload', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 400
        result = r.get_json()
        assert 'compra' in result.get('error', '').lower()


class TestFacturasView:
    """Tests for GET /api/facturas/view/<fid>."""

    def test_ver_factura_requires_auth(self, client):
        r = client.get('/api/facturas/view/999999')
        assert r.status_code == 401

    def test_ver_factura_not_found(self, logged_in_client):
        r = logged_in_client.get('/api/facturas/view/999999')
        assert r.status_code == 404
