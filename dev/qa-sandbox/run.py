import sys
import os
import logging
from pathlib import Path

# Asegurar que el CWD sea la carpeta del script
_script_dir = Path(__file__).resolve().parent
os.chdir(_script_dir)

try:
    from dotenv import load_dotenv
    load_dotenv(_script_dir / ".env")
except ImportError:
    pass


# Configurar logging en APPDATA
appdata_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
log_dir = Path(appdata_dir) / "DLAB_CRM" / "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = log_dir / "app.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Garantiza que las librerías instaladas en el perfil de usuario
# (google-auth, google-api-python-client) sean encontradas por Flask.
_user_pkg = os.path.expandvars(
    r"%APPDATA%\Python\Python313\site-packages"
)
if _user_pkg not in sys.path:
    sys.path.insert(0, _user_pkg)

from app import create_app
from app.config import config_by_name

try:
    logging.info("Iniciando creación de la aplicación Flask...")
    env = os.environ.get("FLASK_ENV", "development")
    app = create_app(config_by_name.get(env, config_by_name["development"]))
    logging.info("Aplicación Flask creada con éxito.")
    from app.core.logger import log_info, get_log_path
    log_info('SISTEMA', f'Aplicacion iniciada. Logs en: {get_log_path()}')
except Exception as e:
    logging.exception("Error crítico inicializando la aplicación Flask:")
    sys.exit(1)

import webbrowser
from threading import Timer

def open_browser():
    try:
        import subprocess
        logging.info("Intentando abrir el navegador...")
        subprocess.run(["cmd", "/c", "start", "http://127.0.0.1:5000/"], creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        logging.error(f"Error al intentar abrir el navegador: {e}")

if __name__ == "__main__":
    print("\n" + "="*50)
    print(" INICIANDO DLAB-DATA CRM...")
    print(" NO CIERRE ESTA VENTANA MIENTRAS USE EL SISTEMA.")
    print("="*50 + "\n", flush=True)
    
    logging.info("==================================================")
    logging.info(" INICIANDO DLAB-DATA CRM...")
    logging.info("==================================================")
    
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1.5, open_browser).start()
        
    try:
        host = os.environ.get("HOST", "127.0.0.1")
        port = int(os.environ.get("PORT", "5000"))
        app.run(host=host, port=port, debug=False)
    except Exception as e:
        logging.exception("Ocurrió un error fatal al intentar iniciar la aplicación.")
