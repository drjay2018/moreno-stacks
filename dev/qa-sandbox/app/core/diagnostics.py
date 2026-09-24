"""
diagnostics.py — Recopilacion de diagnosticos y generacion de reportes de soporte.
El reporte se copia al portapapeles para enviar por WhatsApp/Telegram.
"""

import os
import platform
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_system_info() -> dict:
    """Recopila informacion basica del sistema."""
    from app.version import get_version, get_build

    appdata = os.environ.get("APPDATA", "")
    db_path = os.path.join(appdata, "DLAB_CRM", "data", "dlab.db")
    db_size_mb = 0
    if os.path.exists(db_path):
        db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)

    return {
        "version": get_version(),
        "build": get_build(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "db_size_mb": db_size_mb,
    }


def get_recent_log_lines(n: int = 50) -> list:
    """Retorna las ultimas N lineas del log del dia."""
    from app.core.logger import get_log_path

    logs_dir = get_log_path()
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(logs_dir, f"app_{today}.log")

    if not os.path.isfile(log_file):
        return ["No hay logs disponibles para hoy."]

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip() for line in lines[-n:]]
    except Exception:
        return ["Error leyendo archivos de log."]


def get_recent_errors(n: int = 10) -> list:
    """Retorna las ultimas N lineas de ERROR del log."""
    all_lines = get_recent_log_lines(200)
    error_lines = [l for l in all_lines if "ERROR" in l]
    return error_lines[-n:]


def get_db_info() -> dict:
    """Informacion basica de la base de datos."""
    appdata = os.environ.get("APPDATA", "")
    db_path = os.path.join(appdata, "DLAB_CRM", "data", "dlab.db")

    if not os.path.exists(db_path):
        return {"exists": False}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Contar tablas
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]

        # Contar registros en tablas principales
        tables_info = {}
        main_tables = ["clientes", "transacciones", "cobros", "usuarios", "entidades", "proyectos"]
        for table in main_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                tables_info[table] = cursor.fetchone()[0]
            except Exception:
                pass

        conn.close()

        return {
            "exists": True,
            "path": db_path,
            "size_mb": round(os.path.getsize(db_path) / (1024 * 1024), 2),
            "tables": table_count,
            "records": tables_info,
        }
    except Exception as e:
        return {"exists": True, "error": str(e)}


def generate_support_report(description: str, include_logs: bool = True, include_db_info: bool = True) -> str:
    """
    Genera un reporte formateado para enviar por WhatsApp/Telegram.
    """
    sys_info = get_system_info()
    report = []
    report.append("=" * 50)
    report.append("  [DLAB CRM - REPORTE DE SOPORTE]")
    report.append("=" * 50)
    report.append("")
    report.append(f"Version: {sys_info['version']} (build {sys_info['build']})")
    report.append(f"Python: {sys_info['python']}")
    report.append(f"SO: {sys_info['platform']}")
    report.append(f"Arquitectura: {sys_info['machine']}")
    report.append(f"Tamano DB: {sys_info['db_size_mb']} MB")
    report.append("")
    report.append("PROBLEMA REPORTADO:")
    report.append("-" * 30)
    report.append(description)
    report.append("")

    if include_db_info:
        db_info = get_db_info()
        if db_info.get("exists") and db_info.get("records"):
            report.append("REGISTROS EN DB:")
            report.append("-" * 30)
            for table, count in db_info["records"].items():
                report.append(f"  {table}: {count} registros")
            report.append("")

    if include_logs:
        errors = get_recent_errors(5)
        if errors:
            report.append("ULTIMOS ERRORES:")
            report.append("-" * 30)
            for err in errors:
                report.append(f"  {err[:200]}")
            report.append("")

        recent = get_recent_log_lines(20)
        if recent:
            report.append("LOGS RECIENTES (ultimas 20 lineas):")
            report.append("-" * 30)
            for line in recent:
                report.append(f"  {line[:200]}")
            report.append("")

    report.append("=" * 50)
    report.append(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("Enviar a: [tu numero de WhatsApp/Telegram]")

    return "\n".join(report)


def generate_support_report_json(description: str) -> dict:
    """Genera reporte en formato JSON para uso programatico."""
    sys_info = get_system_info()
    db_info = get_db_info()

    return {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "generator": "DLAB CRM Support Report",
        },
        "system": sys_info,
        "database": db_info,
        "problem": description,
        "errors": get_recent_errors(5),
        "recent_logs": get_recent_log_lines(30),
    }
