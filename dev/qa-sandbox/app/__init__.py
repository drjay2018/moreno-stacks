"""
app/__init__.py — Application Factory de Flask con middleware de Seguridad OWASP.
Proteccion reforzada: PRAGMAs SQLite seguros, integridad de DB, headers OWASP.
Compatible con Power BI: DB sin cifrar a nivel de archivo.
"""

import os
import logging
from datetime import datetime
from flask import Flask
from app.config import Config
from app.extensions import db
from app.core.auth_middleware import _is_user_locked
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _inicializar_esquema(db_path):
    """Construye el esquema canonico (db_schema.sql) en una base recien creada.

    Es idempotente (CREATE TABLE IF NOT EXISTS) para soportar instalaciones
    parciales sin plantilla y corregir el arranque desde cero de la app.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path
    schema_path = Path(__file__).resolve().parent.parent / "db_schema.sql"
    if not schema_path.exists():
        logging.error("No se encontro db_schema.sql para inicializar la base.")
        return
    consultas = schema_path.read_text(encoding="utf-8")
    con = _sqlite3.connect(db_path)
    try:
        for sentencia in consultas.split(";"):
            sentencia = sentencia.strip()
            if not sentencia or sentencia.startswith("--"):
                continue
            if sentencia.lower().startswith("create table"):
                sentencia = sentencia.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
            con.execute(sentencia)
        con.commit()
        logging.info(f"Esquema canonico inicializado en: {db_path}")
    except Exception as e:
        con.rollback()
        logging.error(f"Error inicializando esquema base: {e}")
    finally:
        con.close()


import sys
def create_app(config_class=Config):
    if getattr(sys, 'frozen', False):
        template_folder = os.path.join(sys._MEIPASS, 'app', 'templates')
        static_folder = os.path.join(sys._MEIPASS, 'app', 'static')
        app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    else:
        app = Flask(__name__)
    app.config.from_object(config_class)

    # Crear la carpeta de la base de datos si no existe
    db_path = app.config.get("SQLALCHEMY_DATABASE_URI", "").replace("sqlite:///", "")
    es_test = app.config.get("TESTING", False)
    if db_path and not es_test:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(db_dir, exist_ok=True)

        # Si la base de datos no existe o esta vacia, copiar la plantilla
        # (solo archivos inexistentes o de 0 bytes; nunca sobrescribir una DB
        # pequena pero valida, que perderia los datos del usuario)
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            from app.config import TEMPLATE_DB_PATH
            import shutil
            if TEMPLATE_DB_PATH.exists():
                try:
                    shutil.copy2(TEMPLATE_DB_PATH, db_path)
                    logging.info(f"Base de datos plantilla copiada a: {db_path}")
                except Exception as e:
                    logging.error(f"Error copiando base de datos plantilla: {e}")
            else:
                logging.warning(f"No se encontro la base de datos plantilla en: {TEMPLATE_DB_PATH}")

    # Inicializar extensiones
    db.init_app(app)
    csrf = CSRFProtect(app)

    # Rate limiting (sin limites globales por defecto, para no romper la app existente)
    limiter = Limiter(
        get_remote_address,
        app=app,
        storage_uri=app.config.get("RATE_LIMIT_STORAGE_URI", "memory://"),
        default_limits=[],
        enabled=app.config.get("RATE_LIMIT_ENABLED", True),
    )
    # IMPORTANTE: flask-limiter no guarda una referencia fuerte al objeto
    # Limiter en app.extensions en esta version. Si "limiter" queda solo como
    # variable local de create_app(), Python la recolecta como basura en
    # cuanto create_app() retorna, y los decoradores @limiter.limit(...) ya
    # aplicados quedan con una referencia debil muerta a su propio Limiter —
    # la siguiente peticion revienta con
    # "ReferenceError: weakly-referenced object no longer exists". Se guarda
    # una referencia fuerte en la propia app para que viva mientras la app viva.
    app.limiter = limiter

    # ─── PRAGMAs de SQLite reforzados ────────────────────────────────────────
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    import sqlite3

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            # Rendimiento
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            # Integridad
            cursor.execute("PRAGMA foreign_keys=ON")
            # Seguridad reforzada
            cursor.execute("PRAGMA secure_delete=OFF")  # No borrar datos en DELETE (auditoria)
            cursor.execute("PRAGMA temp_store=MEMORY")  # Temp tables en memoria
            cursor.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
            cursor.execute("PRAGMA busy_timeout=5000")  # 5s espera si DB bloqueada
            cursor.close()

    # ─── Proteccion Global de Rutas ──────────────────────────────────────────
    from flask import request, session, redirect, url_for, jsonify

    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": f"{e.name}."}), e.code
            return e.get_response()
        if request.path.startswith("/api/"):
            app.logger.error("Error no controlado en %s: %s", request.path, repr(e), exc_info=True)
            return jsonify({"success": False, "error": "Error interno del servidor."}), 500
        from flask import abort
        abort(500)

    @app.before_request
    def check_login():
        # Excepciones (oauth_autorizar y estado_conexion manejan datos sensibles
        # y SI requieren sesion; solo oauth_callback queda exenta porque Google
        # no reenvia la cookie de sesion en la redireccion del callback)
        if request.endpoint and (
            request.endpoint.startswith('auth_views.') or
            request.endpoint == 'static' or
            request.endpoint == 'google_calendar_api.oauth_callback'
        ):
            return

        usuario = session.get("usuario")
        if not usuario:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Autenticación requerida."}), 401
            return redirect(url_for("auth_views.login"))

        # Verificar bloqueo de cuenta (reutiliza la misma logica de auth_middleware)
        if _is_user_locked(usuario.get("id", 0)):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Autenticación requerida."}), 401
            return redirect(url_for("auth_views.login"))

        # Forzar cambio de password obligatorio: no se permite navegar a otras
        # rutas hasta completarlo (antes se podia evadir yendo a otra URL)
        if usuario.get("debo_cambiar_password") and request.endpoint != 'auth_views.cambiar_password_obligatorio':
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Debe cambiar su contrasena antes de continuar."}), 403
            return redirect(url_for("auth_views.cambiar_password_obligatorio"))

        # TODO(seguridad): forzar tambien la aceptacion de politicas
        # (usuario.get("acepto_politicas") == False) antes de usar el resto de
        # la app, igual que con debo_cambiar_password. No se implementa aqui
        # porque no existe todavia una vista/pagina dedicada a mostrar y
        # aceptar las politicas (solo existe el endpoint API
        # usuarios_api.aceptar_politicas, sin una ruta HTML que la sirva) —
        # bloquear sin una pantalla real dejaria a los usuarios sin salida.
        # Cuando exista esa vista, exceptuarla aqui y anadir el mismo patron
        # de redirect/403 usado arriba para debo_cambiar_password.

    # ─── Context Processor (White-label) ─────────────────────────────────────
    @app.context_processor
    def inject_global_data():
        try:
            from sqlalchemy import text
            rows = db.session.execute(text("SELECT clave, valor FROM app_config")).mappings().all()
            app_data = {row["clave"]: row["valor"] for row in rows}
            return {
                "dlab_empresa": app_data.get("empresa_nombre", "DLab"),
                "dlab_gerente": app_data.get("empresa_gerente", ""),
                "dlab_telefono": app_data.get("empresa_telefono", ""),
                "dlab_correo": app_data.get("empresa_correo", "")
            }
        except Exception:
            return {
                "dlab_empresa": "DLab",
                "dlab_gerente": "",
                "dlab_telefono": "",
                "dlab_correo": ""
            }

    # ─── Security Headers OWASP ──────────────────────────────────────────────
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.datatables.net https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.datatables.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
        return response

    # ─── Registrar Blueprints de API (JSON) ──────────────────────────────────
    from app.api.catalogos_api import catalogos_api_bp
    from app.api.kpis_api import kpis_api_bp
    from app.api.maestros_api import maestros_api_bp
    from app.api.cierres_api import cierres_api_bp
    from app.api.cobros_api import cobros_api_bp
    from app.api.marketing_api import marketing_api_bp
    from app.api.exportaciones_api import exportaciones_api_bp
    from app.api.configuracion_api import configuracion_api_bp
    from app.api.carga_archivos_api import carga_archivos_api_bp
    from app.api.alertas_api import alertas_api_bp
    from app.api.facturas_api import facturas_api_bp
    from app.api.google_calendar_api import google_calendar_api_bp
    from app.api.usuarios_api import usuarios_api_bp
    from app.api.compras_api import compras_api_bp
    from app.api.comisiones_api import comisiones_api_bp
    from app.api.incidentes_api import incidentes_api_bp
    from app.api.alterestate_api import alterestate_api_bp
    from app.api.clarodom_api import clarodom_api_bp

    app.register_blueprint(catalogos_api_bp)
    app.register_blueprint(kpis_api_bp)
    app.register_blueprint(maestros_api_bp)
    app.register_blueprint(cierres_api_bp)
    app.register_blueprint(cobros_api_bp)
    app.register_blueprint(marketing_api_bp)
    app.register_blueprint(exportaciones_api_bp)
    app.register_blueprint(configuracion_api_bp)
    app.register_blueprint(carga_archivos_api_bp)
    app.register_blueprint(alertas_api_bp)
    app.register_blueprint(facturas_api_bp)
    app.register_blueprint(google_calendar_api_bp)
    app.register_blueprint(usuarios_api_bp)
    app.register_blueprint(compras_api_bp)
    app.register_blueprint(comisiones_api_bp)
    app.register_blueprint(incidentes_api_bp)
    app.register_blueprint(alterestate_api_bp)
    app.register_blueprint(clarodom_api_bp)

    # Eximir blueprints de API de CSRF (usan autenticacion por sesion, no formularios HTML)
    for _api_bp in (
        catalogos_api_bp, kpis_api_bp, maestros_api_bp, cierres_api_bp,
        cobros_api_bp, marketing_api_bp, exportaciones_api_bp, configuracion_api_bp,
        carga_archivos_api_bp, alertas_api_bp, facturas_api_bp, google_calendar_api_bp,
        usuarios_api_bp, compras_api_bp, comisiones_api_bp, incidentes_api_bp,
        alterestate_api_bp, clarodom_api_bp,
    ):
        csrf.exempt(_api_bp)

    # ─── Registrar Blueprints de Vistas (HTML) ───────────────────────────────
    from app.views.auth_views import auth_views_bp
    from app.views.dashboard_views import dashboard_views_bp
    from app.views.maestros_views import maestros_views_bp
    from app.views.cierres_views import cierres_views_bp

    app.register_blueprint(auth_views_bp)
    # Limitar intentos de login (fuerza bruta) sin tocar app/views/auth_views.py.
    # IMPORTANTE: no se decora directamente app.view_functions['auth_views.login']
    # porque esa funcion es un singleton a nivel de modulo compartido por TODAS
    # las apps que se creen en el proceso (p. ej. cada test llama a create_app()).
    # flask-limiter marca la funcion decorada con una referencia debil a su
    # propio Limiter; si se decora el mismo objeto compartido en cada
    # create_app(), al recrear la app el Limiter anterior se recolecta como
    # basura y esa referencia debil queda muerta, provocando
    # "ReferenceError: weakly-referenced object no longer exists" en la
    # siguiente peticion. Se envuelve en una funcion NUEVA (creada de cero en
    # cada create_app()) para que flask-limiter marque un objeto que vive y
    # muere junto con su propio Limiter, nunca el original compartido.
    _login_original = app.view_functions['auth_views.login']

    def _login_rate_limited(*args, **kwargs):
        return _login_original(*args, **kwargs)
    _login_rate_limited.__name__ = _login_original.__name__

    app.view_functions['auth_views.login'] = limiter.limit("10 per minute")(_login_rate_limited)
    app.register_blueprint(dashboard_views_bp)
    from app.views.cobros_views import cobros_views_bp
    from app.views.marketing_views import marketing_views_bp
    from app.views.exportaciones_views import exportaciones_views_bp
    from app.views.configuracion_views import configuracion_views_bp
    from app.views.carga_archivos_views import carga_archivos_views_bp
    from app.views.compras_views import compras_views_bp
    from app.views.comisiones_views import comisiones_views_bp
    from app.views.incidentes_views import incidentes_views_bp
    from app.views.alterestate_views import alterestate_views_bp
    from app.views.clarodom_views import clarodom_views_bp
    app.register_blueprint(maestros_views_bp)
    app.register_blueprint(cierres_views_bp)
    app.register_blueprint(cobros_views_bp)
    app.register_blueprint(marketing_views_bp)
    app.register_blueprint(exportaciones_views_bp)
    app.register_blueprint(configuracion_views_bp)
    app.register_blueprint(carga_archivos_views_bp)
    app.register_blueprint(compras_views_bp)
    app.register_blueprint(comisiones_views_bp)
    app.register_blueprint(incidentes_views_bp)
    app.register_blueprint(alterestate_views_bp)
    app.register_blueprint(clarodom_views_bp)

    # ─── Inicializacion de DB y migraciones de seguridad ─────────────────────
    with app.app_context():
        from app.core.google_models import GoogleOAuthToken, ConfiguracionSistema  # noqa: F401
        db.create_all()

        from sqlalchemy import text
        from werkzeug.security import generate_password_hash

        # Si el esquema principal no existe (primera ejecucion sin plantilla),
        # construir el esquema canonico desde db_schema.sql antes de operar.
        if db_path and not es_test:
            try:
                tabla_entidades = db.session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='entidades'")
                ).scalar()
            except Exception:
                tabla_entidades = None
            if not tabla_entidades:
                _inicializar_esquema(db_path)
                db.engine.dispose()

        # Tabla usuarios
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL,
                entidad_id INTEGER,
                activo INTEGER DEFAULT 1,
                debo_cambiar_password INTEGER DEFAULT 0,
                intentos_fallidos INTEGER DEFAULT 0,
                bloqueado_hasta DATETIME,
                acepto_politicas INTEGER DEFAULT 0,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(entidad_id) REFERENCES entidades(id)
            )
        """))
        db.session.commit()

        # Migraciones de columnas de seguridad (idempotentes)
        security_migrations = [
            "ALTER TABLE usuarios ADD COLUMN debo_cambiar_password INTEGER DEFAULT 0",
            "ALTER TABLE usuarios ADD COLUMN intentos_fallidos INTEGER DEFAULT 0",
            "ALTER TABLE usuarios ADD COLUMN bloqueado_hasta DATETIME",
            "ALTER TABLE usuarios ADD COLUMN acepto_politicas INTEGER DEFAULT 0",
            "ALTER TABLE usuarios ADD COLUMN fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE pagos ADD COLUMN enlace_dropbox TEXT",
            # Columnas de auditoria mejorada
            "ALTER TABLE auditoria ADD COLUMN ip_address VARCHAR(45)",
            "ALTER TABLE auditoria ADD COLUMN user_agent VARCHAR(255)",
            "ALTER TABLE auditoria ADD COLUMN request_path VARCHAR(500)",
            "ALTER TABLE auditoria ADD COLUMN hash_firma VARCHAR(64)",
        ]
        for migration in security_migrations:
            try:
                db.session.execute(text(migration))
                db.session.commit()
            except Exception:
                pass  # Columna ya existe

        # Migraciones de columnas funcionales (idempotentes, via PRAGMA table_info)
        def _agregar_columna_si_falta(tabla, columna, definicion):
            columnas_existentes = db.session.execute(
                text(f"PRAGMA table_info({tabla})")
            ).mappings().all()
            if columna not in {c["name"] for c in columnas_existentes}:
                db.session.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}"))
                db.session.commit()

        columnas_migracion = {
            "transacciones": {
                "fecha_cierre": "DATE",
                "comprobante_fiscal": "VARCHAR(14)",
                "ingreso_verificado": "BOOLEAN DEFAULT 0",
            },
            "proyectos": {
                "es_exclusivo": "BOOLEAN DEFAULT 1",
            },
            "compras_pagos": {
                "fecha_pago": "DATE",
            },
        }
        for tabla, columnas in columnas_migracion.items():
            for columna, definicion in columnas.items():
                try:
                    _agregar_columna_si_falta(tabla, columna, definicion)
                except Exception as e:
                    logging.warning(f"No se pudo migrar columna {tabla}.{columna}: {e}")

        # Verificar si existe el admin
        admin_exists = db.session.execute(text("SELECT id FROM usuarios WHERE username = 'admin'")).scalar()
        if not admin_exists and not es_test:
            admin_password = os.environ.get("ADMIN_PASSWORD") or "MiClaveAdmin_2026!"
            hashed_pw = generate_password_hash(admin_password)
            db.session.execute(
                text("INSERT INTO usuarios (username, password_hash, rol, activo, debo_cambiar_password) "
                     "VALUES (:u, :p, :r, 1, 1)"),
                {"u": "admin", "p": hashed_pw, "r": "Admin"}
            )
            db.session.commit()
            print(f"Usuario Super Admin creado.")
            print(f"  Usuario: admin")
            print(f"  Password: {admin_password}")
            print(f"  ** CAMBIA ESTE PASSWORD DESPUES DE TU PRIMER LOGIN **")

        # Verificar integridad de la DB
        integrity_secret = app.config.get("DB_INTEGRITY_SECRET", "")
        if integrity_secret and db_path:
            try:
                from app.core.integrity import verify_db_integrity, store_db_hash
                result = verify_db_integrity(db_path, integrity_secret, db.session)
                if not result["valid"]:
                    logging.critical(f"INTEGRIDAD DB COMPROMETIDA: {result['message']}")
                else:
                    if result["stored_hash"] is None:
                        store_db_hash(db_path, integrity_secret, db.session)
                        logging.info("Hash de integridad de DB inicializado.")
                    else:
                        logging.info("Integridad de DB verificada correctamente.")
            except Exception as e:
                logging.warning(f"No se pudo verificar integridad de DB: {e}")

        # ─── Registro de version en DB ─────────────────────────────────────
        from app.version import get_version, get_build
        current_version = get_version()
        current_build = get_build()
        try:
            db.session.execute(
                text("INSERT INTO app_config (clave, valor) VALUES ('app_version', :v) "
                     "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"),
                {"v": current_version}
            )
            db.session.execute(
                text("INSERT INTO app_config (clave, valor) VALUES ('app_build', :b) "
                     "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"),
                {"b": current_build}
            )
            db.session.commit()
        except Exception:
            pass

        # ─── Client ID unico para esta instalacion ─────────────────────────
        try:
            client_id_row = db.session.execute(
                text("SELECT valor FROM app_config WHERE clave='client_id'")
            ).scalar()
            if not client_id_row:
                import uuid
                client_id = str(uuid.uuid4())[:12]
                db.session.execute(
                    text("INSERT INTO app_config (clave, valor) VALUES ('client_id', :c)"),
                    {"c": client_id}
                )
                db.session.commit()
        except Exception:
            pass

        # ─── Registrar ultima vez que la app se inicio ─────────────────────
        try:
            import platform
            db.session.execute(
                text("INSERT INTO app_config (clave, valor) VALUES ('last_startup', :v) "
                     "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"),
                {"v": datetime.now().isoformat()}
            )
            db.session.execute(
                text("INSERT INTO app_config (clave, valor) VALUES ('os_info', :v) "
                     "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"),
                {"v": f"{platform.system()} {platform.release()}"}
            )
            db.session.commit()
        except Exception:
            pass

        # Activar OAUTHLIB en desarrollo HTTP
        if app.config.get("OAUTHLIB_INSECURE_TRANSPORT"):
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        # ─── Migraciones AlterEstate ─────────────────────────────────────────
        try:
            from app.core.alterestate_migration import run_migration as ae_migration
            ae_migration()
        except Exception as e:
            logging.warning(f"Migraciones AlterEstate no ejecutadas (esperado en primera instalacion): {e}")

    # ─── Verificar actualizaciones en background ─────────────────────────────
    try:
        if not es_test:
            from app.core.updater import check_updates_background
            check_updates_background()
    except Exception:
        pass

    # ─── Inyectar version en templates ───────────────────────────────────────
    @app.context_processor
    def inject_version():
        from app.version import get_version_dict
        return {"app_version": get_version_dict()}

    # Iniciar motor de tareas programadas
    try:
        if not es_test:
            from app.core.scheduler import init_scheduler
            init_scheduler(app)
    except Exception as e:
        print(f"Error iniciando scheduler: {e}")

    return app
