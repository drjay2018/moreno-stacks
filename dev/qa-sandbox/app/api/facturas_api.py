import os
from flask import Blueprint, jsonify, request, send_file, current_app
from app.core.auth_middleware import requiere_rol
from werkzeug.utils import secure_filename
from sqlalchemy import text
from app.extensions import db
from app.core.auditoria import registrar_auditoria
from app.core.utils import dt_args
from pathlib import Path

facturas_api_bp = Blueprint("facturas_api", __name__, url_prefix="/api/facturas")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_FOLDER = BASE_DIR / "dlab-data" / "uploads" / "facturas"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@facturas_api_bp.route("/", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_facturas():
    search_cols = ['cf.numero_factura', 'c.concepto', 'p.razon_social']
    sort_cols = ['cf.id', 'c.concepto', 'p.razon_social', 'cf.numero_factura', 'cf.monto_factura', 'cf.fecha_subida', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)

    compra_id_filter = request.args.get("compra_id", type=int)
    if compra_id_filter:
        if "WHERE" in where_clause:
            where_clause += " AND cf.compra_id = :compra_id_filter"
        else:
            where_clause = "WHERE cf.compra_id = :compra_id_filter"
        params["compra_id_filter"] = compra_id_filter

    if not order_clause:
        order_clause = "ORDER BY cf.id DESC"

    base_query = """
        FROM compras_facturas cf
        JOIN compras c ON cf.compra_id = c.id
        JOIN proveedores p ON cf.proveedor_id = p.id
    """
    
    total_filtered = db.session.execute(text(f"SELECT COUNT(cf.id) {base_query} {where_clause}"), params).scalar() or 0
    total_records = db.session.execute(text(f"SELECT COUNT(cf.id) {base_query}")).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""
            SELECT cf.id, cf.compra_id, c.concepto as compra_concepto, 
                   cf.proveedor_id, p.razon_social as proveedor_nombre,
                   cf.numero_factura, cf.monto_factura, cf.ruta_archivo_pdf, cf.fecha_subida
            {base_query}
            {where_clause}
            {order_clause} LIMIT :limit OFFSET :offset
        """),
        params
    ).mappings().all()

    items = [dict(r) for r in rows]

    if is_dt:
        return jsonify({"draw": draw, "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items})
    return jsonify({"success": True, "items": items, "total": total_filtered})

@facturas_api_bp.route("/upload", methods=["POST"])
@requiere_rol("Admin")
def subir_factura():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No se encontró el archivo."}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Archivo vacío."}), 400
        
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "error": "Solo se permiten archivos PDF."}), 400

    compra_id = request.form.get("compra_id")
    numero_factura = request.form.get("numero_factura", "").strip()
    monto_factura = request.form.get("monto_factura", 0.0)

    if not compra_id:
        return jsonify({"success": False, "error": "Debe asociar la factura a una compra."}), 400

    # Obtener proveedor de la compra
    compra = db.session.execute(text("SELECT proveedor_id FROM compras WHERE id = :id"), {"id": compra_id}).fetchone()
    if not compra or not compra[0]:
        return jsonify({"success": False, "error": "Compra no válida o sin proveedor asignado."}), 404

    proveedor_id = compra[0]
    filename = secure_filename(f"compra_{compra_id}_{file.filename}")
    filepath = UPLOAD_FOLDER / filename
    
    try:
        file.save(filepath)
        db.session.execute(
            text("""
                INSERT INTO compras_facturas (compra_id, proveedor_id, numero_factura, monto_factura, ruta_archivo_pdf)
                VALUES (:cid, :pid, :num, :monto, :ruta)
            """),
            {"cid": compra_id, "pid": proveedor_id, "num": numero_factura, "monto": float(monto_factura), "ruta": filename}
        )
        db.session.commit()
        registrar_auditoria(1, 'admin', 'subir_factura', 'COMPRAS', f'Factura {filename} subida para compra {compra_id}')
        return jsonify({"success": True, "message": "Factura subida correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en facturas_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

@facturas_api_bp.route("/view/<int:fid>", methods=["GET"])
@requiere_rol("Admin", "Gerente Financiera", "Gerente General", "CEO")
def ver_factura(fid):
    # NOTA SEGURIDAD: compras_facturas / compras no registran quién la subió ni
    # tienen un campo de "propietario" claro (solo compra_id/proveedor_id), por lo
    # que aquí solo se restringe por rol. Falta pendiente: validar pertenencia
    # (p. ej. asesor/proyecto asociado a la compra) si el modelo de datos lo permite
    # en el futuro.
    factura = db.session.execute(text("SELECT ruta_archivo_pdf FROM compras_facturas WHERE id = :id"), {"id": fid}).fetchone()
    if not factura:
        return "Factura no encontrada", 404
        
    filepath = UPLOAD_FOLDER / factura[0]
    if not os.path.exists(filepath):
        return "Archivo físico no encontrado", 404

    return send_file(filepath, mimetype='application/pdf')

@facturas_api_bp.route("/<int:fid>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_factura(fid):
    factura = db.session.execute(text("SELECT ruta_archivo_pdf FROM compras_facturas WHERE id = :id"), {"id": fid}).fetchone()
    if not factura:
        return jsonify({"success": False, "error": "Factura no encontrada."}), 404

    try:
        db.session.execute(text("DELETE FROM compras_facturas WHERE id = :id"), {"id": fid})
        db.session.commit()
        filepath = UPLOAD_FOLDER / factura[0]
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
        registrar_auditoria(1, 'admin', 'borrar_factura', 'COMPRAS', f'Factura {fid} eliminada')
        return jsonify({"success": True, "message": "Factura eliminada correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en facturas_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500
