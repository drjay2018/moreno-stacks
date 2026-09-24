"""
auth_views.py — Blueprints de autenticacion (Login, Logout, Cambio de password)
con proteccion contra fuerza bruta, rate limiting y open redirect fix.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash
from app.extensions import db
from app.core.brute_force import (
    record_failed_attempt, record_successful_attempt,
    is_locked, get_client_ip, get_failed_attempts
)
from urllib.parse import urlparse
import re

auth_views_bp = Blueprint("auth_views", __name__)

_PASSWORD_MIN_LENGTH = 12
_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{12,}$")


def _is_strong_password(password: str) -> tuple[bool, str]:
    """Valida complejidad de contrasena. Retorna (es_valida, mensaje_error)."""
    if len(password) < _PASSWORD_MIN_LENGTH:
        return False, f"La contrasena debe tener al menos {_PASSWORD_MIN_LENGTH} caracteres."
    if not _PASSWORD_PATTERN.match(password):
        return False, "Debe incluir mayuscula, minuscula, numero y simbolo (!@#$%^&*...)."
    return True, ""


@auth_views_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        ip = get_client_ip()

        if not username or not password:
            flash("Usuario y contrasena son requeridos.", "error")
            return render_template("auth/login.html")

        # Verificar si la IP esta bloqueada
        lock_status = is_locked(ip)
        if lock_status["locked"]:
            mins = lock_status["remaining_seconds"] // 60
            flash(f"Cuenta temporalmente bloqueada. Intenta en {mins} minutos.", "error")
            return render_template("auth/login.html")

        user_row = db.session.execute(
            text("SELECT id, username, password_hash, rol, entidad_id, activo, "
                 "acepto_politicas, debo_cambiar_password, intentos_fallidos, bloqueado_hasta "
                 "FROM usuarios WHERE username = :u AND activo = 1"),
            {"u": username}
        ).mappings().first()

        # Verificar bloqueo en DB
        if user_row and user_row.get("bloqueado_hasta"):
            from datetime import datetime
            bloqueado_hasta = user_row["bloqueado_hasta"]
            if isinstance(bloqueado_hasta, str):
                bloqueado_hasta = datetime.fromisoformat(bloqueado_hasta)
            if datetime.now() < bloqueado_hasta:
                flash("Cuenta bloqueada por intentos fallidos. Contacta al administrador.", "error")
                return render_template("auth/login.html")
            else:
                db.session.execute(
                    text("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE id=:id"),
                    {"id": user_row["id"]}
                )
                db.session.commit()

        if user_row and check_password_hash(user_row["password_hash"], password):
            # Login exitoso
            record_successful_attempt(ip)
            db.session.execute(
                text("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE id=:id"),
                {"id": user_row["id"]}
            )
            db.session.commit()

            session.clear()
            session["usuario"] = {
                "id": user_row["id"],
                "username": user_row["username"],
                "rol": user_row["rol"],
                "entidad_id": user_row["entidad_id"],
                "acepto_politicas": bool(user_row["acepto_politicas"]),
                "debo_cambiar_password": bool(user_row.get("debo_cambiar_password", False))
            }
            if user_row.get("debo_cambiar_password"):
                return redirect(url_for("auth_views.cambiar_password_obligatorio"))

            # Open redirect fix: solo permitir paths relativos seguros
            next_url = request.args.get("next", "")
            if next_url:
                parsed = urlparse(next_url)
                if not parsed.netloc and next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
            return redirect(url_for("dashboard_views.dashboard"))
        else:
            # Login fallido — registrar intento (rate limiting por IP, aplica siempre)
            attempt_info = record_failed_attempt(ip)

            max_attempts = current_app.config.get("MAX_LOGIN_ATTEMPTS", 5)
            lockout_seconds = current_app.config.get("LOCKOUT_SECONDS", 1800)

            if user_row:
                # Usuario real: se mantiene el contador de intentos/bloqueo por cuenta.
                attempts_db = user_row["intentos_fallidos"] + 1

                from datetime import datetime, timedelta
                lockout_until = None
                if attempts_db >= max_attempts:
                    lockout_until = datetime.now() + timedelta(seconds=lockout_seconds)

                db.session.execute(
                    text("UPDATE usuarios SET intentos_fallidos=:a, bloqueado_hasta=:l WHERE username=:u"),
                    {"a": attempts_db, "l": lockout_until, "u": username}
                )
                db.session.commit()

                remaining = max_attempts - attempts_db if attempts_db < max_attempts else 0
                if remaining > 0:
                    flash(f"Credenciales incorrectas. Te quedan {remaining} intentos.", "error")
                else:
                    flash("Cuenta bloqueada por intentos fallidos.", "error")
            else:
                # Usuario inexistente: mensaje generico y fijo, sin simular un contador
                # de intentos. Antes se calculaba un "0 + 1" ficticio y se mostraba
                # "Te quedan N intentos" igual que a un usuario real, lo cual permitia
                # distinguir usuarios existentes de inexistentes observando si el
                # mensaje decrece (real) o se mantiene igual siempre (inexistente).
                flash("Usuario o contrasena incorrectos.", "error")

    # Si ya esta logueado, redirigir
    if session.get("usuario"):
        return redirect(url_for("dashboard_views.dashboard"))

    return render_template("auth/login.html")


@auth_views_bp.route("/cambiar-password", methods=["GET", "POST"])
def cambiar_password_obligatorio():
    if not session.get("usuario"):
        return redirect(url_for("auth_views.login"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        is_valid, error_msg = _is_strong_password(new_password)
        if not is_valid:
            flash(error_msg, "error")
            return render_template("auth/cambiar_password.html")

        if new_password != confirm_password:
            flash("Las contrasenas no coinciden.", "error")
            return render_template("auth/cambiar_password.html")

        user_id = session["usuario"]["id"]
        hashed_pw = generate_password_hash(new_password)
        db.session.execute(
            text("UPDATE usuarios SET password_hash = :p, debo_cambiar_password = 0 WHERE id = :id"),
            {"p": hashed_pw, "id": user_id}
        )
        db.session.commit()

        session["usuario"]["debo_cambiar_password"] = False
        flash("Contrasena actualizada exitosamente.", "success")
        return redirect(url_for("dashboard_views.dashboard"))

    return render_template("auth/cambiar_password.html")


@auth_views_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth_views.login"))
