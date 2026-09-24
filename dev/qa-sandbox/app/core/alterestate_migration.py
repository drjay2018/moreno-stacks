"""
alterestate_migration.py — Migraciones de DB para la integracion AlterEstate.

Ejecutar con:
    python -m app.core.alterestate_migration

Crea las tablas necesarias si no existen (idempotente).
"""

import logging
from sqlalchemy import text
from app.extensions import db

logger = logging.getLogger(__name__)

# ─── SQL de creacion de tablas ──────────────────────────────────────────────────

MIGRATIONS = [
    # Tabla de mapping entre entidades externas (AE) e internas (DLAB)
    """
    CREATE TABLE IF NOT EXISTS api_entity_mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        external_id TEXT NOT NULL,
        external_uid TEXT,
        internal_id INTEGER NOT NULL,
        internal_table TEXT NOT NULL,
        match_key TEXT,
        extra_meta TEXT DEFAULT '{}',
        sync_hash TEXT,
        last_synced_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, entity_type, external_id)
    )
    """,

    # Indices para busquedas frecuentes
    "CREATE INDEX IF NOT EXISTS idx_api_mapping_provider ON api_entity_mapping(provider, entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_api_mapping_internal ON api_entity_mapping(internal_table, internal_id)",
    "CREATE INDEX IF NOT EXISTS idx_api_mapping_external ON api_entity_mapping(provider, external_id)",

    # Tabla de paises
    """
    CREATE TABLE IF NOT EXISTS cat_paises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        codigo_iso TEXT,
        telefono_codigo TEXT,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Tabla de ciudades
    """
    CREATE TABLE IF NOT EXISTS cat_ciudades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ae_city_id TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        pais_id INTEGER,
        pais_nombre TEXT,
        provincia TEXT,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(pais_id) REFERENCES cat_paises(id)
    )
    """,

    # Tabla de sectores
    """
    CREATE TABLE IF NOT EXISTS cat_sectores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ae_sector_id TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        ciudad_id INTEGER,
        ciudad_nombre TEXT,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(ciudad_id) REFERENCES cat_ciudades(id)
    )
    """,

    # Indices para busquedas geograficas
    "CREATE INDEX IF NOT EXISTS idx_cat_ciudades_pais ON cat_ciudades(pais_id)",
    "CREATE INDEX IF NOT EXISTS idx_cat_sectores_ciudad ON cat_sectores(ciudad_id)",

    # Tabla de tipos de inmueble
    """
    CREATE TABLE IF NOT EXISTS cat_tipos_inmueble (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        ae_category_id INTEGER,
        icono TEXT,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Tabla de tipos de listado (Venta/Alquiler)
    """
    CREATE TABLE IF NOT EXISTS cat_tipos_listado (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        ae_listing_type_id INTEGER,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Tabla de estados de unidad
    """
    CREATE TABLE IF NOT EXISTS cat_estados_unidad (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        ae_status_code INTEGER,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Tabla de condiciones de inmueble
    """
    CREATE TABLE IF NOT EXISTS cat_condiciones_inmueble (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        ae_condition_id INTEGER,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Tabla de amenidades
    """
    CREATE TABLE IF NOT EXISTS cat_amenidades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        ae_amenity_id INTEGER,
        icono TEXT,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Tabla de monedas
    """
    CREATE TABLE IF NOT EXISTS cat_monedas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        simbolo TEXT,
        activo INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

# ─── Seed data para catalogos ─────────────────────────────────────────────────

SEEDS = [
    # cat_tipos_inmueble (17 categorias AE)
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Apartamento', 1, 'apartment')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Casa', 2, 'house')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Edificio', 3, 'building')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Solar/Lote', 4, 'land')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Hotel', 5, 'hotel')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Local Comercial', 6, 'commercial')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Nave Industrial', 7, 'industrial')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Penthouse', 10, 'penthouse')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Villa', 13, 'villa')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Loft', 14, 'loft')",),
    ("INSERT OR IGNORE INTO cat_tipos_inmueble (nombre, ae_category_id, icono) VALUES ('Townhouse', 17, 'townhouse')",),

    # cat_tipos_listado
    ("INSERT OR IGNORE INTO cat_tipos_listado (nombre, ae_listing_type_id) VALUES ('Venta', 1)",),
    ("INSERT OR IGNORE INTO cat_tipos_listado (nombre, ae_listing_type_id) VALUES ('Alquiler', 2)",),

    # cat_estados_unidad
    ("INSERT OR IGNORE INTO cat_estados_unidad (nombre, ae_status_code) VALUES ('Disponible', 1)",),
    ("INSERT OR IGNORE INTO cat_estados_unidad (nombre, ae_status_code) VALUES ('Reservado', 2)",),
    ("INSERT OR IGNORE INTO cat_estados_unidad (nombre, ae_status_code) VALUES ('Vendido', 3)",),
    ("INSERT OR IGNORE INTO cat_estados_unidad (nombre, ae_status_code) VALUES ('Bloqueado', 11)",),

    # cat_condiciones_inmueble
    ("INSERT OR IGNORE INTO cat_condiciones_inmueble (nombre, ae_condition_id) VALUES ('En Construccion', 5)",),
    ("INSERT OR IGNORE INTO cat_condiciones_inmueble (nombre, ae_condition_id) VALUES ('Listo / Entregado', 9)",),

    # cat_amenidades (desde AE)
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Piscina', 74, 'pool')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Terraza Compartida', 77, 'terrace')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Terraza Exclusiva', 516, 'terrace')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Gimnasio', 73, 'gym')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Linea Blanca', 66, 'white_line')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Seguridad 24h', NULL, 'security')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Ascensor', NULL, 'elevator')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Parqueo Techado', NULL, 'parking')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Area Social', NULL, 'social')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Balcon/Terraza', NULL, 'balcony')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Area Ninos', NULL, 'kids')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Cancha Deportiva', NULL, 'sports')",),
    ("INSERT OR IGNORE INTO cat_amenidades (nombre, ae_amenity_id, icono) VALUES ('Mascotas', NULL, 'pets')",),

    # cat_monedas
    ("INSERT OR IGNORE INTO cat_monedas (codigo, nombre, simbolo) VALUES ('USD', 'Dolar Estadounidense', '$')",),
    ("INSERT OR IGNORE INTO cat_monedas (codigo, nombre, simbolo) VALUES ('DOP', 'Peso Dominicano', 'RD$')",),
    ("INSERT OR IGNORE INTO cat_monedas (codigo, nombre, simbolo) VALUES ('MXN', 'Peso Mexicano', 'MX$')",),
    ("INSERT OR IGNORE INTO cat_monedas (codigo, nombre, simbolo) VALUES ('COP', 'Peso Colombiano', 'COL$')",),
    ("INSERT OR IGNORE INTO cat_monedas (codigo, nombre, simbolo) VALUES ('CRC', 'Colon Costarricense', '₡')",),
    ("INSERT OR IGNORE INTO cat_monedas (codigo, nombre, simbolo) VALUES ('GTQ', 'Quetzal Guatemalteco', 'Q')",),
    ("INSERT OR IGNORE INTO cat_monedas (codigo, nombre, simbolo) VALUES ('PEN', 'Sol Peruano', 'S/')",),
]


def run_migration():
    """Ejecuta todas las migraciones de forma idempotente."""
    migraciones_aplicadas = 0
    migraciones_fallidas = 0

    for i, sql in enumerate(MIGRATIONS):
        try:
            db.session.execute(text(sql.strip()))
            db.session.commit()
            migraciones_aplicadas += 1
        except Exception as e:
            # "table already exists" es esperado en migraciones idempotentes
            if "already exists" in str(e).lower():
                migraciones_aplicadas += 1
            else:
                migraciones_fallidas += 1
                logger.warning(f"Migracion {i+1} falló: {e}")

    # ─── Seed data ──────────────────────────────────────────────────────────────
    seeds_insertados = 0
    for seed_tuple in SEEDS:
        try:
            db.session.execute(text(seed_tuple[0].strip()))
            db.session.commit()
            seeds_insertados += 1
        except Exception:
            pass  # Registro ya existe

    logger.info(
        f"Migraciones AlterEstate: {migraciones_aplicadas} aplicadas, "
        f"{migraciones_fallidas} fallidas, {seeds_insertados} seeds insertados"
    )

    # ─── Migraciones ALTER TABLE para tablas existentes ──────────────────────────
    alter_migrations = [
        ("proyectos", "atributos_extra", "JSON DEFAULT '{}'"),
        ("proyectos", "descripcion", "TEXT"),
        ("cat_ciudades", "provincia", "TEXT"),
        ("cat_ciudades", "ae_city_id", "TEXT"),
        ("cat_sectores", "ae_sector_id", "TEXT"),
        # === Campos de captacion (xlsx) ===
        ("transacciones", "promocion", "VARCHAR(100)"),
        ("transacciones", "adicionales", "TEXT"),
        ("transacciones", "moneda", "VARCHAR(5) DEFAULT 'USD'"),
        ("transacciones", "tiempo_entrega", "DATE"),
        ("transacciones", "plan_pago_tipo", "VARCHAR(30)"),
        ("transacciones", "descuento_pct", "NUMERIC(5,2) DEFAULT 0"),
        # === Comision gerencia 50/50 ===
        ("transacciones", "comision_gerencia_total", "NUMERIC(14,2) DEFAULT 0"),
        ("transacciones", "comision_gerencia_pagada", "NUMERIC(14,2) DEFAULT 0"),
        ("transacciones", "comision_gerencia_saldo", "NUMERIC(14,2) DEFAULT 0"),
        ("transacciones", "gastos_legales", "NUMERIC(14,2) DEFAULT 0"),
        # === Dropbox documentos ===
        ("transacciones", "dropbox_plan_pago", "TEXT"),
        ("transacciones", "dropbox_reserva", "TEXT"),
        ("transacciones", "dropbox_kyc", "TEXT"),
        ("transacciones", "dropbox_contrato", "TEXT"),
        ("transacciones", "dropbox_pago_inicial", "TEXT"),
        # === Fix campos perdidos ===
        ("clientes", "sector", "VARCHAR(80)"),
        ("clientes", "institucion_bancaria", "VARCHAR(80)"),
        # === Identificador de inmueble ===
        ("transacciones", "nombre_propiedad", "VARCHAR(120)"),
        ("transacciones", "numero_inmueble", "VARCHAR(30)"),
    ]
    for table, col, col_type in alter_migrations:
        try:
            db.session.execute(text(f"PRAGMA table_info({table})"))
            existing = [row[1] for row in db.session.execute(text(f"PRAGMA table_info({table})")).fetchall()]
            if col not in existing:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                db.session.commit()
                logger.info(f"ALTER TABLE {table} ADD COLUMN {col}")
        except Exception as e:
            logger.warning(f"ALTER {table}.{col}: {e}")

    return {
        "aplicadas": migraciones_aplicadas,
        "fallidas": migraciones_fallidas,
        "seeds": seeds_insertados,
        "total": len(MIGRATIONS) + len(SEEDS),
    }


if __name__ == "__main__":
    # Ejecutar standalone
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

    from app import create_app
    app = create_app()

    with app.app_context():
        result = run_migration()
        print(f"Migracion completada: {result}")
