"""
auth_middleware.py — Decoradores de seguridad y control de acceso basado en roles (RBAC).
Ahora verifica bloqueo de cuenta antes de autorizar.
"""

from functools import wraps
from flask import session, jsonify, redirect, url_for, request
from sqlalchemy import text
from datetime import datetime


def _is_user_locked(user_id: int) -> bool:
    """Verifica si un usuario esta bloqueado en la DB."""
    try:
        from app.extensions import db
        result = db.session.execute(
            text("SELECT bloqueado_hasta FROM usuarios WHERE id = :id"),
            {"id": user_id}
        ).scalar()
        if not result:
            return False
        if isinstance(result, str):
            result = datetime.fromisoformat(result)
        return datetime.now() < result
    except Exception:
        return False


def requiere_login(f):
    """Decorador para requerir autenticacion general."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        usuario = session.get("usuario")
        if not usuario:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Autenticación requerida."}), 401
            return redirect(url_for("auth_views.login"))

        # Verificar si la sesion expiro o el usuario fue bloqueado
        if _is_user_locked(usuario.get("id", 0)):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Sesion expirada. Cuenta bloqueada."}), 401
            return redirect(url_for("auth_views.login"))

        return f(*args, **kwargs)
    return decorated_function


def requiere_rol(*roles_permitidos):
    """
    Decorador para restringir endpoints API o vistas a roles especificos.
    Ejemplo: @requiere_rol('Admin', 'Gerente Comercial')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            usuario = session.get("usuario")
            if not usuario:
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "error": "Autenticación requerida."}), 401
                return redirect(url_for("auth_views.login"))

            # Verificar bloqueo de cuenta
            if _is_user_locked(usuario.get("id", 0)):
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "error": "Sesion expirada. Cuenta bloqueada."}), 401
                return redirect(url_for("auth_views.login"))

            rol_usuario = (usuario.get("rol") or "").upper()
            roles_upper = [r.upper() for r in roles_permitidos] if roles_permitidos else []

            if roles_upper and rol_usuario not in roles_upper:
                # Si es ADMIN, siempre se permite el acceso
                if rol_usuario != 'ADMIN':
                    if request.path.startswith("/api/"):
                        return jsonify({"success": False, "error": f"Acceso denegado. Se requiere uno de los roles: {', '.join(roles_permitidos)}"}), 403
                    return redirect(url_for("dashboard_views.index"))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
