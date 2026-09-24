"""
db_migrations.py — OBSOLETO, no usar en instalaciones nuevas.

Toda la logica de este script (columnas anadidas a campanas, proveedores,
clientes, entidades, proyectos, cat_ciudades, cat_sectores, y el seed de
kpi_config) fue absorbida de forma idempotente en la revision Alembic
`migrations/versions/002_absorber_db_migrations.py` (down_revision='001').

Este archivo se conserva solo por compatibilidad historica (por si alguien
lo invoca manualmente en una instalacion antigua ya acostumbrada a ese
flujo) y por que no hay ningun .bat/.ps1 ni modulo del repo que lo importe
o lo ejecute automaticamente (se verifico con busqueda global). Para
aplicar/actualizar el esquema en instalaciones nuevas o existentes, usar:

    cd dlab-app
    python -m alembic upgrade head

No anadir cambios de esquema aqui: cualquier columna o seed nuevo debe ir
en una nueva revision Alembic bajo migrations/versions/.
"""
import sqlite3
import sys
import os
from pathlib import Path

# Correct path from config.py: BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Script is in dlab-app/, so BASE_DIR = parent of dlab-app
# DB_PATH = BASE_DIR / "dlab-data" / "data" / "dlab.db"
# But script runs from dlab-app/, so:
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "dlab-data" / "data" / "dlab.db"

print(f"DB Path: {DB_PATH}")
print(f"Exists: {DB_PATH.exists()}")

if not DB_PATH.exists():
    # Try alternate paths
    appdata_db = Path(os.environ.get("APPDATA", Path.home())) / "DLAB_CRM" / "data" / "dlab.db"
    for alt in [
        appdata_db,
        Path(__file__).resolve().parent / "dlab-data" / "data" / "dlab.db",
        Path(r"H:\Mi unidad\Proyecto - CRM Inmobiliaria\dlab-data\data\dlab.db"),
    ]:
        print(f"Trying: {alt} — exists: {alt.exists()}")
        if alt.exists():
            DB_PATH = alt
            break

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f"\nTables: {tables}")

def add_column_if_not_exists(table, column, col_type, default=None):
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    if column not in cols:
        sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
        if default is not None:
            sql += f" DEFAULT {default}"
        cur.execute(sql)
        print(f"  + Added {table}.{column}")
    else:
        print(f"  = {table}.{column} exists")

print("\n=== Migrations ===")

print("\n[campanas] Adding metrics columns:")
add_column_if_not_exists('campanas', 'impresiones', 'INTEGER', 0)
add_column_if_not_exists('campanas', 'clics', 'INTEGER', 0)
add_column_if_not_exists('campanas', 'alcance', 'INTEGER', 0)
add_column_if_not_exists('campanas', 'leads_generados', 'INTEGER', 0)

print("\n[proveedores] Adding descripcion:")
add_column_if_not_exists('proveedores', 'descripcion', 'TEXT')

print("\n[clientes] Adding presupuesto_rango:")
add_column_if_not_exists('clientes', 'presupuesto_rango', 'VARCHAR(60)')

print("\n[entidades/empleados] Adding empresa:")
add_column_if_not_exists('entidades', 'empresa', 'VARCHAR(150)')

print("\n[proyectos] Adding atributos_extra for AlterEstate sync:")
add_column_if_not_exists('proyectos', 'atributos_extra', 'JSON', "'{}'")
add_column_if_not_exists('proyectos', 'descripcion', 'TEXT')

print("\n[cat_ciudades] Adding AlterEstate columns:")
add_column_if_not_exists('cat_ciudades', 'provincia', 'TEXT')
add_column_if_not_exists('cat_ciudades', 'ae_city_id', 'TEXT')

print("\n[cat_sectores] Adding AlterEstate columns:")
add_column_if_not_exists('cat_sectores', 'ae_sector_id', 'TEXT')

print("\n[kpi_config] Checking rows:")
cur.execute("SELECT COUNT(*) FROM kpi_config")
count = cur.fetchone()[0]
print(f"  kpi_config has {count} rows")

if count == 0:
    kpis_base = [
        ('volumen_ventas', 'Volumen de Ventas', 'Comercial', 'USD', 1000000, 800000, 500000, 1),
        ('total_cierres', 'Cierres Aprobados', 'Transacciones', 'unidades', 20, 15, 8, 1),
        ('mora_critica', 'Mora Critica (>60d)', 'Cobros', 'USD', 0, 50000, 100000, 0),
        ('incidentes_abiertos', 'Incidentes Abiertos', 'Cumplimiento', 'unidades', 0, 3, 8, 0),
        ('total_clientes', 'Clientes Activos', 'Cartera', 'unidades', 100, 60, 30, 1),
        ('total_proyectos', 'Proyectos Activos', 'Inventario', 'unidades', 5, 3, 1, 1),
        ('comisiones_pendientes', 'Comisiones Pendientes', 'Comisiones', 'USD', 0, 50000, 100000, 0),
        ('cierres_sla', 'Cierres Fuera SLA', 'Cumplimiento', 'unidades', 0, 2, 5, 0),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO kpi_config (kpi_id, nombre, categoria, unidad, meta, umbral_amarillo, umbral_rojo, mayor_es_mejor) VALUES (?,?,?,?,?,?,?,?)",
        kpis_base
    )
    print(f"  Inserted {len(kpis_base)} KPIs")

conn.commit()
conn.close()
print("\n=== Done ===")
