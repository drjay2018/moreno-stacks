"""
app/core/logger.py — Sistema de logging centralizado para DLAB CRM.

Usa TimedRotatingFileHandler para rotación diaria automática.
Escribe en %APPDATA%\\DLAB_CRM\\logs\\ con fallback a dlab-data\\logs\\.
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import date

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_LOGGER_NAME = 'dlab_crm'
_LOG_FORMAT   = '%(asctime)s | %(levelname)-8s | %(module)-20s | %(message)s'
_DATE_FORMAT  = '%Y-%m-%d %H:%M:%S'

# ---------------------------------------------------------------------------
# Directorio de logs
# ---------------------------------------------------------------------------

def _get_logs_dir() -> str:
    """
    Devuelve el directorio donde se almacenarán los logs.
    Prioridad: %APPDATA%\\DLAB_CRM\\logs
    Fallback:  H:\\Mi unidad\\Proyecto - CRM Inmobiliaria\\dlab-data\\logs
    """
    appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
    primary = os.path.join(appdata, 'DLAB_CRM', 'logs')
    try:
        os.makedirs(primary, exist_ok=True)
        # Verificar escritura
        _test = os.path.join(primary, '.write_test')
        with open(_test, 'w') as f:
            f.write('')
        os.remove(_test)
        return primary
    except OSError:
        pass

    # Fallback: carpeta relativa al proyecto
    fallback = os.path.join(
        os.path.dirname(__file__),          # …/app/core
        '..', '..', '..', 'dlab-data', 'logs'
    )
    fallback = os.path.normpath(fallback)
    os.makedirs(fallback, exist_ok=True)
    return fallback


# ---------------------------------------------------------------------------
# Configuración del logger
# ---------------------------------------------------------------------------

def setup_logger() -> logging.Logger:
    """
    Inicializa y devuelve el logger 'dlab_crm'.
    Guarda-idempotente: si ya tiene handlers no los duplica.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    logs_dir = _get_logs_dir()
    log_file = os.path.join(
        logs_dir,
        f'app_{date.today().strftime("%Y-%m-%d")}.log'
    )

    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- Handler de archivo con rotación diaria a medianoche ---
    fh = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        backupCount=30,
        encoding='utf-8',
        delay=False
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # --- Handler de consola (solo INFO+) ---
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Evitar propagación al root logger (logging.basicConfig en run.py)
    logger.propagate = False

    return logger


# ---------------------------------------------------------------------------
# Instancia global (se crea una sola vez al importar el módulo)
# ---------------------------------------------------------------------------
_logger = setup_logger()


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def log_info(module: str, msg: str) -> None:
    """Registra un mensaje de nivel INFO con prefijo de módulo."""
    _logger.info(f'[{module}] {msg}')


def log_warn(module: str, msg: str) -> None:
    """Registra un mensaje de nivel WARNING con prefijo de módulo."""
    _logger.warning(f'[{module}] {msg}')


def log_error(module: str, msg: str, exc_info=None) -> None:
    """
    Registra un mensaje de nivel ERROR con prefijo de módulo.
    :param exc_info: True para incluir el traceback actual,
                     o una tupla (type, value, tb) explícita.
    """
    _logger.error(f'[{module}] {msg}', exc_info=exc_info)


def get_log_path() -> str:
    """Devuelve el directorio de logs activo."""
    return _get_logs_dir()
