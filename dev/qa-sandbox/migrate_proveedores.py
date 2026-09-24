import sqlite3
import os
import sys
from pathlib import Path

# Resolucion de la ruta de la DB duplicada de app/config.py (mismo criterio:
# %APPDATA%/DLAB_CRM/data/dlab.db). No se importa app.config directamente
# porque `import app` dispara la inicializacion completa del paquete Flask
# (app/__init__.py) solo para leer una ruta. Si cambia la logica de
# resolucion en app/config.py, actualizar tambien aqui.
_appdata_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
db_path = str(Path(_appdata_dir) / "DLAB_CRM" / "data" / "dlab.db")

if not os.path.exists(db_path):
    print(f"ERROR: DB not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    # 1. Crear tabla de proveedores
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        razon_social VARCHAR(255) NOT NULL,
        ruc VARCHAR(50),
        email VARCHAR(100),
        telefono VARCHAR(50),
        direccion TEXT,
        estado VARCHAR(20) DEFAULT 'activo',
        fecha_registro DATE DEFAULT CURRENT_DATE
    )
    """)
    print("Tabla 'proveedores' creada/verificada.")

    # Insertar un proveedor por defecto si no existe
    cur.execute("SELECT COUNT(id) FROM proveedores")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO proveedores (razon_social, ruc, estado) 
        VALUES ('Proveedor General', '0000000000', 'activo')
        """)
        print("Proveedor por defecto insertado.")

    # 2. Alterar compras
    # Revisar si ya existe la columna
    cur.execute("PRAGMA table_info(compras)")
    cols = [r[1] for r in cur.fetchall()]
    
    if "proveedor_id" not in cols:
        cur.execute("ALTER TABLE compras ADD COLUMN proveedor_id INTEGER REFERENCES proveedores(id)")
        print("Columna 'proveedor_id' añadida a 'compras'.")
        
        # Asignar proveedor por defecto a las compras existentes
        cur.execute("UPDATE compras SET proveedor_id = 1 WHERE proveedor_id IS NULL")
        print("Compras existentes actualizadas con proveedor_id = 1.")
    else:
        print("Columna 'proveedor_id' ya existe en 'compras'.")

    # 3. Crear tabla compras_facturas
    cur.execute("""
    CREATE TABLE IF NOT EXISTS compras_facturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        compra_id INTEGER NOT NULL REFERENCES compras(id),
        proveedor_id INTEGER NOT NULL REFERENCES proveedores(id),
        numero_factura VARCHAR(100),
        monto_factura NUMERIC(14,2),
        ruta_archivo_pdf VARCHAR(255) NOT NULL,
        fecha_subida DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("Tabla 'compras_facturas' creada/verificada.")

    conn.commit()
    print("Migración completada exitosamente.")

except Exception as e:
    conn.rollback()
    print(f"Error durante migración: {e}")
finally:
    conn.close()
