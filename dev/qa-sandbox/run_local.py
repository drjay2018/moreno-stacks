import sys
import os
from pathlib import Path

# Asegurar que el CWD sea la carpeta del script (para .env, templates, etc.)
_script_dir = Path(__file__).resolve().parent
os.chdir(_script_dir)

try:
    from dotenv import load_dotenv
    load_dotenv(_script_dir / ".env")
except ImportError:
    pass

from app import create_app
from app.config import config_by_name

env = os.environ.get("FLASK_ENV", "development")
app = create_app(config_by_name.get(env, config_by_name["development"]))

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
