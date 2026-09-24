"""
carga_archivos_api.py — Endpoints API securizados para ingesta masiva de CSV.

SEGURIDAD:
- El nombre del archivo DEBE coincidir con el patrón oficial: plantilla_{modulo}_bi_ia.csv
- La tabla destino se infiere ÚNICAMENTE del nombre del archivo (no de columnas), contra whitelist.
- Se validan columnas exactas contra la plantilla oficial antes de insertar.
- Limite de tamaño: 5 MB.
- Sin SQL dinámico de entrada de usuario: tabla_destino solo puede ser un valor de TABLA_MAP.
"""

from flask import Blueprint, jsonify, request, Response, current_app
from app.core.auth_middleware import requiere_rol
from werkzeug.utils import secure_filename

carga_archivos_api_bp = Blueprint("carga_archivos_api", __name__, url_prefix="/api/carga-archivos")

# ─── CONFIGURACIÓN CENTRAL DE PLANTILLAS ────────────────────────────────────
# Fuente de verdad: nombre de módulo → columnas EXACTAS de la plantilla CSV
# Estas columnas deben coincidir 1:1 con lo que genera descargar_plantilla()

PLANTILLAS_COLUMNAS = {
    "clientes": [
        "cedula", "nombre", "apellido", "genero", "fecha_nacimiento",
        "pais", "provincia", "municipio", "direccion", "estado_civil", "nacionalidad",
        "telefono", "email", "via_referida", "etapa_embudo", "fecha_captacion", "activo"
    ],
    "empleados": [
        "codigo", "cedula", "nombre", "apellido", "telefono", "email",
        "posicion", "nivel", "fecha_ingreso", "activo"
    ],
    "constructoras": [
        "nombre", "rnc", "contacto", "telefono", "email",
        "provincia", "direccion", "especialidad", "activo"
    ],
    "proveedores": [
        "razon_social", "ruc", "telefono", "email", "direccion",
        "descripcion", "estado"
    ],
    "proyectos": [
        "nombre", "contraparte_id", "tipo_inmueble", "etapa",
        "provincia", "municipio", "unidades_totales", "fecha_entrega_estimada",
        "financiamiento", "activo"
    ],
    "cobros": [
        "transaccion_id", "tipo", "concepto", "monto_total",
        "fecha_generado", "fecha_vencimiento"
    ],
    "cierres": [
        "codigo", "proyecto_id", "entidad_id", "cliente_id",
        "monto", "monto_separacion", "monto_inicial",
        "num_cuotas", "financiamiento", "pct_comision",
        "fecha_evento", "sla_dias_meta", "estado"
    ],
    "marketing": [
        "nombre", "canal", "fecha_inicio", "monto_invertido", "activo"
    ],
    "compras": [
        "concepto", "monto_total", "fecha_solicitud", "enlace_dropbox", "estado", "proveedor_id"
    ]
}

# Whitelist estricta: módulo → tabla real en la DB
TABLA_MAP = {
    "clientes":  "clientes",
    "empleados": "entidades",
    "constructoras": "contrapartes",
    "proveedores": "proveedores",
    "proyectos": "proyectos",
    "cobros":    "cobros",
    "cierres":   "transacciones",
    "marketing": "campanas",
    "compras":   "compras"
}

# Nombre de archivo oficial generado al descargar: plantilla_{modulo}_bi_ia.csv
NOMBRE_PATRON = "plantilla_{modulo}_bi_ia.csv"

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _modulo_desde_filename(filename: str):
    """
    Extrae el módulo del nombre de archivo si coincide exactamente con el patrón oficial.
    Retorna None si no coincide.
    """
    for modulo in PLANTILLAS_COLUMNAS:
        expected = NOMBRE_PATRON.format(modulo=modulo)
        if filename == expected:
            return modulo
    return None


# ─── ENDPOINT: DESCARGAR PLANTILLA ──────────────────────────────────────────

@carga_archivos_api_bp.route("/plantilla/<modulo>", methods=["GET"])
@requiere_rol("Admin")
def descargar_plantilla(modulo):
    modulo_clean = modulo.lower().strip()
    if modulo_clean not in PLANTILLAS_COLUMNAS:
        return jsonify({"success": False, "error": f"Módulo '{modulo}' no reconocido."}), 404

    columnas = PLANTILLAS_COLUMNAS[modulo_clean]
    # Cabecera + una fila de ejemplo vacía para guía
    ejemplo = ",".join(["" for _ in columnas])
    csv_content = ",".join(columnas) + "\n" + ejemplo + "\n"

    filename = NOMBRE_PATRON.format(modulo=modulo_clean)
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── ENDPOINT: PROCESAR CSV ──────────────────────────────────────────────────

