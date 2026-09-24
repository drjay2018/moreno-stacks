"""
updater_exe.py — Actualizador auxiliar DLAB CRM (compilado aparte como updater.exe).

Su unica funcion es reemplazar la app cuando el proceso principal esta cerrado,
porque Windows bloquea DLAB.exe y las DLLs mientras corren. Nunca se auto-renueva:
siempre conserva la misma version de codigo para poder aplicar futuros parches.

Flujo (invocado por la app via API /api/configuracion/update/apply):
  1. La app descarga dlab_app.zip y lanza este updater pasandole <zip> [checksum].
  2. La app principal se cierra.
  3. Este proceso espera a que DLAB.exe quede desbloqueado, verifica el checksum,
     hace backup, extrae el ZIP sobre la instalacion y relanza la app.
  4. Usa unicamente libreria estandar (compilado onefile, sin dependencias).
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

APP_DIR = Path(sys.executable).resolve().parent
MAIN_EXE = APP_DIR / "DLAB.exe"
UPDATER_NAME = Path(sys.executable).name

LOG_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "DLAB_CRM" / "logs"
BACKUP_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "DLAB_CRM" / "backups"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "updater.log", encoding="utf-8")],
)


def calcular_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def esperar_desbloqueo(nombre="DLAB.exe", timeout=120) -> bool:
    """Espera a que el proceso principal termine y libere sus archivos."""
    objetivo = APP_DIR / nombre
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            fh = open(objetivo, "r+b")
            fh.close()
            return True
        except PermissionError:
            time.sleep(0.5)
        except FileNotFoundError:
            time.sleep(0.5)
    return False


def crear_backup() -> Path:
    """Respaldo de la instalacion actual (excluye DB, backups y logs)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"pre_update_backup_{ts}.zip"

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in APP_DIR.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(APP_DIR)
            partes = set(rel.parts)
            if "backups" in partes or "logs" in partes or "_update" in partes:
                continue
            if UPDATER_NAME in rel.parts:
                continue
            try:
                zf.write(item, rel)
            except Exception as e:
                logging.warning("No se pudo respaldar %s: %s", item, e)
    return backup_path


def aplicar_paquete(zip_path: Path, checksum: str = None) -> bool:
    if checksum:
        actual = calcular_sha256(zip_path)
        if actual.lower() != checksum.lower():
            logging.error("Checksum no coincide: esperado %s, actual %s", checksum[:16], actual[:16])
            return False

    backup_path = crear_backup()
    logging.info("Backup pre-update: %s", backup_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for miembro in zf.infolist():
            base = Path(miembro.filename).parts[0] if miembro.filename else ""
            if base == UPDATER_NAME:
                continue
            try:
                zf.extract(miembro, APP_DIR)
            except PermissionError as e:
                logging.error("Archivo bloqueado al extraer: %s (%s)", miembro.filename, e)
                return False
            except Exception as e:
                logging.warning("Error extrayendo %s: %s", miembro.filename, e)
    return True


def relanzar_app() -> None:
    if not MAIN_EXE.exists():
        return
    flags = 0x00000008  # DETACHED_PROCESS
    try:
        flags |= 0x08000000  # CREATE_NO_WINDOW
        subprocess.Popen([str(MAIN_EXE)], cwd=str(APP_DIR), creationflags=flags)
    except Exception as e:
        logging.error("No se pudo relanzar la app: %s", e)


def main() -> int:
    if len(sys.argv) < 2:
        logging.error("Uso: updater.exe <dlab_app.zip> [sha256]")
        return 2

    zip_path = Path(sys.argv[1])
    checksum = sys.argv[2] if len(sys.argv) > 2 else None

    if not zip_path.exists():
        logging.error("Paquete de update no encontrado: %s", zip_path)
        return 3

    logging.info("Iniciando actualizacion. App dir: %s", APP_DIR)

    if not esperar_desbloqueo():
        logging.error("Tiempo de espera agotado: la app no termino de cerrarse.")
        relanzar_app()
        return 4

    ok = aplicar_paquete(zip_path, checksum)
    logging.info("Resultado del parche: %s", "OK" if ok else "FALLIDO")

    try:
        shutil.rmtree(zip_path.parent, ignore_errors=True)
    except Exception:
        pass

    relanzar_app()
    logging.info("Update finalizado (codigo %d). Relanzando app.", 0 if ok else 5)
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())