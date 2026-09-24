"""
test_crud_incidentes_marketing.py — CRUD tests for Incidentes and Marketing modules.
"""

import json
import time


class TestIncidentesCRUD:
    def test_listar_incidentes(self, logged_in_client):
        r = logged_in_client.get('/api/incidentes/incidentes?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_crear_incidente(self, logged_in_client):
        r = logged_in_client.post('/api/incidentes', json={
            'tipo': 'Test Incident',
            'descripcion': 'Test description for incident',
            'fecha_reporte': '2026-08-24',
            'severidad': 'Baja',
            'nivel': 1,
            'area_responsable': 'Ventas',
        })
        assert r.status_code in (200, 201)
        data = r.get_json()
        assert data.get('success') is True
        inc_id = data.get('id') or data.get('incidente_id')
        assert inc_id is not None

        # Update — API requires 'tipo' and 'descripcion' on PUT
        r = logged_in_client.put(f'/api/incidentes/{inc_id}', json={
            'tipo': 'Test Incident',
            'descripcion': 'Updated description',
            'severidad': 'Media',
            'nivel': 1,
            'area_responsable': 'Ventas',
        })
        assert r.status_code == 200

        # Close
        r = logged_in_client.post(f'/api/incidentes/{inc_id}/cerrar', json={
            'fecha_resolucion': '2026-08-24',
            'comentario_resolucion': 'Resuelto exitosamente',
        })
        assert r.status_code == 200

    def test_listar_incidentes_auth_required(self, client):
        r = client.get('/api/incidentes/incidentes?draw=1&start=0&length=5')
        assert r.status_code == 401


class TestMarketingCRUD:
    def test_listar_campanas(self, logged_in_client):
        r = logged_in_client.get('/api/marketing/campanas?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_crear_campana(self, logged_in_client):
        # Use unique name to avoid collisions
        unique_name = f'Campaña Test {int(time.time() * 1000)}'
        r = logged_in_client.post('/api/marketing/campanas', json={
            'nombre': unique_name,
            'canal': 'Facebook',
            'fecha_inicio': '2026-08-01',
            'monto_invertido': 5000,
            'activo': True,
            'impresiones': 10000,
            'clics': 500,
            'leads_generados': 50,
        })
        assert r.status_code in (200, 201)
        data = r.get_json()
        assert data.get('success') is True

        # API doesn't return id — fetch it from the list endpoint
        r = logged_in_client.get('/api/marketing/campanas')
        campanas = r.get_json().get('items', [])
        camp = next((c for c in campanas if c.get('nombre') == unique_name), None)
        assert camp is not None, f"Campaña '{unique_name}' not found in list"
        camp_id = camp['id']

        # Update
        r = logged_in_client.put(f'/api/marketing/campanas/{camp_id}', json={
            'nombre': f'{unique_name} Updated',
            'monto_invertido': 7500,
        })
        assert r.status_code == 200

        # Delete
        r = logged_in_client.delete(f'/api/marketing/campanas/{camp_id}')
        assert r.status_code == 200

    def test_listar_campanas_auth_required(self, client):
        r = client.get('/api/marketing/campanas?draw=1&start=0&length=5')
        assert r.status_code == 401
