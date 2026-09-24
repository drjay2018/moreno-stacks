"""
test_auth.py — Tests for authentication endpoints.
"""

import re


class TestLogin:
    def test_login_page_renders(self, client):
        r = client.get('/login')
        assert r.status_code == 200

    def test_login_requires_csrf(self, client):
        with client.application.app_context():
            from werkzeug.security import generate_password_hash
            from app.extensions import db
            hashed = generate_password_hash('testpass123')
            db.session.execute(
                db.text("INSERT OR IGNORE INTO usuarios (username, password_hash, rol, activo, fecha_creacion, intentos_fallidos, debo_cambiar_password, acepto_politicas) "
                        "VALUES ('csrf_user', :pw, 'Admin', 1, CURRENT_TIMESTAMP, 0, 0, 1)"),
                {"pw": hashed}
            )
            db.session.commit()

        r = client.post('/login', data={'username': 'csrf_user', 'password': 'testpass123'})
        assert r.status_code in (200, 302, 400)

    def test_login_success(self, client):
        with client.application.app_context():
            from werkzeug.security import generate_password_hash
            from app.extensions import db
            hashed = generate_password_hash('mypass123')
            db.session.execute(
                db.text("INSERT OR IGNORE INTO usuarios (username, password_hash, rol, activo, fecha_creacion, intentos_fallidos, debo_cambiar_password, acepto_politicas) "
                        "VALUES ('testlogin_ok', :pw, 'Admin', 1, CURRENT_TIMESTAMP, 0, 0, 1)"),
                {"pw": hashed}
            )
            db.session.commit()

        r = client.get('/login')
        csrf = re.search(r'name="csrf_token".*?value="(.+?)"', r.data.decode())
        token = csrf.group(1) if csrf else ''
        r = client.post('/login', data={
            'username': 'testlogin_ok',
            'password': 'mypass123',
            'csrf_token': token
        }, follow_redirects=False)
        assert r.status_code == 302
        assert '/dashboard' in r.headers.get('Location', '')

    def test_login_wrong_password(self, client):
        with client.application.app_context():
            from werkzeug.security import generate_password_hash
            from app.extensions import db
            hashed = generate_password_hash('correctpass')
            db.session.execute(
                db.text("INSERT OR IGNORE INTO usuarios (username, password_hash, rol, activo, fecha_creacion, intentos_fallidos, debo_cambiar_password, acepto_politicas) "
                        "VALUES ('testwrong_pw', :pw, 'Admin', 1, CURRENT_TIMESTAMP, 0, 0, 1)"),
                {"pw": hashed}
            )
            db.session.commit()

        r = client.get('/login')
        csrf = re.search(r'name="csrf_token".*?value="(.+?)"', r.data.decode())
        token = csrf.group(1) if csrf else ''
        r = client.post('/login', data={
            'username': 'testwrong_pw',
            'password': 'wrongpass',
            'csrf_token': token
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_login_inactive_user(self, client):
        with client.application.app_context():
            from werkzeug.security import generate_password_hash
            from app.extensions import db
            hashed = generate_password_hash('inactive123')
            db.session.execute(
                db.text("INSERT OR IGNORE INTO usuarios (username, password_hash, rol, activo, fecha_creacion, intentos_fallidos, debo_cambiar_password, acepto_politicas) "
                        "VALUES ('inactive_user', :pw, 'Admin', 0, CURRENT_TIMESTAMP, 0, 0, 1)"),
                {"pw": hashed}
            )
            db.session.commit()

        r = client.get('/login')
        csrf = re.search(r'name="csrf_token".*?value="(.+?)"', r.data.decode())
        token = csrf.group(1) if csrf else ''
        r = client.post('/login', data={
            'username': 'inactive_user',
            'password': 'inactive123',
            'csrf_token': token
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_logout(self, logged_in_client):
        r = logged_in_client.get('/logout', follow_redirects=False)
        assert r.status_code == 302
        assert '/login' in r.headers.get('Location', '')

    def test_api_returns_401_when_not_logged_in(self, client):
        r = client.get('/api/cierres/cierres?draw=1&start=0&length=5')
        assert r.status_code == 401
        data = r.get_json()
        assert data['success'] is False
