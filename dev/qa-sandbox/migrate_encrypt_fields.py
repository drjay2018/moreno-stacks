"""
migrate_encrypt_fields.py — Migra datos sensibles existentes a formato cifrado Fernet.
Ejecutar una sola vez despues de configurar FIELD_ENCRYPTION_KEY en .env.

Uso:
    cd dlab-app
    python migrate_encrypt_fields.py

IMPORTANTE: Haz un backup de tu DB antes de ejecutar este script.
"""

import os
import sys
import sqlite3
from pathlib import Path

# Agregar el directorio al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import DB_PATH
from app.core.crypto import encrypt_field, is_encrypted


def migrate_google_oauth_tokens(conn: sqlite3.Connection) -> int:
    """Cifra tokens OAuth de Google que no estan cifrados."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, access_token, refresh_token, client_secret FROM google_oauth_tokens")
    rows = cursor.fetchall()
    migrated = 0

    for row in rows:
        id_, access_token, refresh_token, client_secret = row
        updates = []
        params = {"id": id_}

        if access_token and not is_encrypted(access_token):
            updates.append("access_token = :access_token")
            params["access_token"] = encrypt_field(access_token)

        if refresh_token and not is_encrypted(refresh_token):
            updates.append("refresh_token = :refresh_token")
            params["refresh_token"] = encrypt_field(refresh_token)

        if client_secret and not is_encrypted(client_secret):
            updates.append("client_secret = :client_secret")
            params["client_secret"] = encrypt_field(client_secret)

        if updates:
            set_clause = ", ".join(updates)
            cursor.execute(f"UPDATE google_oauth_tokens SET {set_clause} WHERE id = :id", params)
            migrated += 1

    conn.commit()
    return migrated


def migrate_configuracion_sistema(conn: sqlite3.Connection) -> int:
    """Cifra google_client_secret en configuracion_sistema."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, google_client_secret FROM configuracion_sistema")
    rows = cursor.fetchall()
    migrated = 0

    for row in rows:
        id_, google_client_secret = row
        if google_client_secret and not is_encrypted(google_client_secret):
            cursor.execute(
                "UPDATE configuracion_sistema SET google_client_secret = :secret WHERE id = :id",
                {"secret": encrypt_field(google_client_secret), "id": id_}
            )
            migrated += 1

    conn.commit()
    return migrated


def migrate_smtp_password(conn: sqlite3.Connection) -> int:
    """Cifra smtp_password en app_config."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, valor FROM app_config WHERE clave = 'smtp_password'")
    row = cursor.fetchone()
    migrated = 0

    if row and row[1] and not is_encrypted(row[1]):
        cursor.execute(
            "UPDATE app_config SET valor = :v WHERE clave = 'smtp_password'",
            {"v": encrypt_field(row[1])}
        )
        migrated = 1

    conn.commit()
    return migrated


def main():
    print("=" * 60)
    print("  MIGRACION DE CIFRADO DE CAMPOS SENSIBLES")
    print("=" * 60)

    if not os.environ.get("FIELD_ENCRYPTION_KEY"):
        print("\nERROR: FIELD_ENCRYPTION_KEY no esta definida en .env")
        print("Genera una clave con: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"\nERROR: Base de datos no encontrada en {DB_PATH}")
        sys.exit(1)

    # Backup
    from datetime import datetime
    backup_path = DB_PATH.parent / f"dlab_pre_encrypt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    import shutil
    shutil.copy2(DB_PATH, backup_path)
    print(f"\nBackup creado: {backup_path}")

    conn = sqlite3.connect(str(DB_PATH))

    try:
        print("\n[1/3] Cifrando tokens OAuth de Google...")
        n = migrate_google_oauth_tokens(conn)
        print(f"      {n} registro(s) cifrado(s).")

        print("[2/3] Cifrando credenciales Google del sistema...")
        n = migrate_configuracion_sistema(conn)
        print(f"      {n} registro(s) cifrado(s).")

        print("[3/3] Cifrando password SMTP...")
        n = migrate_smtp_password(conn)
        print(f"      {n} registro(s) cifrado(s).")

        print("\n" + "=" * 60)
        print("  MIGRACION COMPLETADA CON EXITO")
        print("=" * 60)
        print("\nTu DB original esta respaldada en:")
        print(f"  {backup_path}")

    except Exception as e:
        print(f"\nERROR durante la migracion: {e}")
        print("Restaura el backup y revisa el error.")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
