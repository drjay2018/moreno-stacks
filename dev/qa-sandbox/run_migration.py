import sqlite3
import os
from pathlib import Path

# Resolucion de la ruta de la DB duplicada de app/config.py (mismo criterio:
# %APPDATA%/DLAB_CRM/data/dlab.db). No se importa app.config directamente
# porque `import app` dispara la inicializacion completa del paquete Flask
# (app/__init__.py) solo para leer una ruta. Si cambia la logica de
# resolucion en app/config.py, actualizar tambien aqui.
_appdata_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
db_paths = [
    str(Path(_appdata_dir) / "DLAB_CRM" / "data" / "dlab.db"),
]

queries = [
    # Modificaciones a entidades
    "ALTER TABLE entidades ADD COLUMN tipo_persona VARCHAR(20) DEFAULT 'Física';",
    "ALTER TABLE entidades ADD COLUMN aplica_itbis BOOLEAN DEFAULT 1;",
    
    # Modificaciones a transacciones
    "ALTER TABLE transacciones ADD COLUMN comision_empresa_sin_itbis NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN itbis_comision_empresa NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN comision_vendedor_bruta NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN tipo_persona_vendedor VARCHAR(20);",
    "ALTER TABLE transacciones ADD COLUMN aplica_itbis_vendedor BOOLEAN;",
    "ALTER TABLE transacciones ADD COLUMN pct_isr NUMERIC(5, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN retencion_isr NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN itbis_vendedor NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN pct_itbis_retenido NUMERIC(5, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN retencion_itbis NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN total_retenciones NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN neto_pagado_vendedor NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN costo_total_vendedor NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN ganancia_empresa_sin_itbis NUMERIC(14, 2) DEFAULT 0.0;",
    "ALTER TABLE transacciones ADD COLUMN margen_empresa_neto NUMERIC(14, 2) DEFAULT 0.0;",
]

for db_path in db_paths:
    if not os.path.exists(db_path):
        print(f"Skipping {db_path}, file not found.")
        continue
        
    print(f"Migrando {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    for q in queries:
        try:
            c.execute(q)
            print(f"OK: {q}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"SKIP: Columna ya existe: {q}")
            else:
                print(f"ERROR: {e} en consulta: {q}")
                
    # Update default values so existing transacciones are not completely empty
    try:
        c.execute("UPDATE transacciones SET tipo_persona_vendedor = 'Física', aplica_itbis_vendedor = 1 WHERE tipo_persona_vendedor IS NULL")
    except Exception as e:
        print("Error updating existing rows in transacciones", e)

    # Convert existing 'Asesor Senior con Equipo' roles to 'Asesor Junior' or something default
    try:
        c.execute("UPDATE entidades SET nivel = 'Asesor Junior' WHERE nivel = 'Asesor Senior con Equipo'")
        c.execute("UPDATE entidades SET nivel = 'Asesor Captador' WHERE nivel = 'Asesor Senior'")
    except Exception as e:
        print("Error updating roles", e)

    conn.commit()
    conn.close()

print("Migración finalizada.")
