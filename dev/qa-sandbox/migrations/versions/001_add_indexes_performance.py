"""add_indexes_performance

Revision ID: 001
Revises: 
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '001'
down_revision = '000_baseline_canonico'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =====================================================================
    # INDEXES for JOIN columns (foreign keys without implicit indexes)
    # =====================================================================
    
    # transacciones - most queried table
    op.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_estado ON transacciones(estado)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_fecha_evento ON transacciones(fecha_evento)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_proyecto_id ON transacciones(proyecto_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_entidad_id ON transacciones(entidad_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_cliente_id ON transacciones(cliente_id)")
    
    # cobros
    op.execute("CREATE INDEX IF NOT EXISTS idx_cobros_transaccion_id ON cobros(transaccion_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cobros_fecha_vencimiento ON cobros(fecha_vencimiento)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cobros_estado_aging_id ON cobros(estado_aging_id)")
    
    # pagos
    op.execute("CREATE INDEX IF NOT EXISTS idx_pagos_cobro_id ON pagos(cobro_id)")
    
    # campanas
    op.execute("CREATE INDEX IF NOT EXISTS idx_campanas_proyecto_id ON campanas(proyecto_id)")
    
    # compras
    op.execute("CREATE INDEX IF NOT EXISTS idx_compras_estado ON compras(estado)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_compras_proveedor_id ON compras(proveedor_id)")
    
    # compras_pagos
    op.execute("CREATE INDEX IF NOT EXISTS idx_compras_pagos_compra_id ON compras_pagos(compra_id)")
    
    # comisiones_pagos
    op.execute("CREATE INDEX IF NOT EXISTS idx_comisiones_pagos_transaccion_id ON comisiones_pagos(transaccion_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_comisiones_pagos_entidad_id ON comisiones_pagos(entidad_id)")
    
    # auditoria
    op.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_usuario_id ON auditoria(usuario_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria(fecha)")
    
    # clientes
    op.execute("CREATE INDEX IF NOT EXISTS idx_clientes_vendedor_captador_id ON clientes(vendedor_captador_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_clientes_cedula ON clientes(cedula)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_clientes_etapa_embudo ON clientes(etapa_embudo)")
    
    # entidades
    op.execute("CREATE INDEX IF NOT EXISTS idx_entidades_supervisor_id ON entidades(supervisor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_entidades_nivel ON entidades(nivel)")
    
    # proyectos
    op.execute("CREATE INDEX IF NOT EXISTS idx_proyectos_contraparte_id ON proyectos(contraparte_id)")
    
    # compromisos
    op.execute("CREATE INDEX IF NOT EXISTS idx_compromisos_proyecto_id ON compromisos(proyecto_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_compromisos_contraparte_id ON compromisos(contraparte_id)")


def downgrade() -> None:
    indexes = [
        "idx_transacciones_estado",
        "idx_transacciones_fecha_evento",
        "idx_transacciones_proyecto_id",
        "idx_transacciones_entidad_id",
        "idx_transacciones_cliente_id",
        "idx_cobros_transaccion_id",
        "idx_cobros_fecha_vencimiento",
        "idx_cobros_estado_aging_id",
        "idx_pagos_cobro_id",
        "idx_campanas_proyecto_id",
        "idx_compras_estado",
        "idx_compras_proveedor_id",
        "idx_compras_pagos_compra_id",
        "idx_comisiones_pagos_transaccion_id",
        "idx_comisiones_pagos_entidad_id",
        "idx_auditoria_usuario_id",
        "idx_auditoria_fecha",
        "idx_clientes_vendedor_captador_id",
        "idx_clientes_cedula",
        "idx_clientes_etapa_embudo",
        "idx_entidades_supervisor_id",
        "idx_entidades_nivel",
        "idx_proyectos_contraparte_id",
        "idx_compromisos_proyecto_id",
        "idx_compromisos_contraparte_id",
    ]
    for idx in indexes:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
