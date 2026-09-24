"""
test_crud_maestros.py — CRUD tests for Maestros module.
"""

import json
import time


class TestClientesCRUD:
    def test_listar_clientes(self, logged_in_client):
        r = logged_in_client.get('/api/maestros/clientes?draw=1&start=0&length=5')
        assert r.status_code == 200
        data = r.get_json()
        assert 'data' in data

    def test_crear_cliente(self, logged_in_client):
        # Use unique cédula to avoid collisions with existing data (11 digits required)
        ts = int(time.time() * 1000) % 100000000
        unique_cedula = f'999{ts:08d}'

        r = logged_in_client.post('/api/maestros/clientes-completo', json={
            'nombre': 'Juan',
            'apellido': 'Pérez',
            'cedula': unique_cedula,
            'telefono': '809-555-1234',
            'email': 'juan@test.com',
            'fecha_nacimiento': '1990-01-15',
            'genero': 'Masculino',
            'nacionalidad': 'Dominicana',
            'estado_civil': 'Soltero',
            'pais': 'República Dominicana',
            'provincia': 'Santo Domingo',
            'municipio': 'Santo Domingo de Guzmán',
            'direccion': 'Calle Principal #123',
            'etapa_embudo': 'nuevo',
            'presupuesto_max_usd': 200000,
        })
        assert r.status_code in (200, 201)
        data = r.get_json()
        assert data.get('success') is True

        # API doesn't return id — fetch from list using cédula
        r = logged_in_client.get(f'/api/maestros/clientes?draw=1&start=0&length=50')
        clientes = r.get_json().get('data', [])
        cliente = next((c for c in clientes if c.get('cedula') == unique_cedula), None)
        assert cliente is not None, f"Cliente with cédula {unique_cedula} not found"
        cliente_id = cliente['id']

        # Update — API requires nombre and apellido
        r = logged_in_client.put(f'/api/maestros/clientes/{cliente_id}', json={
            'nombre': 'Juan Carlos',
            'apellido': 'Pérez',
            'telefono': '809-555-9999',
        })
        assert r.status_code == 200

        # Delete
        r = logged_in_client.delete(f'/api/maestros/clientes/{cliente_id}')
        assert r.status_code == 200

    def test_crear_cliente_sin_vendedor_ni_proyecto(self, logged_in_client):
        """
        Regresion: el wizard de alta de cliente (wizard_cliente.html) manda
        "" (cadena vacia), no null, para vendedor_captador_id/proyecto_interes_id/
        campana_id/referido_por_cliente_id cuando el usuario no elige nada en
        esos <select> (el caso mas comun en una instalacion nueva, sin
        empleados/proyectos aun creados). Con PRAGMA foreign_keys=ON, SQLite
        rechazaba "" como valor de FK con "FOREIGN KEY constraint failed",
        que el except IntegrityError generico reportaba enganosamente como
        "Ya existe un registro con este identificador unico" — bloqueando la
        creacion de CUALQUIER cliente en el caso mas comun.
        """
        ts = int(time.time() * 1000) % 100000000
        unique_cedula = f'997{ts:08d}'

        r = logged_in_client.post('/api/maestros/clientes-completo', json={
            'nombre': 'Sin', 'apellido': 'Vendedor',
            'cedula': unique_cedula,
            'pais': 'República Dominicana',
            'provincia': 'Santo Domingo', 'municipio': 'Santo Domingo Este',
            # Exactamente como los manda el wizard cuando no hay seleccion:
            'vendedor_captador_id': '', 'proyecto_interes_id': '',
            'campana_id': '', 'referido_por_cliente_id': '',
        })
        assert r.status_code == 200, r.get_json()
        assert r.get_json().get('success') is True

    def test_listar_clientes_auth_required(self, client):
        r = client.get('/api/maestros/clientes?draw=1&start=0&length=5')
        assert r.status_code == 401


