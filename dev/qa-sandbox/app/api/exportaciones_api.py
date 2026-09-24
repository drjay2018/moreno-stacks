"""
exportaciones_api.py — Endpoints API para disparar exportaciones automáticas.
"""

from flask import Blueprint, jsonify, request, current_app
from app.core.auth_middleware import requiere_rol
from pathlib import Path
from datetime import datetime
from app.extensions import db
from sqlalchemy import text
import os
import logging

logger = logging.getLogger(__name__)

try:
    import pandas as pd
    from dateutil.relativedelta import relativedelta
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

exportaciones_api_bp = Blueprint("exportaciones_api", __name__, url_prefix="/api/exportaciones")

def get_date_filter(periodo):
    now = datetime.now()
    if periodo == 'ultimo_mes':
        return (now - relativedelta(months=1)).strftime('%Y-%m-%d')
    elif periodo == '6_meses':
        return (now - relativedelta(months=6)).strftime('%Y-%m-%d')
    return '1970-01-01'

@exportaciones_api_bp.route("/generar-bi", methods=["POST"])
@requiere_rol("Admin")
def generar_bi():
    try:
        data = request.json or {}
        periodo = data.get('periodo', 'historico')
        fecha_min = get_date_filter(periodo)

        base_dir = Path(current_app.root_path).parent / 'data' / 'exports'
        parquet_dir = base_dir / 'parquet'
        json_dir = base_dir / 'json'
        excel_dir = base_dir / 'excel'
        
        parquet_dir.mkdir(parents=True, exist_ok=True)
        json_dir.mkdir(parents=True, exist_ok=True)
        excel_dir.mkdir(parents=True, exist_ok=True)

        ALLOWED_TABLES = {'transacciones', 'clientes', 'proyectos', 'entidades', 'cobros'}

        with db.engine.connect() as conn:
            for table in ALLOWED_TABLES:
                where_clause = ""
                params = {}
                if table == 'transacciones':
                    where_clause = "WHERE fecha_evento >= :fecha_min"
                    params = {"fecha_min": fecha_min}
                elif table == 'clientes':
                    where_clause = "WHERE fecha_captacion >= :fecha_min"
                    params = {"fecha_min": fecha_min}

                df = pd.read_sql_query(f"SELECT * FROM {table} {where_clause}", conn, params=params)
                
                if not df.empty:
                    df.to_parquet(parquet_dir / f'{table}.parquet', index=False)
                    df.to_json(json_dir / f'{table}.json', orient='records', force_ascii=False)

            query_detalle_vendedores = """
                SELECT 
                    e.nombre || ' ' || e.apellido as Vendedor,
                    e.nivel as Nivel_Vendedor,
                    t.tipo_persona_vendedor as Tipo_Persona,
                    t.codigo as Transaccion,
                    t.fecha_evento as Fecha,
                    c.nombre || ' ' || c.apellido as Cliente,
                    c.genero as Genero_Cliente,
                    p.nombre as Proyecto,
                    p.financiamiento as Financiamiento,
                    t.unidad as Unidad,
                    t.monto as Monto_Venta,
                    t.comision_vendedor_bruta as Comision_Bruta,
                    t.retencion_isr as ISR_Retenido,
                    t.retencion_itbis as ITBIS_Retenido,
                    t.neto_pagado_vendedor as Neto_Pagado,
                    t.estado as Estado
                FROM transacciones t
                LEFT JOIN entidades e ON t.entidad_id = e.id
                LEFT JOIN clientes c ON t.cliente_id = c.id
                LEFT JOIN proyectos p ON t.proyecto_id = p.id
                WHERE t.fecha_evento >= :fecha_min
                ORDER BY Vendedor, t.fecha_evento DESC
            """
            
            query_detalle_constructoras = """
                SELECT 
                    cp.nombre as Constructora,
                    cp.sector as Sector_Constructora,
                    p.nombre as Proyecto,
                    p.financiamiento as Financiamiento,
                    t.codigo as Transaccion,
                    t.fecha_evento as Fecha,
                    t.unidad as Unidad,
                    t.monto as Monto_Venta,
                    t.comision_empresa_sin_itbis as Comision_Constructora,
                    t.itbis_comision_empresa as ITBIS_Constructora,
                    e.nombre || ' ' || e.apellido as Vendedor,
                    t.estado as Estado
                FROM transacciones t
                LEFT JOIN proyectos p ON t.proyecto_id = p.id
                LEFT JOIN contrapartes cp ON p.contraparte_id = cp.id
                LEFT JOIN entidades e ON t.entidad_id = e.id
                WHERE t.fecha_evento >= :fecha_min
                ORDER BY Constructora, p.nombre, t.fecha_evento DESC
            """

            query_detalle_proyectos = """
                SELECT 
                    p.nombre as Proyecto,
                    p.tipo_inmueble as Tipo_Inmueble,
                    p.financiamiento as Financiamiento,
                    cp.nombre as Constructora,
                    t.codigo as Transaccion,
                    t.fecha_evento as Fecha,
                    t.unidad as Unidad,
                    t.monto as Monto_Venta,
                    c.nombre || ' ' || c.apellido as Cliente,
                    t.estado as Estado
                FROM transacciones t
                JOIN proyectos p ON t.proyecto_id = p.id
                LEFT JOIN contrapartes cp ON p.contraparte_id = cp.id
                LEFT JOIN clientes c ON t.cliente_id = c.id
                WHERE t.fecha_evento >= :fecha_min
                ORDER BY p.nombre, t.fecha_evento DESC
            """

            df_vendedores = pd.read_sql_query(query_detalle_vendedores, conn, params={"fecha_min": fecha_min})
            df_constructoras = pd.read_sql_query(query_detalle_constructoras, conn, params={"fecha_min": fecha_min})
            df_proyectos = pd.read_sql_query(query_detalle_proyectos, conn, params={"fecha_min": fecha_min})

            for old_file in excel_dir.glob("Reporte_Detallado_Ventas_*.xlsx"):
                try: old_file.unlink()
                except: pass
            
            excel_path = excel_dir / f'Reporte_Detallado_Ventas_{datetime.now().strftime("%Y%m%d")}.xlsx'
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df_vendedores.to_excel(writer, sheet_name='Detalle Vendedores', index=False)
                df_constructoras.to_excel(writer, sheet_name='Detalle Constructoras', index=False)
                df_proyectos.to_excel(writer, sheet_name='Detalle Proyectos', index=False)

        return jsonify({"success": True, "message": f"Exportacion completada exitosamente.\nArchivos detallados guardados en data/exports/excel/"})
    
    except Exception as e:
        return jsonify({"success": False, "message": f"Error en la exportacion: {str(e)}"})


