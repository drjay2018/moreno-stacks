"""absorber_db_migrations

Revision ID: 002
Revises: 001
Create Date: 2026-09-09

Absorbe en Alembic los cambios de esquema que hasta ahora solo aplicaba el
script suelto `db_migrations.py` (sqlite3 crudo, no versionado, con rutas
de localizacion de la DB hardcodeadas). Reproduce exactamente las mismas
columnas y el mismo seed de `kpi_config` que ese script, de forma
idempotente (se comprueba la existencia de tabla/columna antes de tocar
nada), para que `alembic upgrade head` deje la base de datos en el mismo
estado sin depender de ejecutar manualmente `db_migrations.py`.

Notas de auditoria (para quien revise esta revision):
- La mayoria de estas columnas YA estan incluidas en el esquema canonico
  (db_schema.sql / revision 000_baseline_canonico) en instalaciones
  nuevas: campanas.{impresiones,clics,alcance,leads_generados},
  proveedores.descripcion, clientes.presupuesto_rango, entidades.empresa,
  proyectos.{atributos_extra,descripcion}. Aqui se repiten solo para cubrir
  bases de datos antiguas que se crearon antes de que esas columnas
  entraran al esquema canonico.
- cat_ciudades y cat_sectores NO forman parte del esquema canonico: las
  crea en caliente `app/core/alterestate_migration.py` (fuera del alcance
  de esta migracion) durante el arranque de la app, ya con las columnas
  provincia/ae_city_id/ae_sector_id incluidas en el CREATE TABLE. En una
  instalacion nueva basada solo en `alembic upgrade head` (sin arrancar la
  app todavia) esas tablas aun no existiran; este upgrade lo detecta y no
  hace nada en ese caso, sin fallar.
- El seed de las 8 filas de `kpi_config` es la UNICA pieza de
  `db_migrations.py` que no se reproduce en ningun otro lugar del repo
  (ni en db_schema.sql ni en alterestate_migration.py). Sin esta revision,
  una instalacion nueva basada solo en Alembic quedaria con `kpi_config`
  vacio y el dashboard de KPIs sin umbrales configurados.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


# Los 8 KPIs base sembrados originalmente por db_migrations.py.
_KPIS_BASE = [
    ('volumen_ventas', 'Volumen de Ventas', 'Comercial', 'USD', 1000000, 800000, 500000, 1),
    ('total_cierres', 'Cierres Aprobados', 'Transacciones', 'unidades', 20, 15, 8, 1),
    ('mora_critica', 'Mora Critica (>60d)', 'Cobros', 'USD', 0, 50000, 100000, 0),
    ('incidentes_abiertos', 'Incidentes Abiertos', 'Cumplimiento', 'unidades', 0, 3, 8, 0),
    ('total_clientes', 'Clientes Activos', 'Cartera', 'unidades', 100, 60, 30, 1),
    ('total_proyectos', 'Proyectos Activos', 'Inventario', 'unidades', 5, 3, 1, 1),
    ('comisiones_pendientes', 'Comisiones Pendientes', 'Comisiones', 'USD', 0, 50000, 100000, 0),
    ('cierres_sla', 'Cierres Fuera SLA', 'Cumplimiento', 'unidades', 0, 2, 5, 0),
]


def _columnas(inspector, tabla):
    return {c['name'] for c in inspector.get_columns(tabla)}


def _add_column_if_not_exists(inspector, tabla, columna, tipo, **kwargs):
    if columna not in _columnas(inspector, tabla):
        op.add_column(tabla, sa.Column(columna, tipo, **kwargs))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tablas = set(inspector.get_table_names())

    # --- campanas: metricas ------------------------------------------------
    if 'campanas' in tablas:
        _add_column_if_not_exists(inspector, 'campanas', 'impresiones', sa.Integer(), server_default='0')
        _add_column_if_not_exists(inspector, 'campanas', 'clics', sa.Integer(), server_default='0')
        _add_column_if_not_exists(inspector, 'campanas', 'alcance', sa.Integer(), server_default='0')
        _add_column_if_not_exists(inspector, 'campanas', 'leads_generados', sa.Integer(), server_default='0')

    # --- proveedores.descripcion --------------------------------------------
    if 'proveedores' in tablas:
        _add_column_if_not_exists(inspector, 'proveedores', 'descripcion', sa.Text())

    # --- clientes.presupuesto_rango -----------------------------------------
    if 'clientes' in tablas:
        _add_column_if_not_exists(inspector, 'clientes', 'presupuesto_rango', sa.String(60))

    # --- entidades.empresa ---------------------------------------------------
    if 'entidades' in tablas:
        _add_column_if_not_exists(inspector, 'entidades', 'empresa', sa.String(150))

    # --- proyectos: atributos_extra / descripcion (sync AlterEstate) --------
    if 'proyectos' in tablas:
        _add_column_if_not_exists(inspector, 'proyectos', 'atributos_extra', sa.JSON(), server_default="'{}'")
        _add_column_if_not_exists(inspector, 'proyectos', 'descripcion', sa.Text())

    # --- cat_ciudades / cat_sectores (sync AlterEstate) ---------------------
    # Estas tablas no existen en el esquema canonico; las crea en caliente
    # app/core/alterestate_migration.py. Si aun no existen, no hacemos nada.
    if 'cat_ciudades' in tablas:
        _add_column_if_not_exists(inspector, 'cat_ciudades', 'provincia', sa.Text())
        _add_column_if_not_exists(inspector, 'cat_ciudades', 'ae_city_id', sa.Text())

    if 'cat_sectores' in tablas:
        _add_column_if_not_exists(inspector, 'cat_sectores', 'ae_sector_id', sa.Text())

    # --- kpi_config: seed de 8 KPIs base ------------------------------------
    if 'kpi_config' in tablas:
        insert_kpi = sa.text(
            "INSERT OR IGNORE INTO kpi_config "
            "(kpi_id, nombre, categoria, unidad, meta, umbral_amarillo, umbral_rojo, mayor_es_mejor) "
            "VALUES (:kpi_id, :nombre, :categoria, :unidad, :meta, :umbral_amarillo, :umbral_rojo, :mayor_es_mejor)"
        )
        for kpi_id, nombre, categoria, unidad, meta, umbral_amarillo, umbral_rojo, mayor_es_mejor in _KPIS_BASE:
            bind.execute(
                insert_kpi,
                {
                    "kpi_id": kpi_id,
                    "nombre": nombre,
                    "categoria": categoria,
                    "unidad": unidad,
                    "meta": meta,
                    "umbral_amarillo": umbral_amarillo,
                    "umbral_rojo": umbral_rojo,
                    "mayor_es_mejor": mayor_es_mejor,
                },
            )


def downgrade() -> None:
    # No destructivo por diseno, igual que 000_baseline_canonico: no se
    # eliminan columnas ni filas de kpi_config para no arriesgar datos de
    # instalaciones existentes.
    pass
