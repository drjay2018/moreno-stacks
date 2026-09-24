"""
test_crud_carga_archivos.py — Tests for carga-archivos API endpoints.
"""

import io


class TestPlantillaDownload:
    """Tests for GET /api/carga-archivos/plantilla/<modulo>."""

    def test_plantilla_requires_auth(self, client):
        r = client.get('/api/carga-archivos/plantilla/clientes')
        assert r.status_code == 401

    def test_plantilla_clientes(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/clientes')
        assert r.status_code == 200
        assert r.content_type.startswith('text/csv')
        body = r.data.decode('utf-8')
        assert 'cedula' in body
        assert 'nombre' in body
        assert 'plantilla_clientes_bi_ia.csv' in r.headers.get('Content-Disposition', '')

    def test_plantilla_empleados(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/empleados')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'codigo' in body
        assert 'posicion' in body

    def test_plantilla_constructoras(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/constructoras')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'nombre' in body
        assert 'rnc' in body

    def test_plantilla_proveedores(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/proveedores')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'razon_social' in body

    def test_plantilla_proyectos(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/proyectos')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'contraparte_id' in body

    def test_plantilla_cobros(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/cobros')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'transaccion_id' in body

    def test_plantilla_cierres(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/cierres')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'codigo' in body

    def test_plantilla_marketing(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/marketing')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'canal' in body

    def test_plantilla_compras(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/compras')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'proveedor_id' in body

    def test_plantilla_invalid_module(self, logged_in_client):
        r = logged_in_client.get('/api/carga-archivos/plantilla/NOEXISTE')
        assert r.status_code == 404
        data = r.get_json()
        assert data.get('success') is False

    def test_plantilla_csv_has_empty_data_row(self, logged_in_client):
        """Verify the CSV has a header row and one empty example row."""
        r = logged_in_client.get('/api/carga-archivos/plantilla/clientes')
        body = r.data.decode('utf-8')
        lines = body.strip().split('\n')
        assert len(lines) == 2  # header + one empty data row


class TestProcesarCSV:
    """Tests for POST /api/carga-archivos/procesar."""

    def test_procesar_requires_auth(self, client):
        r = client.post('/api/carga-archivos/procesar')
        assert r.status_code == 401

    def test_procesar_no_file(self, logged_in_client):
        r = logged_in_client.post('/api/carga-archivos/procesar')
        assert r.status_code == 400
        data = r.get_json()
        assert data.get('success') is False

    def test_procesar_invalid_filename(self, logged_in_client):
        """Non-official filename must be rejected."""
        csv_content = "cedula,nombre\n123,Juan\n"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'random_file.csv'),
        }
        r = logged_in_client.post('/api/carga-archivos/procesar', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 400
        result = r.get_json()
        assert 'Nombre de archivo no reconocido' in result.get('error', '')

    def test_procesar_non_csv_rejected(self, logged_in_client):
        data = {
            'file': (io.BytesIO(b'not csv'), 'plantilla_clientes_bi_ia.txt'),
        }
        r = logged_in_client.post('/api/carga-archivos/procesar', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 400

    def test_procesar_official_filename_empty_csv(self, logged_in_client):
        """Official filename but empty CSV content."""
        csv_content = "cedula,nombre,apellido\n"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'plantilla_clientes_bi_ia.csv'),
        }
        r = logged_in_client.post('/api/carga-archivos/procesar', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 400
        result = r.get_json()
        assert 'vacío' in result.get('error', '').lower() or result.get('success') is False

    def test_procesar_official_filename_wrong_columns(self, logged_in_client):
        """Official filename but columns don't match the template."""
        csv_content = "wrong_col1,wrong_col2\nval1,val2\n"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'plantilla_clientes_bi_ia.csv'),
        }
        r = logged_in_client.post('/api/carga-archivos/procesar', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 400
        result = r.get_json()
        assert 'columnas' in result.get('error', '').lower() or result.get('success') is False

    def test_procesar_clientes_valid_csv(self, logged_in_client):
        """Upload a correctly structured clientes template."""
        import time
        unique_id = str(int(time.time() * 1000))[-8:]
        header = "cedula,nombre,apellido,genero,fecha_nacimiento,pais,provincia,municipio,direccion,estado_civil,nacionalidad,telefono,email,via_referida,etapa_embudo,fecha_captacion,activo"
        row = f"001-{unique_id}-9,Test,User,Masculino,1990-01-01,RD,SD,SD,Calle 1,Soltero,DR,809-000-0000,test{unique_id}@test.com,directo,nuevo,2025-01-01,1"
        csv_content = f"{header}\n{row}\n"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'plantilla_clientes_bi_ia.csv'),
        }
        r = logged_in_client.post('/api/carga-archivos/procesar', data=data,
                                  content_type='multipart/form-data')
        assert r.status_code == 200
        result = r.get_json()
        assert result.get('success') is True
        assert result.get('modulo') == 'clientes'
        assert result.get('tabla_destino') == 'clientes'
        assert result.get('insertados', 0) >= 1
