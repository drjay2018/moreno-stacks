"""
conftest.py — Fixtures compartidas para todos los tests.
Usa una base de datos SQLite temporal aislada (TestConfig) cargada desde db_schema.sql.
"""

import os
import sys
import re
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-unit-tests-only')


@pytest.fixture(scope='session')
def app():
    from app import create_app
    from app.config import TestConfig
    app = create_app(TestConfig)
    app.config['TESTING'] = True
    yield app


@pytest.fixture(scope='function')
def db(app):
    import sqlite3
    from app.extensions import db as _db
    from app.config import TestConfig
    with app.app_context():
        _db.engine.dispose()  # Cerrar conexiones abiertas antes de eliminar el archivo
        path = str(TestConfig.test_db)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        raw = sqlite3.connect(path)
        try:
            schema_path = os.path.join(os.path.dirname(__file__), 'db_schema.sql')
            with open(schema_path, 'r', encoding='utf-8') as f:
                raw.executescript(f.read())
            raw.commit()
        finally:
            raw.close()
        _db.engine.dispose()
        # Replicar el estado real de produccion: tablas y columnas AlterEstate (cat_*)
        try:
            from app.core.alterestate_migration import run_migration as ae_migration
            ae_migration()
        except Exception:
            _db.session.rollback()
        # Datos base minimos (paridad con produccion donde existe proyecto id=1)
        try:
            _db.session.execute(_db.text(
                "INSERT OR IGNORE INTO contrapartes (id, nombre, activo, atributos_extra) VALUES (1, 'Contraparte DLAB', 1, '{}')"
            ))
            _db.session.execute(_db.text(
                "INSERT OR IGNORE INTO proyectos (id, nombre, contraparte_id, amenidades, activo) VALUES (1, 'Proyecto DLAB', 1, '{}', 1)"
            ))
            _db.session.commit()
        except Exception:
            _db.session.rollback()
        yield _db
        _db.session.rollback()


@pytest.fixture(scope='function')
def client(app, db):
    return app.test_client()


@pytest.fixture
def logged_in_client(client, app):
    with app.app_context():
        from werkzeug.security import generate_password_hash
        from app.extensions import db
        hashed = generate_password_hash('v1UR5KWv1wyj3TFI')
        db.session.execute(
            db.text("INSERT OR IGNORE INTO usuarios (username, password_hash, rol, activo, fecha_creacion, intentos_fallidos, debo_cambiar_password, acepto_politicas) "
                    "VALUES ('admin', :pw, 'Admin', 1, CURRENT_TIMESTAMP, 0, 0, 1)"),
            {"pw": hashed}
        )
        db.session.commit()

    r = client.get('/login')
    csrf = re.search(r'name="csrf_token".*?value="(.+?)"', r.data.decode())
    token = csrf.group(1) if csrf else ''
    client.post('/login', data={
        'username': 'admin',
        'password': 'v1UR5KWv1wyj3TFI',
        'csrf_token': token
    }, follow_redirects=True)
    return client
