"""
test_crud_usuarios_config.py — CRUD tests for Usuarios and Configuracion modules.
"""

import json
import time


class TestUsuariosCRUD:
    def test_listar_usuarios(self, logged_in_client):
        r = logged_in_client.get('/api/usuarios')
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('success') is True
        assert 'items' in data

    def test_crear_usuario(self, logged_in_client):
        # Use unique username to avoid UNIQUE constraint collisions
        ts = int(time.time() * 1000) % 10000000
        unique_username = f'test_user_{ts}'

        r = logged_in_client.post('/api/usuarios', json={
            'username': unique_username,
            'password': 'TestPass123!',
            'rol': 'Asistente',
        })
        assert r.status_code in (200, 201)
        data = r.get_json()
        assert data.get('success') is True

        # API doesn't return id — fetch from list using username
        r = logged_in_client.get('/api/usuarios')
        usuarios = r.get_json().get('items', [])
        user = next((u for u in usuarios if u.get('username') == unique_username), None)
        assert user is not None, f"Usuario '{unique_username}' not found"
        user_id = user['id']

        # Update
        r = logged_in_client.put(f'/api/usuarios/{user_id}', json={
            'rol': 'Gerente Comercial',
        })
        assert r.status_code == 200

        # Delete
        r = logged_in_client.delete(f'/api/usuarios/{user_id}')
        assert r.status_code == 200

    def test_cannot_delete_super_admin(self, logged_in_client):
        r = logged_in_client.delete('/api/usuarios/1')
        assert r.status_code in (400, 403, 200)
        data = r.get_json()
        if r.status_code == 200:
            assert data.get('success') is False

    def test_listar_usuarios_auth_required(self, client):
        r = client.get('/api/usuarios')
        assert r.status_code == 401


class TestConfiguracionCRUD:
    def test_listar_kpis(self, logged_in_client):
        r = logged_in_client.get('/api/configuracion/kpis')
        assert r.status_code == 200

    def test_listar_matriz_comisiones(self, logged_in_client):
        r = logged_in_client.get('/api/configuracion/matriz_comisiones')
        assert r.status_code == 200
        data = r.get_json()
        assert 'items' in data

    def test_listar_auditoria(self, logged_in_client):
        r = logged_in_client.get('/api/configuracion/auditoria')
        assert r.status_code == 200

    def test_configuracion_auth_required(self, client):
        r = client.get('/api/configuracion/kpis')
        assert r.status_code == 401


class TestKPIs:
    def test_obtener_kpis(self, logged_in_client):
        r = logged_in_client.get('/api/kpis/resumen?periodo=Este%20mes')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, dict)

    def test_kpis_auth_required(self, client):
        r = client.get('/api/kpis/resumen?periodo=Este%20mes')
        assert r.status_code == 401

    def test_kpi_comisiones_pagadas_refleja_pagos_reales(self, logged_in_client, app, db):
        """
        Regresion: comisiones_api.pagar_comision() guarda estado = 'pagado'
        (masculino), pero kpis_api.py comparaba contra 'pagada' (femenino).
        Como nunca coincidian, "Comisiones Pagadas" marcaba siempre US$ 0 sin
        importar cuanto se hubiera pagado de verdad, y "Comisiones
        Pendientes" nunca bajaba aunque todo estuviera liquidado. Se
        reproduce insertando una comision ya en estado 'pagado' (el valor
        real que usa el codigo de produccion) y verificando que el KPI la
        cuente como pagada, no como pendiente.
        """
        from sqlalchemy import text as _text
        # Reutiliza los endpoints reales (ya probados) para crear un empleado
        # y un cierre con su comision de hito 1 auto-generada, en vez de
        # reconstruir a mano el esquema completo de "transacciones" (tiene
        # muchas columnas NOT NULL sin default que crear_cierre() sí rellena).
        ts = int(time.time() * 1000) % 100000000
        r_emp = logged_in_client.post('/api/maestros/empleados', json={
            'nombre': 'KPI', 'apellido': 'Test', 'cedula': f'994{ts:08d}',
            'rol': 'Asesor Ventas', 'nivel': 'Asesor interno - Inmobiliario',
        })
        assert r_emp.get_json().get('success') is True
        empleados = logged_in_client.get('/api/maestros/empleados').get_json().get('items', [])
        entidad_id = next(e['id'] for e in empleados if e['cedula'] == f'994{ts:08d}')

        r_cli = logged_in_client.post('/api/maestros/clientes-completo', json={
            'nombre': 'KPI', 'apellido': 'Cliente', 'cedula': f'993{ts:08d}',
            'pais': 'República Dominicana',
        })
        assert r_cli.get_json().get('success') is True, r_cli.get_json()
        clientes = logged_in_client.get('/api/maestros/clientes?draw=1&start=0&length=200').get_json()['data']
        cliente_id = next(c['id'] for c in clientes if c['cedula'] == f'993{ts:08d}')

        with app.app_context():
            db.session.execute(_text("INSERT OR IGNORE INTO cat_gastos_pub (id, nombre) VALUES (1, 'SI')"))
            db.session.commit()

        r_cierre = logged_in_client.post('/api/cierres', json={
            'proyecto_id': 1, 'entidad_id': entidad_id, 'cliente_id': cliente_id,
            'monto': 100000, 'pct_comision': 5, 'gastos_pub_id': 1, 'origen_prospecto': 'propio',
        })
        assert r_cierre.get_json().get('success') is True, r_cierre.get_json()

        with app.app_context():
            # Forzar el estado exacto que usa comisiones_api.pagar_comision()
            # en produccion, sin pasar por sus validaciones de NCF/banco
            # (irrelevantes para esta regresion puntual de la KPI).
            db.session.execute(_text(
                "UPDATE comisiones_pagos SET estado = 'pagado', fecha_pago = CURRENT_DATE "
                "WHERE entidad_id = :eid"
            ), {"eid": entidad_id})
            db.session.commit()
            monto_pagado = db.session.execute(_text(
                "SELECT monto FROM comisiones_pagos WHERE entidad_id = :eid"
            ), {"eid": entidad_id}).scalar()

        r = logged_in_client.get('/api/kpis/resumen?periodo=Historico')
        assert r.status_code == 200
        kpis = {k['id']: k for k in r.get_json()['kpis']}
        monto_esperado = f"{int(round(monto_pagado)):,}"
        assert monto_esperado in kpis['comisiones_pagadas']['valor'], kpis['comisiones_pagadas']
        # La comision pagada NO debe seguir contando como pendiente.
        assert kpis['comisiones_pendientes']['valor'] == 'US$ 0', kpis['comisiones_pendientes']


class TestAlertas:
    def test_obtener_alertas(self, logged_in_client):
        r = logged_in_client.get('/api/alertas/dashboard')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, dict)

    def test_alertas_auth_required(self, client):
        r = client.get('/api/alertas/dashboard')
        assert r.status_code == 401
