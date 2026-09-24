"""
updater.py — Motor de auto-update desde GitHub Releases.
Costo: GRATIS (GitHub Releases + GitHub Actions).
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuracion del repositorio de GitHub
GITHUB_OWNER = os.environ.get("DLAB_GITHUB_OWNER", "drjay2018")
GITHUB_REPO = os.environ.get("DLAB_GITHUB_REPO", "dlab-data")
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
DLAB_RELEASES_API_URL = os.environ.get(
    "DLAB_RELEASES_API_URL",
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest",
)

# Estado global del update
_update_status = {
    "checking": False,
    "available": False,
    "latest_version": None,
    "current_version": None,
    "downloading": False,
    "download_progress": 0,
    "applying": False,
    "error": None,
    "last_check": None,
}

# Actualizador auxiliar compilado (reemplaza archivos bloqueados cuando la app se cierra)
APP_INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "DLAB_CRM"
UPDATER_EXE = APP_INSTALL_DIR / "updater.exe"


def get_update_status() -> dict:
    return _update_status.copy()


def get_current_version() -> str:
    from app.version import get_version
    return get_version()


def _compare_versions(current: str, latest: str) -> bool:
    """Retorna True si latest > current."""
    def parse(v):
        return tuple(int(x) for x in v.strip().split("."))
    try:
        return parse(latest) > parse(current)
    except (ValueError, AttributeError):
        return False


def _error_result(mensaje: str, detalle: str = None) -> dict:
    """Resultado estructurado cuando el check de actualizacion no puede completarse."""
    _update_status["error"] = mensaje
    return {
        "available": False,
        "disponible": False,
        "error": detalle,
        "mensaje": mensaje,
    }


def check_for_updates() -> dict:
    """
    Verifica si hay una nueva version en GitHub Releases.
    Retorna: {"available": bool, "version": str, "changelog": str, "download_url": str}
    O, ante fallo de la consulta: {"available": False, "disponible": False, "mensaje": str}.
    Nunca lanza excepciones crudas que rompan el endpoint.
    """
    import urllib.request
    import urllib.error

    _update_status["checking"] = True
    _update_status["error"] = None

    try:
        current = get_current_version()
        _update_status["current_version"] = current

        req = urllib.request.Request(DLAB_RELEASES_API_URL, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return _error_result(
                "No se pudieron comprobar las actualizaciones (repo privado o sin release).",
                f"HTTP {e.code}",
            )
        return _error_result(
            "No se pudieron comprobar las actualizaciones (error del servidor de releases).",
            f"HTTP {e.code}",
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return _error_result(
            "No se pudieron comprobar las actualizaciones (sin conexion o timeout).",
            str(e),
        )
    except ValueError as e:
        return _error_result(
            "No se pudieron comprobar las actualizaciones (respuesta no valida del servidor).",
            str(e),
        )
    except Exception as e:
        return _error_result(
            "No se pudieron comprobar las actualizaciones.",
            str(e),
        )
    finally:
        _update_status["checking"] = False

    try:
        tag = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "")

        # Buscar asset con el ZIP
        download_url = None
        checksum = None
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".zip") and "dlab_app" in name:
                download_url = asset.get("browser_download_url")
            if name == "checksum.txt":
                checksum_url = asset.get("browser_download_url")
                try:
                    creq = urllib.request.Request(checksum_url)
                    with urllib.request.urlopen(creq, timeout=10) as cresp:
                        _checksum_txt = cresp.read().decode().strip()
                    # checksum.txt contiene "<hash>  <nombre>" por linea
                    for linea in _checksum_txt.splitlines():
                        if "dlab_app.zip" in linea:
                            checksum = linea.split()[0].strip().lower()
                            break
                except Exception:
                    pass

        available = _compare_versions(current, tag)
        _update_status["available"] = available
        _update_status["latest_version"] = tag
        _update_status["last_check"] = datetime.now().isoformat()

        return {
            "available": available,
            "current_version": current,
            "latest_version": tag,
            "changelog": body,
            "download_url": download_url,
            "checksum": checksum,
        }

    except Exception as e:
        return _error_result(
            "No se pudo completar la comprobacion de actualizaciones.",
            str(e),
        )


def _compute_file_hash(filepath: str) -> str:
    """Calcula SHA256 de un archivo."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_file(url: str, dest: str, progress_callback=None) -> bool:
    """Descarga un archivo con progreso."""
    import urllib.request

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(int(downloaded * 100 / total))
        return True
    except Exception as e:
        logger.error(f"Error descargando update: {e}")
        return False


def create_pre_update_backup() -> str:
    """Crea un backup de la instalacion actual antes de actualizar."""
    from app.config import USER_DATA_DIR

    backup_dir = USER_DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"pre_update_backup_{timestamp}.zip"
    backup_path = backup_dir / backup_name

    # Backup del directorio de la app (no de la DB)
    app_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "DLAB_CRM"
    if not app_dir.exists():
        app_dir = USER_DATA_DIR.parent

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in app_dir.rglob("*"):
            if item.is_file() and "backups" not in str(item) and "logs" not in str(item):
                try:
                    zf.write(item, item.relative_to(app_dir))
                except Exception:
                    pass

    logger.info(f"Backup pre-update creado: {backup_path}")
    return str(backup_path)


