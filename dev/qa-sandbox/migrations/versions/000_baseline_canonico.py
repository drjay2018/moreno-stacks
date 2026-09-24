"""baseline_canonico

Revision ID: 000_baseline_canonico
Revises:
Create Date: 2026-09-05

Baseline idempotente que construye el esquema canonico (db_schema.sql) en
bases nuevas. En instalaciones existentes no altera nada (IF NOT EXISTS).
La revision 001 (indices de rendimiento) depende de esta baseline.

"""
from alembic import op
from pathlib import Path


# revision identifiers
revision = '000_baseline_canonico'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = Path(__file__).resolve().parent.parent.parent / "db_schema.sql"
    if not schema.exists():
        raise RuntimeError(f"No se encontro el esquema canonico: {schema}")
    consultas = schema.read_text(encoding="utf-8")
    for sentencia in consultas.split(";"):
        sentencia = sentencia.strip()
        if not sentencia or sentencia.startswith("--"):
            continue
        if sentencia.lower().startswith("create table"):
            sentencia = sentencia.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
        op.execute(sentencia)


def downgrade() -> None:
    # No destructivo por diseno: las instalaciones existentes conservan sus datos.
    pass