"""
usuarios_api.py — API REST para la gestion CRUD de Usuarios del Sistema.
Seguridad: SQL injection mitigada, validacion estricta de columnas, sin exposicion de errores raw.
"""

import re

from flask import Blueprint, request, jsonify, session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.core.auth_middleware import requiere_rol, requiere_login

usuarios_api_bp = Blueprint("usuarios_api", __name__, url_prefix="/api/usuarios")

# Columnas permitidas para UPDATE (whitelist estricto)
_ALLOWED_UPDATE_COLUMNS = {"rol", "activo", "password_hash", "entidad_id", "debo_cambiar_password", "username"}
_ALLOWED_ROLES = {"Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO", "Asistente", "Asesor"}
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")


def _username_valido(username):
    return bool(_USERNAME_RE.match(username)) and bool(re.search(r"[A-Za-z0-9]", username))


@usuarios_api_bp.route("", methods=["GET"])
@requiere_rol("Admin")
def get_usuarios():
    try:
        rows = db.session.execute(text("""
            SELECT u.id, u.username, u.rol, u.activo, u.entidad_id,
                   e.nombre || ' ' || e.apellido as empleado_nombre
            FROM usuarios u
            LEFT JOIN entidades e ON u.entidad_id = e.id
            ORDER BY u.id DESC
        """)).mappings().all()
        return jsonify({"success": True, "items": [dict(r) for r in rows]})
    except Exception:
        return jsonify({"success": False, "error": "Error al obtener usuarios."}), 500


@usuarios_api_bp.route("", methods=["POST"])
@requiere_rol("Admin")
def create_usuario():
    try:
        data = request.json
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        rol = data.get("rol", "Asesor")
        entidad_id = data.get("entidad_id")

        if not username or not password:
            return jsonify({"success": False, "error": "Username y contrasena son requeridos"}), 400

        if not _username_valido(username):
            return jsonify({"success": False, "error": "Username invalido. Solo letras, numeros, puntos, guiones y guiones bajos (minimo 3 caracteres)."}), 400

        if rol not in _ALLOWED_ROLES:
            return jsonify({"success": False, "error": "Rol no valido."}), 400

        if len(password) < 12:
            return jsonify({"success": False, "error": "La contrasena debe tener al menos 12 caracteres."}), 400

        hashed_pw = generate_password_hash(password)

        db.session.execute(text("""
            INSERT INTO usuarios (username, password_hash, rol, entidad_id, activo, fecha_creacion, intentos_fallidos)
            VALUES (:u, :p, :r, :e, 1, CURRENT_TIMESTAMP, 0)
        """), {"u": username, "p": hashed_pw, "r": rol, "e": entidad_id if entidad_id else None})
        db.session.commit()
        return jsonify({"success": True, "message": "Usuario creado correctamente"})
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": f"El username '{username}' ya esta en uso."}), 409
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Error al crear usuario."}), 500


@usuarios_api_bp.route("/<int:user_id>", methods=["PUT"])
@requiere_rol("Admin")
def update_usuario(user_id):
    try:
        data = request.json
        updates = []
        params = {"id": user_id}

        # Validar y filtrar solo columnas permitidas (anti SQL injection)
        if "rol" in data:
            rol = data["rol"]
            if rol not in _ALLOWED_ROLES:
                return jsonify({"success": False, "error": "Rol no valido."}), 400
            updates.append("rol = :rol")
            params["rol"] = rol

        if "activo" in data:
            updates.append("activo = :activo")
            params["activo"] = int(bool(data["activo"]))

        if "entidad_id" in data:
            updates.append("entidad_id = :entidad_id")
            params["entidad_id"] = data["entidad_id"]

        if "username" in data:
            username = data["username"].strip()
            if not _username_valido(username):
                return jsonify({"success": False, "error": "Username invalido. Solo letras, numeros, puntos, guiones y guiones bajos (minimo 3 caracteres)."}), 400
            updates.append("username = :username")
            params["username"] = username

        password = (data.get("password") or "").strip()
        if password:
            if len(password) < 12:
                return jsonify({"success": False, "error": "La contrasena debe tener al menos 12 caracteres."}), 400
            updates.append("password_hash = :password_hash")
            params["password_hash"] = generate_password_hash(password)

        if not updates:
            return jsonify({"success": False, "error": "Nada para actualizar"}), 400

        set_clause = ", ".join(updates)
        resultado = db.session.execute(text(f"UPDATE usuarios SET {set_clause} WHERE id = :id"), params)
        if resultado.rowcount == 0:
            db.session.rollback()
            return jsonify({"success": False, "error": "Usuario no encontrado."}), 404
        db.session.commit()
        return jsonify({"success": True, "message": "Usuario actualizado correctamente"})
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Error al actualizar usuario."}), 500


@usuarios_api_bp.route("/<int:user_id>", methods=["DELETE"])
@requiere_rol("Admin")
def delete_usuario(user_id):
    try:
        if user_id == 1:
            return jsonify({"success": False, "error": "No se puede borrar el super admin."}), 400

        current_user = session.get("usuario", {})
        if current_user.get("id") == user_id:
            return jsonify({"success": False, "error": "No puedes eliminarte a ti mismo."}), 400

        resultado = db.session.execute(text("UPDATE usuarios SET activo = 0 WHERE id = :id"), {"id": user_id})
        if resultado.rowcount == 0:
            db.session.rollback()
            return jsonify({"success": False, "error": "Usuario no encontrado."}), 404
        db.session.commit()
        return jsonify({"success": True, "message": "Usuario desactivado"})
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Error al eliminar usuario."}), 500


@usuarios_api_bp.route("/aceptar-politicas", methods=["POST"])
@requiere_login
def aceptar_politicas():
    if not session.get("usuario"):
        return jsonify({"success": False, "error": "No autorizado"}), 401
    try:
        user_id = session["usuario"]["id"]
        db.session.execute(
            text("UPDATE usuarios SET acepto_politicas = 1 WHERE id = :id"),
            {"id": user_id}
        )
        db.session.commit()
        session["usuario"]["acepto_politicas"] = True
        session.modified = True
        return jsonify({"success": True})
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Error al aceptar politicas."}), 500