def apply_update(zip_path: str, checksum: str = None) -> dict:
    """
    Aplica un parche de actualizacion.
    Retorna: {"success": bool, "message": str}
    """
    _update_status["applying"] = True

    try:
        # Verificar checksum si se proporciona
        if checksum:
            actual_hash = _compute_file_hash(zip_path)
            if actual_hash != checksum:
                return {"success": False, "error": "Checksum no coincide. El archivo puede estar corrupto."}

        # Backup antes de actualizar
        backup_path = create_pre_update_backup()

        # Determinar destino
        app_dest = Path(os.environ.get("LOCALAPPDATA", "")) / "DLAB_CRM"
        if not app_dest.exists():
            app_dest = Path(os.environ.get("APPDATA", "")) / "DLAB_CRM"

        # Extraer ZIP (sobreescribe archivos existentes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(app_dest)

        logger.info(f"Update aplicado desde {zip_path} a {app_dest}")

        return {
            "success": True,
            "message": f"Actualizacion aplicada. Backup en: {backup_path}",
            "backup_path": backup_path,
        }

    except Exception as e:
        logger.error(f"Error aplicando update: {e}")
        return {"success": False, "error": str(e)}
    finally:
        _update_status["applying"] = False


def download_and_apply(update_info: dict, progress_callback=None) -> dict:
    """Descarga y aplica una actualizacion completa."""
    _update_status["downloading"] = True
    _update_status["download_progress"] = 0

    try:
        url = update_info.get("download_url")
        if not url:
            return {"success": False, "error": "No hay URL de descarga disponible."}

        # Descargar a temporal
        tmp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_dir, "dlab_update.zip")

        def on_progress(pct):
            _update_status["download_progress"] = pct
            if progress_callback:
                progress_callback(pct)

        if not _download_file(url, zip_path, on_progress):
            return {"success": False, "error": "Error al descargar la actualizacion."}

        # Aplicar
        result = apply_update(zip_path, update_info.get("checksum"))

        # Limpiar temporal
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

        return result

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        _update_status["downloading"] = False
        _update_status["download_progress"] = 0


def prepare_update(update_info: dict, progress_callback=None) -> dict:
    """
    Descarga el paquete de actualizacion a un directorio temporal y verifica
    su checksum. Retorna: {"success": bool, "zip_path": str, "checksum": str|None}.
    """
    _update_status["downloading"] = True
    _update_status["download_progress"] = 0

    try:
        url = update_info.get("download_url")
        if not url:
            return {"success": False, "error": "No hay URL de descarga disponible."}

        tmp_dir = Path(tempfile.mkdtemp(prefix="dlab_update_"))
        zip_path = tmp_dir / "dlab_app.zip"

        def on_progress(pct):
            _update_status["download_progress"] = pct
            if progress_callback:
                progress_callback(pct)

        if not _download_file(url, str(zip_path), on_progress):
            return {"success": False, "error": "Error al descargar la actualizacion."}

        expected = update_info.get("checksum")
        if expected:
            actual = _compute_file_hash(str(zip_path))
            if actual.lower() != expected.lower():
                return {
                    "success": False,
                    "error": "Checksum no coincide. El archivo puede estar corrupto.",
                }

        return {"success": True, "zip_path": str(zip_path), "checksum": expected}

    except Exception as e:
        logger.error(f"Error preparando update: {e}")
        return {"success": False, "error": str(e)}

    finally:
        _update_status["downloading"] = False
        _update_status["download_progress"] = 0


def launch_updater(zip_path: str, checksum: str = None) -> bool:
    """
    Lanza updater.exe (compilado aparte) que espera a que la app se cierre,
    reemplaza los archivos bloqueados y relanza la app. Retorna True si se lanzo.
    Si no existe updater.exe (dev/instalacion antigua), retorna False.
    """
    if not UPDATER_EXE.exists():
        logger.warning("updater.exe no encontrado en %s", UPDATER_EXE)
        return False

    try:
        args = [str(UPDATER_EXE), str(zip_path)]
        if checksum:
            args.append(checksum)
        subprocess.Popen(args, cwd=str(APP_INSTALL_DIR), creationflags=0x08000000)  # CREATE_NO_WINDOW
        logger.info("updater.exe lanzado para aplicar update: %s", zip_path)
        return True
    except Exception as e:
        logger.error(f"Error lanzando updater.exe: {e}")
        return False


def check_updates_background():
    """Verifica actualizaciones en background (no bloquea)."""
    def _run():
        try:
            check_for_updates()
        except Exception as e:
            logger.warning(f"Error verificando updates en background: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