import pandas as pd
from app.extensions import db
from sqlalchemy import text

@carga_archivos_api_bp.route("/procesar", methods=["POST"])
@requiere_rol("Admin")
def procesar_csv():
    # ── 1. Verificar archivo presente
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No se seleccionó ningún archivo."}), 400

    file = request.files["file"]
    filename_raw = file.filename or ""
    safe_filename = secure_filename(filename_raw)

    # ── 2. Validar extensión
    if not safe_filename.lower().endswith(".csv"):
        return jsonify({"success": False, "error": "Solo se permiten archivos con extensión .csv"}), 400

    # ── 3. Validar tamaño (5 MB max)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({"success": False, "error": f"Archivo demasiado grande. Máximo permitido: 5 MB."}), 400

    # ── 4. VALIDACIÓN DE NOMBRE — Solo se aceptan plantillas oficiales
    modulo = _modulo_desde_filename(safe_filename)
    if modulo is None:
        nombres_validos = ", ".join([NOMBRE_PATRON.format(modulo=m) for m in PLANTILLAS_COLUMNAS])
        return jsonify({
            "success": False,
            "error": (
                f"Nombre de archivo no reconocido: '{safe_filename}'. "
                f"Solo se aceptan plantillas oficiales descargadas desde este sistema. "
                f"Nombres válidos: {nombres_validos}"
            )
        }), 400

    # ── 5. Resolver tabla destino desde whitelist (sin SQL injection posible)
    tabla_destino = TABLA_MAP[modulo]
    columnas_esperadas = PLANTILLAS_COLUMNAS[modulo]

    try:
        df = pd.read_csv(file)

        # ── 6. Verificar que no esté vacío
        if df.empty:
            return jsonify({"success": False, "error": "El archivo CSV está vacío."}), 400

        # ── 7. Validar columnas EXACTAS contra la plantilla oficial
        columnas_csv = list(df.columns)
        columnas_faltantes = [c for c in columnas_esperadas if c not in columnas_csv]
        columnas_extra = [c for c in columnas_csv if c not in columnas_esperadas]

        errores_columnas = []
        if columnas_faltantes:
            errores_columnas.append(f"Columnas faltantes: {', '.join(columnas_faltantes)}")
        if columnas_extra:
            errores_columnas.append(f"Columnas no reconocidas (elimínalas): {', '.join(columnas_extra)}")

        if errores_columnas:
            return jsonify({
                "success": False,
                "error": (
                    f"La plantilla '{safe_filename}' no coincide con la estructura oficial del módulo '{modulo}'. "
                    + " | ".join(errores_columnas)
                )
            }), 400

        # ── 8. Obtener columnas reales de la BD para filtrar
        from sqlalchemy import inspect
        from sqlalchemy.exc import IntegrityError
        import numpy as np

        inspector = inspect(db.engine)
        db_cols = [col['name'] for col in inspector.get_columns(tabla_destino)]

        # ── 9. Valores por defecto según módulo
        if tabla_destino == "clientes":
            if "etapa_embudo" not in df.columns: df["etapa_embudo"] = "Nuevo"
            if "activo" not in df.columns: df["activo"] = 1
            from datetime import date
            if "fecha_captacion" not in df.columns:
                df["fecha_captacion"] = date.today().strftime('%Y-%m-%d')

        elif tabla_destino == "entidades":
            if "activo" not in df.columns: df["activo"] = 1
            if "atributos_extra" not in df.columns: df["atributos_extra"] = "{}"
            if "fecha_ingreso" not in df.columns:
                from datetime import date
                df["fecha_ingreso"] = date.today().strftime('%Y-%m-%d')

        elif tabla_destino == "proyectos":
            if "activo" not in df.columns: df["activo"] = 1
            if "amenidades" not in df.columns: df["amenidades"] = "[]"

        elif tabla_destino == "transacciones":
            if "estado" not in df.columns: df["estado"] = "en_proceso"
            if "atributos_extra" not in df.columns: df["atributos_extra"] = "{}"
            if "financiamiento" not in df.columns: df["financiamiento"] = 0
            if "kyc_completo" not in df.columns: df["kyc_completo"] = 0
            if "sla_dias_meta" not in df.columns: df["sla_dias_meta"] = 10
            if "estado_plan_pagos" not in df.columns: df["estado_plan_pagos"] = "al_dia"
            if "canal" not in df.columns: df["canal"] = "interno"
            from datetime import date
            if "fecha_evento" not in df.columns:
                df["fecha_evento"] = date.today().strftime('%Y-%m-%d')

        elif tabla_destino == "campanas":
            if "activo" not in df.columns: df["activo"] = 1
            from datetime import date
            if "fecha_inicio" not in df.columns:
                df["fecha_inicio"] = date.today().strftime('%Y-%m-%d')
                
        elif tabla_destino == "contrapartes":
            if "activo" not in df.columns: df["activo"] = 1
            if "atributos_extra" not in df.columns: df["atributos_extra"] = "{}"
            
        elif tabla_destino == "proveedores":
            if "estado" not in df.columns: df["estado"] = "activo"
            if "atributos_extra" not in df.columns: df["atributos_extra"] = "{}"
        
        elif tabla_destino == "compras":
            if "estado" not in df.columns: df["estado"] = "pendiente"
            if "aprobado_ceo" not in df.columns: df["aprobado_ceo"] = 0
            if "f03_completado" not in df.columns: df["f03_completado"] = 0

        # ── 10. Prevención de duplicados
        unique_col_map = {
            "clientes": "cedula",
            "entidades": "cedula",
            "contrapartes": "nombre",
            "proveedores": "razon_social",
            "proyectos": "nombre",
            "campanas": "nombre",
            "transacciones": "codigo",
        }
        unique_col = unique_col_map.get(tabla_destino)
        rechazados = 0
        detalles_rechazos = {}

        if unique_col and unique_col in df.columns:
            try:
                existentes = [
                    row[0] for row in
                    db.session.execute(text(f"SELECT {unique_col} FROM {tabla_destino}")).fetchall()
                ]
                duplicados = df[df[unique_col].isin(existentes)]
                if not duplicados.empty:
                    rechazados += len(duplicados)
                    detalles_rechazos["Duplicado (ya existe en BD)"] = len(duplicados)
                df = df[~df[unique_col].isin(existentes)]
            except Exception:
                pass

        # ── 11. Filtrar solo columnas presentes en la BD
        cols_to_keep = [c for c in df.columns if c in db_cols]
        df = df[cols_to_keep]

        # ── 12. Reemplazar NaN con None
        df = df.replace({np.nan: None})

        # ── 13. Inserción fila por fila con manejo de errores
        insertados = 0
        if not df.empty and cols_to_keep:
            columns_str = ", ".join(cols_to_keep)
            placeholders = ", ".join([f":{c}" for c in cols_to_keep])
            insert_query = text(f"INSERT INTO {tabla_destino} ({columns_str}) VALUES ({placeholders})")

            for _, row in df.iterrows():
                try:
                    db.session.execute(insert_query, row.to_dict())
                    insertados += 1
                except IntegrityError as e:
                    db.session.rollback()
                    rechazados += 1
                    err = str(e.orig)
                    if "NOT NULL constraint failed" in err:
                        reason = f"Falta campo obligatorio: {err.split(':')[-1].strip()}"
                    elif "UNIQUE constraint failed" in err:
                        reason = "Duplicado (restricción única)"
                    else:
                        reason = f"Error de integridad: {err[:80]}"
                    detalles_rechazos[reason] = detalles_rechazos.get(reason, 0) + 1
                except Exception as e:
                    db.session.rollback()
                    rechazados += 1
                    reason = f"Error de formato: {str(e)[:60]}"
                    detalles_rechazos[reason] = detalles_rechazos.get(reason, 0) + 1

            db.session.commit()

        # ── 14. Log de auditoría
        import os
        from datetime import datetime
        log_raw = ""
        if rechazados > 0:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_lines = [
                f"--- REPORTE DE CARGA: {safe_filename} | {timestamp} ---",
                f"Módulo: {modulo} → {tabla_destino} | Insertadas: {insertados} | Rechazadas: {rechazados}"
            ]
            for motivo, count in detalles_rechazos.items():
                log_lines.append(f"  - {count} fila(s): {motivo}")
            log_lines.append("-" * 50)
            log_raw = "\n".join(log_lines)

            try:
                log_path = os.path.join(os.getcwd(), "logs", "carga_masiva_errores.txt")
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_raw + "\n")
            except Exception:
                pass

        return jsonify({
            "success": True,
            "filename": safe_filename,
            "modulo": modulo,
            "tabla_destino": tabla_destino,
            "columnas_validadas": len(cols_to_keep),
            "filas_recibidas": insertados + rechazados,
            "insertados": insertados,
            "rechazados": rechazados,
            "detalles_rechazos": detalles_rechazos,
            "log_raw": log_raw,
            "message": f"✅ Archivo '{safe_filename}' procesado. {insertados} registros guardados en '{tabla_destino}'."
        })

    except pd.errors.EmptyDataError:
        return jsonify({"success": False, "error": "El archivo CSV está vacío o no contiene columnas."}), 400
    except Exception as e:
        current_app.logger.error("Error procesando archivo CSV: %s", repr(e))
        return jsonify({"success": False, "error": "Error procesando el archivo. Verifique el formato y el contenido."}), 500