@exportaciones_api_bp.route("/generar-agente", methods=["POST"])
@requiere_rol("Admin")
def generar_agente():
    try:
        try:
            import pandas as pd
        except ImportError:
            return jsonify({"success": False, "message": "Error: pandas no esta instalado."})

        project_dir = Path(current_app.root_path).parent.parent
        agente_dir = project_dir / 'dlab-data' / 'exports' / 'Agente'
        os.makedirs(agente_dir, exist_ok=True)
        
        fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        q1 = """
        SELECT 
            t.id AS transaccion_id, t.fecha_evento AS fecha, t.estado AS estado_venta, t.monto AS precio_venta, (t.monto * COALESCE(t.pct_comision,0)) AS comision_total,
            p.nombre AS proyecto, p.provincia AS ciudad, p.tipo_inmueble, p.etapa,
            'Constructora_' || p.contraparte_id AS constructora_anonimizada,
            'Asesor_' || t.entidad_id AS asesor_anonimizado,
            'Cliente_' || t.cliente_id AS cliente_anonimizado
        FROM transacciones t
        LEFT JOIN proyectos p ON t.proyecto_id = p.id
        """
        df_ventas = pd.DataFrame([dict(r) for r in db.session.execute(text(q1)).mappings().all()])
        df_ventas.to_csv(agente_dir / f"IA_1_Ventas_Cierres_{fecha_str}.csv", index=False, encoding='utf-8-sig')

        q2 = """
        SELECT 
            cb.transaccion_id, cb.concepto, cb.fecha_vencimiento, cb.monto_total AS cuota_monto, cb.estado_aging_id AS estado_cuota,
            COALESCE((SELECT SUM(pg.monto) FROM pagos pg WHERE pg.cobro_id = cb.id), 0) AS monto_pagado,
            'Cliente_' || (SELECT cliente_id FROM transacciones WHERE id = cb.transaccion_id) AS cliente_anonimizado
        FROM cobros cb
        """
        df_cobros = pd.DataFrame([dict(r) for r in db.session.execute(text(q2)).mappings().all()])
        df_cobros.to_csv(agente_dir / f"IA_2_Cobros_Ingresos_{fecha_str}.csv", index=False, encoding='utf-8-sig')

        q3 = """
        SELECT 
            c.fecha_solicitud AS fecha, c.concepto, c.monto_total AS monto, c.estado AS estado_pago,
            'Proveedor_' || c.proveedor_id AS proveedor_anonimizado,
            COALESCE((SELECT SUM(pg.monto_pagado) FROM compras_pagos pg WHERE pg.compra_id = c.id), 0) AS monto_abonado
        FROM compras c
        """
        try:
            df_compras = pd.DataFrame([dict(r) for r in db.session.execute(text(q3)).mappings().all()])
        except Exception:
            df_compras = pd.DataFrame(columns=["fecha", "concepto", "monto", "estado_pago", "proveedor_anonimizado", "monto_abonado"])
        df_compras.to_csv(agente_dir / f"IA_3_Compras_Gastos_{fecha_str}.csv", index=False, encoding='utf-8-sig')

        q4 = """
        SELECT 
            m.nombre AS nombre_campana, m.canal AS plataforma, m.monto_invertido AS presupuesto, m.leads_generados,
            CASE WHEN m.leads_generados > 0 THEN m.monto_invertido / m.leads_generados ELSE 0 END AS costo_por_lead,
            m.fecha_inicio, m.fecha_fin, m.activo AS estatus,
            'Proyecto_' || m.proyecto_id AS proyecto_asociado
        FROM campanas m
        """
        df_marketing = pd.DataFrame([dict(r) for r in db.session.execute(text(q4)).mappings().all()])
        df_marketing.to_csv(agente_dir / f"IA_4_Marketing_{fecha_str}.csv", index=False, encoding='utf-8-sig')

        q5 = """
        SELECT 
            t.id AS transaccion_id,
            t.comision_empresa_sin_itbis AS comision_bruta_empresa,
            t.retencion_isr,
            t.retencion_itbis,
            t.ganancia_empresa_sin_itbis AS comision_neta_empresa,
            t.comision_vendedor_bruta AS comision_vendedor,
            'Asesor_' || t.entidad_id AS asesor_anonimizado
        FROM transacciones t
        """
        df_comisiones = pd.DataFrame([dict(r) for r in db.session.execute(text(q5)).mappings().all()])
        df_comisiones.to_csv(agente_dir / f"IA_5_Comisiones_{fecha_str}.csv", index=False, encoding='utf-8-sig')

        filename_excel = "Diccionario_Identidades_SECRETO.xlsx"
        filepath_excel = agente_dir / filename_excel
        
        with pd.ExcelWriter(filepath_excel, engine='openpyxl') as writer:
            pd.DataFrame([dict(r) for r in db.session.execute(text("SELECT 'Cliente_' || id AS alias_ia, nombre || ' ' || COALESCE(apellido,'') AS nombre_real, telefono, email FROM clientes")).mappings().all()]).to_excel(writer, sheet_name='Clientes', index=False)
            pd.DataFrame([dict(r) for r in db.session.execute(text("SELECT 'Asesor_' || id AS alias_ia, nombre || ' ' || COALESCE(apellido,'') AS nombre_real, posicion AS rol, nivel FROM entidades")).mappings().all()]).to_excel(writer, sheet_name='Asesores', index=False)
            pd.DataFrame([dict(r) for r in db.session.execute(text("SELECT 'Constructora_' || id AS alias_ia, nombre AS nombre_real, rnc, contacto FROM contrapartes")).mappings().all()]).to_excel(writer, sheet_name='Constructoras', index=False)
            pd.DataFrame([dict(r) for r in db.session.execute(text("SELECT 'Proveedor_' || id AS alias_ia, razon_social AS nombre_real, ruc, telefono FROM proveedores")).mappings().all()]).to_excel(writer, sheet_name='Proveedores', index=False)
            pd.DataFrame([dict(r) for r in db.session.execute(text("SELECT 'Proyecto_' || id AS alias_ia, nombre AS nombre_real, provincia AS ciudad FROM proyectos")).mappings().all()]).to_excel(writer, sheet_name='Proyectos', index=False)

        try:
            import msoffcrypto
            with open(filepath_excel, 'rb') as f:
                encrypted = msoffcrypto.OfficeFile(f)
                encrypted.load_key('DLAB-SEC-2026')
                with open(filepath_excel.with_suffix('.tmp'), 'wb') as tmp:
                    encrypted.encrypt(tmp)
            import shutil
            shutil.move(str(filepath_excel.with_suffix('.tmp')), str(filepath_excel))
        except ImportError:
            logger.warning("msoffcrypto no instalado. Diccionario sin cifrar. Instala con: pip install msoffcrypto-tool")
        except Exception as e:
            logger.warning(f"No se pudo cifrar diccionario: {e}")
        
        return jsonify({
            "success": True, 
            "message": "Exportacion Integral completada. Se generaron 5 datasets analiticos para la IA y 1 Diccionario Secreto."
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@exportaciones_api_bp.route("/generar-historico-operativo", methods=["POST"])
@requiere_rol("Admin")
def generar_historico_operativo():
    try:
        try:
            import pandas as pd
        except ImportError:
            return jsonify({"success": False, "message": "Error: pandas no esta instalado. Ejecuta: pip install pandas openpyxl"})
        
        try:
            import openpyxl
        except ImportError:
            return jsonify({"success": False, "message": "Error: openpyxl no esta instalado. Ejecuta: pip install openpyxl"})

        project_dir = Path(current_app.root_path).parent.parent
        excel_dir = project_dir / 'dlab-data' / 'exports' / 'excel'
        excel_dir.mkdir(parents=True, exist_ok=True)
        
        with db.engine.connect() as conn:
            query_compras = """
                SELECT 
                    c.id as Compra_ID, pv.razon_social as Proveedor, c.concepto as Concepto,
                    c.monto_total as Monto_Total, c.fecha_solicitud as Fecha_Solicitud, c.estado as Estado
                FROM compras c
                LEFT JOIN proveedores pv ON c.proveedor_id = pv.id
                ORDER BY c.fecha_solicitud DESC
            """
            
            query_pagos = """
                SELECT 
                    p.id as Pago_ID, pv.razon_social as Proveedor, c.concepto as Compra_Concepto,
                    p.monto_pagado as Monto_Pagado, p.fecha_pago as Fecha_Pago, p.referencia as Referencia
                FROM compras_pagos p
                JOIN compras c ON p.compra_id = c.id
                LEFT JOIN proveedores pv ON c.proveedor_id = pv.id
                ORDER BY p.fecha_pago DESC
            """
            
            query_cierres = """
                SELECT 
                    t.codigo as Transaccion, t.fecha_evento as Fecha_Cierre, t.estado as Estado_Transaccion,
                    e.nombre || ' ' || e.apellido as Asesor, cl.nombre || ' ' || cl.apellido as Cliente,
                    p.nombre as Proyecto, t.unidad as Unidad, t.monto as Monto_Venta,
                    t.pct_comision as Porcentaje_Comision, t.comision_empresa_sin_itbis as Comision_Empresa,
                    t.itbis_comision_empresa as ITBIS_Empresa, t.comision_vendedor_bruta as Comision_Bruta,
                    t.tipo_persona_vendedor as Tipo_Persona, t.aplica_itbis_vendedor as Aplica_ITBIS,
                    t.pct_isr as Pct_ISR, t.retencion_isr as ISR_Retenido,
                    t.itbis_vendedor as ITBIS_Vendedor, t.pct_itbis_retenido as Pct_ITBIS_Retenido,
                    t.retencion_itbis as ITBIS_Retenido, t.total_retenciones as Total_Retenciones,
                    t.neto_pagado_vendedor as Neto_Pagado, t.costo_total_vendedor as Costo_Total_Vendedor,
                    t.ganancia_empresa_sin_itbis as Ganancia_Empresa, t.margen_empresa_neto as Margen_Empresa
                FROM transacciones t
                LEFT JOIN entidades e ON t.entidad_id = e.id
                LEFT JOIN clientes cl ON t.cliente_id = cl.id
                LEFT JOIN proyectos p ON t.proyecto_id = p.id
                WHERE t.estado NOT IN ('Caida', 'Perdida')
                ORDER BY t.fecha_evento DESC
            """
            
            query_comisiones_pagos = """
                SELECT 
                    cp.id as Pago_Comision_ID, e.nombre || ' ' || e.apellido as Asesor,
                    t.codigo as Transaccion, cp.monto as Monto_Pagado,
                    cp.fecha_generacion as Fecha_Generacion, cp.fecha_pago as Fecha_Pago,
                    cp.estado as Estado_Pago
                FROM comisiones_pagos cp
                JOIN entidades e ON cp.entidad_id = e.id
                JOIN transacciones t ON cp.transaccion_id = t.id
                ORDER BY cp.fecha_generacion DESC
            """

            query_entidades = """
                SELECT
                    e.id, e.codigo, e.nombre, e.apellido, e.cedula,
                    e.telefono, e.email, e.posicion, e.nivel,
                    e.fecha_nacimiento, e.fecha_ingreso,
                    sup.nombre || ' ' || sup.apellido as Supervisor,
                    e.activo, e.genero, e.tipo
                FROM entidades e
                LEFT JOIN entidades sup ON e.supervisor_id = sup.id
                ORDER BY e.nombre
            """

            query_clientes = """
                SELECT
                    cl.id, cl.nombre, cl.apellido, cl.cedula,
                    cl.telefono, cl.email, cl.genero,
                    cl.pais, cl.provincia, cl.municipio,
                    cl.fecha_captacion, cl.etapa_embudo, cl.activo,
                    pr.nombre as Proyecto_Interes,
                    e.nombre || ' ' || e.apellido as Vendedor_Captador
                FROM clientes cl
                LEFT JOIN proyectos pr ON cl.proyecto_interes_id = pr.id
                LEFT JOIN entidades e ON cl.vendedor_captador_id = e.id
                ORDER BY cl.nombre
            """

            query_proyectos = """
                SELECT
                    p.id, p.nombre, cp.nombre as Constructora,
                    p.etapa, p.tipo_inmueble,
                    p.provincia, p.municipio, p.sector,
                    p.fecha_entrega_estimada,
                    p.unidades_totales, p.precio_min, p.precio_max,
                    p.financiamiento, p.institucion_bancaria, p.activo
                FROM proyectos p
                LEFT JOIN contrapartes cp ON p.contraparte_id = cp.id
                ORDER BY p.nombre
            """

            query_contrapartes = """
                SELECT id, nombre, rnc, telefono, contacto, direccion, provincia, sector, municipio, activo
                FROM contrapartes ORDER BY nombre
            """

            query_proveedores = """
                SELECT id, razon_social, ruc, email, telefono, direccion, estado, fecha_registro
                FROM proveedores ORDER BY razon_social
            """

            df_compras          = pd.read_sql_query(query_compras, conn)
            df_pagos            = pd.read_sql_query(query_pagos, conn)
            df_cierres          = pd.read_sql_query(query_cierres, conn)
            df_comisiones_pagos = pd.read_sql_query(query_comisiones_pagos, conn)
            df_entidades        = pd.read_sql_query(query_entidades, conn)
            df_clientes         = pd.read_sql_query(query_clientes, conn)
            df_proyectos        = pd.read_sql_query(query_proyectos, conn)
            df_contrapartes     = pd.read_sql_query(query_contrapartes, conn)
            df_proveedores      = pd.read_sql_query(query_proveedores, conn)
            
            for old_file in excel_dir.glob("Historico_Operativo_*.xlsx"):
                try: old_file.unlink()
                except: pass
                
            excel_path = excel_dir / f'Historico_Operativo_{datetime.now().strftime("%Y%m%d")}.xlsx'
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df_compras.to_excel(writer, sheet_name='Compras', index=False)
                df_pagos.to_excel(writer, sheet_name='Pagos_Proveedores', index=False)
                df_cierres.to_excel(writer, sheet_name='Cierres', index=False)
                df_comisiones_pagos.to_excel(writer, sheet_name='Pagos_Comisiones', index=False)
                df_entidades.to_excel(writer, sheet_name='M_Entidades', index=False)
                df_clientes.to_excel(writer, sheet_name='M_Clientes', index=False)
                df_proyectos.to_excel(writer, sheet_name='M_Proyectos', index=False)
                df_contrapartes.to_excel(writer, sheet_name='M_Constructoras', index=False)
                df_proveedores.to_excel(writer, sheet_name='M_Proveedores', index=False)

        total_sheets = 9
        return jsonify({
            "success": True,
            "message": f"Historico Operativo generado exitosamente.\n{total_sheets} hojas incluidas: Compras, Pagos_Proveedores, Cierres, Pagos_Comisiones, M_Entidades, M_Clientes, M_Proyectos, M_Constructoras, M_Proveedores."
        })
    
    except Exception as e:
        return jsonify({"success": False, "message": f"Error en la exportacion: {str(e)}"})


@exportaciones_api_bp.route("/abrir-powerbi", methods=["POST"])
@requiere_rol("ADMIN", "GERENTE COMERCIAL", "GERENTE FINANCIERA")
def abrir_powerbi():
    import subprocess, sys

    try:
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parents[2]

        pbip_path = base_dir / "powerbi" / "DLAB_BI.pbip"
        pbix_path = base_dir / "powerbi" / "DLAB_BI.pbix"
        readme_path = base_dir / "powerbi" / "README_PowerBI.txt"

        try:
            tasklist = subprocess.check_output('tasklist', shell=True).decode('cp850', errors='ignore')
            if 'PBIDesktop.exe' in tasklist:
                return jsonify({
                    "success": True, 
                    "message": "Power BI ya se encuentra abierto o cargando.", 
                    "modo": "abierto"
                })
        except Exception:
            pass

        if pbip_path.exists():
            os.startfile(str(pbip_path))
            return jsonify({"success": True, "message": "Power BI (.pbip) abierto correctamente.", "modo": "pbip"})
        elif pbix_path.exists():
            os.startfile(str(pbix_path))
            return jsonify({"success": True, "message": "Power BI (.pbix) abierto correctamente.", "modo": "pbix"})
        elif readme_path.exists():
            os.startfile(str(readme_path))
            return jsonify({
                "success": True,
                "message": "El reporte Power BI no esta configurado aun. Se abrio la guia de instalacion.",
                "modo": "readme"
            })
        else:
            return jsonify({
                "success": False,
                "message": "No se encontro la carpeta 'powerbi/' junto al ejecutable."
            })

    except Exception as e:
        return jsonify({"success": False, "message": f"Error al abrir Power BI: {str(e)}"})
