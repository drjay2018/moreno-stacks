"""
app_tray.py — Entrada de la aplicacion compilada (PyInstaller, modo bandeja).

Ejecuta DLAB CRM sin ventana de consola: el servidor Flask corre en un hilo en
segundo plano y la aplicacion queda en la bandeja del sistema con un icono
(clic derecho: Abrir / Salir; clic izquierdo: abre el navegador).
"""

import os
import sys
import logging
import threading
import webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)

# ─── Modo compilado sin consola: redirigir stdout/stderr a un archivo ───────
log_dir = Path(
    os.environ.get("APPDATA", os.path.expanduser("~"))
) / "DLAB_CRM" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
_std_file = log_dir / "app_console.log"


def _reassign_stdio():
    if sys.stdout is None:
        sys.stdout = open(_std_file, "a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = open(_std_file, "a", encoding="utf-8", buffering=1)


_reassign_stdio()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def abrir_navegador():
    """Abre la app en el navegador por defecto (sin abrir ventana de consola)."""
    try:
        import subprocess
        logging.info("Abriendo navegador...")
        result = subprocess.run(
            ["cmd", "/c", "start", "", "http://127.0.0.1:5000"],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            webbrowser.open("http://127.0.0.1:5000")
    except Exception as e:
        logging.error("Error abriendo navegador: %s" % e)
        try:
            webbrowser.open("http://127.0.0.1:5000")
        except Exception:
            pass


# ─── Inicializar aplicacion Flask (en un hilo) ──────────────────────────────
def iniciar_servidor():
    from app import create_app
    from app.config import config_by_name

    try:
        env = os.environ.get("FLASK_ENV", "development")
        app = create_app(config_by_name.get(env, config_by_name["development"]))
        logging.info("Aplicacion lista en http://127.0.0.1:5000")
        # Sin reloader: el servidor vive en un hilo de segundo plano
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    except Exception:
        logging.exception("Error critico al iniciar el servidor Flask:")
        sys.exit(1)


# ─── Bandeja del sistema ─────────────────────────────────────────────────────
_salir = threading.Event()


def _construir_icono():
    try:
        from PIL import Image
        icon_path = getattr(sys, "_MEIPASS", SCRIPT_DIR)
        png = Path(icon_path) / "app" / "static" / "img" / "dlab_favicon.png"
        if png.exists():
            return Image.open(png)
        # Fallback: icono generado
        img = Image.new("RGBA", (64, 64), (15, 23, 42, 255))
        return img
    except Exception as e:
        logging.warning("No se pudo cargar el icono de bandeja: %s" % e)
        from PIL import Image
        return Image.new("RGBA", (64, 64), (15, 23, 42, 255))


def ejecutar_bandeja():
    import pystray
    from pystray import Menu, MenuItem

    imagen = _construir_icono()

    def abrir(icon, item=None):
        threading.Thread(target=abrir_navegador, daemon=True).start()

    def salir(icon, item):
        logging.info("Cerrando DLAB desde la bandeja.")
        icon.stop()
        _salir.set()

    icono = pystray.Icon(
        "DLAB CRM",
        imagen,
        "DLAB CRM Inmobiliaria",
        menu=Menu(
            MenuItem("Abrir sistema", abrir, default=True),
            MenuItem("Salir", salir),
        ),
    )

    # Primer arranque: abrir el navegador tras preparar la app
    threading.Timer(2.0, abrir_navegador).start()
    try:
        icono.run()
    except Exception as e:
        logging.exception("Error en bandeja del sistema: %s" % e)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Iniciando DLAB CRM (modo bandeja)...", flush=True)
    logging.info("Iniciando DLAB CRM (modo bandeja)...")

    hilo_server = threading.Thread(target=iniciar_servidor, daemon=True)
    hilo_server.start()

    ejecutar_bandeja()

    # Salida limpia cuando el icono se detiene
    os._exit(0)