class TestEmpleadosCRUD:
    def test_listar_empleados(self, logged_in_client):
        r = logged_in_client.get('/api/maestros/empleados?draw=1&start=0&length=5')
        assert r.status_code == 200

    def test_crear_empleado(self, logged_in_client):
        # Use unique cédula to avoid collisions (11 digits required)
        ts = int(time.time() * 1000) % 100000000
        unique_cedula = f'998{ts:08d}'

        r = logged_in_client.post('/api/maestros/empleados', json={
            'nombre': 'María García',
            'cedula': unique_cedula,
            'rol': 'Asesora',
            'nivel': 'Senior',
            'telefono': '809-555-4321',
            'email': 'maria@test.com',
            'fecha_ingreso': '2024-01-15',
            'activo': True,
        })
        assert r.status_code in (200, 201)
        data = r.get_json()
        assert data.get('success') is True

        # API doesn't return id — fetch from list using cédula
        r = logged_in_client.get('/api/maestros/empleados')
        empleados = r.get_json().get('items', [])
        emp = next((e for e in empleados if e.get('cedula') == unique_cedula), None)
        assert emp is not None, f"Empleado with cédula {unique_cedula} not found"
        emp_id = emp['id']

        # Read
        r = logged_in_client.get(f'/api/maestros/empleados/{emp_id}')
        assert r.status_code == 200

        # Update
        r = logged_in_client.put(f'/api/maestros/empleados/{emp_id}', json={
            'nombre': 'María Elena García',
            'cedula': unique_cedula,
            'rol': 'Asesora',
            'nivel': 'Senior',
        })
        assert r.status_code == 200

        # Delete
        r = logged_in_client.delete(f'/api/maestros/empleados/{emp_id}')
        assert r.status_code == 200

    def test_crear_empleado_sin_fecha_ingreso(self, logged_in_client):
        """
        Regresion: el campo "Fecha Ingreso" del formulario de empleados
        (app/templates/maestros/index.html) NO es requerido en el HTML (sin
        atributo `required`, sin asterisco en el label) y su JS manda
        `null` cuando queda vacio. Pero `entidades.fecha_ingreso` es
        NOT NULL en el esquema, y crear_empleado() no tenia ningun
        COALESCE/default — el INSERT fallaba con IntegrityError, reportado
        enganosamente como "Ya existe un registro con este identificador
        unico" para un campo que la UI presenta como opcional.
        """
        ts = int(time.time() * 1000) % 100000000
        unique_cedula = f'996{ts:08d}'

        r = logged_in_client.post('/api/maestros/empleados', json={
            'nombre': 'Sin', 'apellido': 'FechaIngreso',
            'cedula': unique_cedula,
            'rol': 'Asesor Ventas', 'nivel': 'Asesor interno - Inmobiliario',
            'fecha_ingreso': None,  # como lo manda el JS cuando el campo queda vacio
        })
        assert r.status_code == 200, r.get_json()
        assert r.get_json().get('success') is True


class TestConstructorasCRUD:
    def test_listar_constructoras(self, logged_in_client):
        r = logged_in_client.get('/api/maestros/constructoras?draw=1&start=0&length=5')
        assert r.status_code == 200

    def test_crear_constructora(self, logged_in_client):
        # Use unique name and RNC to avoid collisions (UNIQUE constraints on both)
        ts = int(time.time() * 1000) % 100000000
        unique_name = f'Constructora Test {ts}'
        unique_rnc = f'9{ts % 100000000:08d}'  # 9 digits total

        r = logged_in_client.post('/api/maestros/constructoras', json={
            'nombre': unique_name,
            'rnc': unique_rnc,
            'telefono': '809-555-0000',
            'contacto': 'Roberto Manager',
            'activo': True,
        })
        assert r.status_code in (200, 201)
        data = r.get_json()
        assert data.get('success') is True

        # API doesn't return id — fetch from list using name
        r = logged_in_client.get('/api/maestros/constructoras')
        items = r.get_json().get('items', r.get_json().get('constructoras', []))
        const = next((c for c in items if c.get('nombre') == unique_name), None)
        assert const is not None, f"Constructora '{unique_name}' not found"
        const_id = const['id']

        # Update
        r = logged_in_client.put(f'/api/maestros/constructoras/{const_id}', json={
            'nombre': f'{unique_name} Updated',
            'rnc': unique_rnc,
        })
        assert r.status_code == 200

        # Delete
        r = logged_in_client.delete(f'/api/maestros/constructoras/{const_id}')
        assert r.status_code == 200


class TestProveedoresCRUD:
    def test_listar_proveedores(self, logged_in_client):
        r = logged_in_client.get('/api/maestros/proveedores?draw=1&start=0&length=5')
        assert r.status_code == 200

    def test_crear_proveedor(self, logged_in_client):
        # Use unique RNC to avoid collisions (9 digits required)
        ts = int(time.time() * 1000) % 100000000
        unique_rnc = f'{ts:09d}'

        r = logged_in_client.post('/api/maestros/proveedores', json={
            'razon_social': f'Proveedor Test {ts}',
            'ruc': unique_rnc,
            'telefono': '809-555-1111',
            'email': 'proveedor@test.com',
            'direccion': 'Av. Principal #456',
        })
        assert r.status_code in (200, 201)
        data = r.get_json()
        assert data.get('success') is True

        # API doesn't return id — fetch from list using ruc
        r = logged_in_client.get('/api/maestros/proveedores')
        items = r.get_json().get('data', [])
        prov = next((p for p in items if p.get('ruc') == unique_rnc), None)
        assert prov is not None, f"Proveedor with RNC {unique_rnc} not found"
        prov_id = prov['id']

        # Update
        r = logged_in_client.put(f'/api/maestros/proveedores/{prov_id}', json={
            'razon_social': f'Proveedor Test {ts} Updated',
            'ruc': unique_rnc,
        })
        assert r.status_code == 200

        # Delete
        r = logged_in_client.delete(f'/api/maestros/proveedores/{prov_id}')
        assert r.status_code == 200


class TestCatalogos:
    def test_obtener_catalogos(self, logged_in_client):
        r = logged_in_client.get('/api/catalogos')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, dict)
