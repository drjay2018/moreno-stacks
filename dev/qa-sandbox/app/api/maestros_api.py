"""
maestros_api.py — Endpoints API para gestión de los 4 catálogos de Datos Maestros y LeadPreferencia.
"""

from datetime import datetime

from app.core.auth_middleware import requiere_rol
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import text
from app.extensions import db
from app.core.auditoria import registrar_auditoria
from app.core.utils import dt_args
import logging

logger = logging.getLogger(__name__)

maestros_api_bp = Blueprint("maestros_api", __name__, url_prefix="/api/maestros")


def _proyectos_tiene_es_exclusivo():
    columnas = db.session.execute(text("PRAGMA table_info(proyectos)")).mappings().all()
    return any(c["name"] == "es_exclusivo" for c in columnas)


def _validar_fecha(valor, campo):
    if not valor:
        return None
    try:
        datetime.strptime(str(valor), "%Y-%m-%d")
    except ValueError:
        return f"El campo {campo} debe ser una fecha válida en formato YYYY-MM-DD."
    return None


@maestros_api_bp.route("/catalogos-comisiones", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def catalogos_comisiones():
    niveles = [dict(r) for r in db.session.execute(text("SELECT id, nombre FROM cat_niveles ORDER BY id")).mappings().all()]
    captadores = [dict(r) for r in db.session.execute(text("SELECT id, nombre FROM cat_captadores ORDER BY id")).mappings().all()]
    gastos_pub = [dict(r) for r in db.session.execute(text("SELECT id, nombre FROM cat_gastos_pub ORDER BY id")).mappings().all()]
    reglas = [dict(r) for r in db.session.execute(text("SELECT nivel_id, captador_id, gastos_pub_id FROM config_matriz_comisiones")).mappings().all()]
    return jsonify({
        "success": True,
        "niveles": niveles,
        "captadores": captadores,
        "gastos_pub": gastos_pub,
        "reglas": reglas
    })




# --- CLIENTES ---
# NOTA: el PUT y el DELETE de clientes en este mismo fichero exigen rol Admin
# (ver actualizar_cliente/borrar_cliente); se replica aquí el mismo criterio
# para mantener coherencia en todo el CRUD de clientes.
@maestros_api_bp.route("/clientes", methods=["GET"])
@requiere_rol("Admin")
def listar_clientes():
    search_cols = ['nombre', 'apellido', 'cedula', 'telefono', 'email']
    sort_cols = ['nombre', 'cedula', 'telefono', 'email', 'provincia', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    if not order_clause:
        order_clause = "ORDER BY id DESC"
        
    total_filtered = db.session.execute(text(f"SELECT COUNT(id) FROM clientes {where_clause}"), params).scalar() or 0
    total_records = db.session.execute(text("SELECT COUNT(id) FROM clientes WHERE activo = 1")).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"SELECT id, nombre, apellido, cedula, telefono, email, pais, provincia, municipio, vendedor_captador_id as captador_id FROM clientes {where_clause} {order_clause} LIMIT :limit OFFSET :offset"),
        params
    ).mappings().all()

    items = [dict(r) for r in rows]

    if is_dt:
        return jsonify({"draw": draw, "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items})
    return jsonify({"success": True, "items": items, "total": total_filtered})


@maestros_api_bp.route("/clientes-completo", methods=["POST"])
@requiere_rol("Admin")
def crear_cliente_completo():
    data = request.get_json() or {}
    
    nombre = data.get("nombre", "").strip()
    apellido = data.get("apellido", "").strip()
    cedula = data.get("cedula", "").strip().replace("-", "").replace(" ", "")
    genero = data.get("genero")
    fecha_nacimiento = data.get("fecha_nacimiento") or None
    estado_civil = data.get("estado_civil")
    
    if fecha_nacimiento:
        from datetime import datetime, date
        try:
            fn = datetime.strptime(fecha_nacimiento, '%Y-%m-%d').date()
            age = (date.today() - fn).days / 365.2425
            if age < 18:
                return jsonify({"success": False, "error": "El cliente debe ser mayor de 18 años."}), 400
        except ValueError:
            pass

    
    nacionalidad = data.get("nacionalidad", "Dominicana")
    pais = data.get("pais", "República Dominicana")
    provincia = data.get("provincia")
    municipio = data.get("municipio")
    direccion = data.get("direccion")

    telefono = data.get("telefono")
    telefono_residencial = data.get("telefono_residencial")
    email = data.get("email")
    via_referida = data.get("via_referida")
    # IMPORTANTE: normalizar "" -> None en las FK opcionales. Los <select>
    # del wizard mandan "" (no null) cuando no hay opcion elegida (p. ej.
    # instalaciones nuevas sin empleados/proyectos aun creados). SQLite con
    # PRAGMA foreign_keys=ON rechaza "" como valor de una FK con
    # "FOREIGN KEY constraint failed", que el except IntegrityError generico
    # de abajo reportaba enganosamente como "Ya existe un registro con este
    # identificador unico" — bloqueando la creacion de CUALQUIER cliente en
    # el caso mas comun (sin vendedor/campana/referido asignado todavia).
    campana_id = data.get("campana_id") or None
    vendedor_captador_id = data.get("vendedor_captador_id") or None
    referido_por_cliente_id = data.get("referido_por_cliente_id") or None
    fecha_captacion = data.get("fecha_captacion") or None
    etapa_embudo = data.get("etapa_embudo", "Nuevo")
    proyecto_interes_id = data.get("proyecto_interes_id") or None
    presupuesto_rango = data.get("presupuesto_rango")

    import re
    if not nombre or not apellido:
        return jsonify({"success": False, "error": "Nombre y apellido son requeridos."}), 400
    if not re.match(r"^\d{11}$", cedula):
        return jsonify({"success": False, "error": "Cédula inválida. Debe tener 11 dígitos."}), 400

    from sqlalchemy.exc import IntegrityError
    try:
        existente = db.session.execute(text("SELECT id FROM clientes WHERE cedula = :c"), {"c": cedula}).scalar()
        if existente:
            return jsonify({"success": False, "error": f"La cédula {cedula} ya está registrada."}), 400

        result = db.session.execute(
            text("""
                INSERT INTO clientes (
                    nombre, apellido, cedula, genero, fecha_nacimiento, estado_civil,
                    nacionalidad, pais, provincia, municipio, direccion, sector,
                    telefono, telefono_residencial, email, via_referida, campana_id,
                    vendedor_captador_id, referido_por_cliente_id, fecha_captacion, etapa_embudo, activo,
                    proyecto_interes_id, presupuesto_rango, institucion_bancaria
                ) VALUES (
                    :nombre, :apellido, :cedula, :genero, :fecha_nacimiento, :estado_civil,
                    :nacionalidad, :pais, :provincia, :municipio, :direccion, :sector,
                    :telefono, :telefono_residencial, :email, :via_referida, :campana_id,
                    :vendedor_captador_id, :referido_por_cliente_id, COALESCE(:fecha_captacion, CURRENT_DATE), :etapa_embudo, 1,
                    :proyecto_interes_id, :presupuesto_rango, :institucion_bancaria
                )
            """),
            {
                "nombre": nombre, "apellido": apellido, "cedula": cedula, "genero": genero,
                "fecha_nacimiento": fecha_nacimiento, "estado_civil": estado_civil,
                "nacionalidad": nacionalidad, "pais": pais, "provincia": provincia, "municipio": municipio,
                "direccion": direccion, "sector": data.get("sector", ""),
                "telefono": telefono, "telefono_residencial": telefono_residencial, "email": email,
                "via_referida": via_referida, "campana_id": campana_id, "vendedor_captador_id": vendedor_captador_id,
                "referido_por_cliente_id": referido_por_cliente_id, "fecha_captacion": fecha_captacion, "etapa_embudo": etapa_embudo,
                "proyecto_interes_id": proyecto_interes_id, "presupuesto_rango": presupuesto_rango,
                "institucion_bancaria": data.get("institucion_bancaria", "")
            }
        )
        db.session.flush()

        cliente_id = db.session.execute(text("SELECT id FROM clientes WHERE cedula = :c"), {"c": cedula}).scalar()

        motivo_compra = data.get("motivo_compra")
        presupuesto_min = data.get("presupuesto_min")
        presupuesto_max = data.get("presupuesto_max")
        moneda_presupuesto = data.get("moneda_presupuesto", "US$")
        metodo_pago_preferido = data.get("metodo_pago_preferido")
        tamano_familia = data.get("tamano_familia")
        habitaciones_min = data.get("habitaciones_min")
        zonas_interes = data.get("zonas_interes", "[]")
        tiempo_mudanza = data.get("tiempo_mudanza")
        amenidades_must_have = data.get("amenidades_must_have", "[]")
        ocupacion = data.get("ocupacion")
        rango_ingreso_mensual = data.get("rango_ingreso_mensual")

        import json
        db.session.execute(
            text("""
                INSERT INTO lead_preferencias (
                    cliente_id, motivo_compra, presupuesto_min, presupuesto_max, moneda_presupuesto,
                    metodo_pago_preferido, tamano_familia, habitaciones_min, zonas_interes,
                    tiempo_mudanza, amenidades_must_have, ocupacion, rango_ingreso_mensual, fecha_actualizacion
                ) VALUES (
                    :c_id, :motivo, :p_min, :p_max, :moneda,
                    :pago, :fam, :hab, :zonas,
                    :tiempo, :amenidades, :ocu, :ingreso, CURRENT_TIMESTAMP
                )
            """),
            {
                "c_id": cliente_id, "motivo": motivo_compra, "p_min": presupuesto_min, "p_max": presupuesto_max, "moneda": moneda_presupuesto,
                "pago": metodo_pago_preferido, "fam": tamano_familia, "hab": habitaciones_min,
                "zonas": json.dumps(zonas_interes) if isinstance(zonas_interes, list) else zonas_interes,
                "tiempo": tiempo_mudanza,
                "amenidades": json.dumps(amenidades_must_have) if isinstance(amenidades_must_have, list) else amenidades_must_have,
                "ocu": ocupacion, "ingreso": rango_ingreso_mensual
            }
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"IntegrityError en {request.endpoint}: {e}")
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único (RNC, Cédula o Nombre)."}), 409
    registrar_auditoria(1, 'admin', 'crear_cliente', 'MAESTROS', f'Cliente {nombre} {apellido} registrado')
    return jsonify({"success": True, "message": f"Cliente {nombre} {apellido} y sus Preferencias de Compra registradas exitosamente."})

@maestros_api_bp.route("/clientes/<int:cliente_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_cliente(cliente_id):
    data = request.get_json() or {}
    
    nombre = data.get("nombre", "").strip()
    apellido = data.get("apellido", "").strip()
    telefono = data.get("telefono", "").strip()
    email = data.get("email", "").strip()
    cedula = data.get("cedula", "").strip().replace("-", "").replace(" ", "")
    fecha_nacimiento = data.get("fecha_nacimiento") or None
    genero = data.get("genero")
    estado_civil = data.get("estado_civil")
    nacionalidad = data.get("nacionalidad")
    pais = data.get("pais")
    provincia = data.get("provincia")
    municipio = data.get("municipio")
    direccion = data.get("direccion")
    telefono_residencial = data.get("telefono_residencial")
    vendedor_captador_id = data.get("vendedor_captador_id") or None  # "" -> None (ver nota en crear_cliente_completo)

    import re
    if not nombre or not apellido:
        return jsonify({"success": False, "error": "Nombre y apellido son requeridos."}), 400

    if cedula and not re.match(r"^\d{11}$", cedula):
        return jsonify({"success": False, "error": "Cédula inválida. Debe tener 11 dígitos."}), 400

    if cedula:
        existente = db.session.execute(text("SELECT id FROM clientes WHERE cedula = :c AND id != :id"), {"c": cedula, "id": cliente_id}).scalar()
        if existente:
            return jsonify({"success": False, "error": f"La cédula {cedula} ya está registrada."}), 400

    if fecha_nacimiento:
        from datetime import datetime, date
        try:
            fn = datetime.strptime(fecha_nacimiento, '%Y-%m-%d').date()
            age = (date.today() - fn).days / 365.2425
            if age < 18:
                return jsonify({"success": False, "error": "El cliente debe ser mayor de 18 años."}), 400
        except ValueError:
            pass

    db.session.execute(
        text("""
            UPDATE clientes 
            SET nombre = :nombre, apellido = :apellido, telefono = :telefono, email = :email,
                cedula = COALESCE(NULLIF(:cedula, ''), cedula),
                fecha_nacimiento = COALESCE(:fecha_nacimiento, fecha_nacimiento),
                genero = COALESCE(:genero, genero), estado_civil = COALESCE(:estado_civil, estado_civil),
                nacionalidad = COALESCE(:nacionalidad, nacionalidad), pais = COALESCE(:pais, pais),
                provincia = COALESCE(:provincia, provincia), municipio = COALESCE(:municipio, municipio),
                direccion = COALESCE(:direccion, direccion),
                telefono_residencial = COALESCE(:telefono_residencial, telefono_residencial),
                vendedor_captador_id = COALESCE(:vendedor_captador_id, vendedor_captador_id)
            WHERE id = :id
        """),
        {"nombre": nombre, "apellido": apellido, "telefono": telefono, "email": email,
         "cedula": cedula, "fecha_nacimiento": fecha_nacimiento,
         "genero": genero, "estado_civil": estado_civil,
         "nacionalidad": nacionalidad, "pais": pais,
         "provincia": provincia, "municipio": municipio, "direccion": direccion,
         "telefono_residencial": telefono_residencial,
         "vendedor_captador_id": vendedor_captador_id,
         "id": cliente_id}
    )
    db.session.commit()
    registrar_auditoria(1, 'admin', 'editar_cliente', 'MAESTROS', f'Cliente {cliente_id} actualizado')
    return jsonify({"success": True, "message": "Cliente actualizado correctamente."})

@maestros_api_bp.route("/clientes/<int:cliente_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_cliente(cliente_id):
    try:
        db.session.execute(text("UPDATE clientes SET activo = 0 WHERE id = :id"), {"id": cliente_id})
        db.session.commit()
        registrar_auditoria(1, 'admin', 'borrar_cliente', 'MAESTROS', f'Cliente {cliente_id} desactivado')
        return jsonify({"success": True, "message": "Cliente desactivado correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en maestros_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

# --- EMPLEADOS ---
@maestros_api_bp.route("/empleados", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_empleados():
    search_cols = ['nombre', 'apellido', 'cedula', 'posicion', 'nivel']
    sort_cols = ['codigo', 'nombre', 'cedula', 'posicion', 'nivel', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    if not order_clause:
        order_clause = "ORDER BY id DESC"
        
    total_filtered = db.session.execute(text(f"SELECT COUNT(id) FROM entidades {where_clause}"), params).scalar() or 0
    total_records = db.session.execute(text("SELECT COUNT(id) FROM entidades WHERE activo = 1")).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"""SELECT id, codigo, nombre, apellido, cedula, posicion, nivel, activo, atributos_extra,
                    tipo_persona, aplica_itbis, fecha_nacimiento, fecha_ingreso,
                    posee_vehiculo, vehiculo_datos, direccion
                  FROM entidades {where_clause} {order_clause} LIMIT :limit OFFSET :offset"""),
        params
    ).mappings().all()

    import json
    items = []
    for r in rows:
        d = dict(r)
        extra = {}
        if d.get("atributos_extra"):
            try:
                extra = json.loads(d["atributos_extra"])
            except:
                pass
        d["comision_base"] = extra.get("comision_base", "")
        d["provincia"] = extra.get("provincia", "")
        d["municipio"] = extra.get("municipio", "")
        d["sector"] = extra.get("sector", "")
        d["rol"] = d.get("nivel") # We mapped rol to nivel
        items.append(d)

    if is_dt:
        return jsonify({"draw": draw, "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items})
    return jsonify({"success": True, "items": items, "total": total_filtered})


@maestros_api_bp.route("/empleados", methods=["POST"])
@requiere_rol("Admin")
def crear_empleado():
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()
    apellido = data.get("apellido", "").strip()
    cedula = data.get("cedula", "").strip().replace("-", "")
    rol = data.get("rol", "Asesor Ventas")
    nivel = data.get("nivel", "Asesor interno - Inmobiliario")
    tipo_persona = data.get("tipo_persona", "Física")
    aplica_itbis = bool(data.get("aplica_itbis", True))
    estatus = int(data.get("estatus", 1))
    comision_base = data.get("comision_base", 0)
    if comision_base in [None, ""]:
        comision_base = 0
    try:
        comision_base = float(comision_base)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "comision_base debe ser un número."}), 400
    if comision_base < 0:
        return jsonify({"success": False, "error": "comision_base no puede ser negativa."}), 400

    fecha_nacimiento = data.get("fecha_nacimiento") or None
    fecha_ingreso = data.get("fecha_ingreso") or None
    error_fecha = _validar_fecha(fecha_nacimiento, "fecha_nacimiento") or _validar_fecha(fecha_ingreso, "fecha_ingreso")
    if error_fecha:
        return jsonify({"success": False, "error": error_fecha}), 400

    posee_vehiculo = int(data.get("posee_vehiculo", 0))
    vehiculo_datos = data.get("vehiculo_datos", "")
    direccion = data.get("direccion", "")

    import json
    atributos_extra = json.dumps({
        "comision_base": comision_base,
        "provincia": data.get("provincia", ""),
        "municipio": data.get("municipio", ""),
        "sector": data.get("sector", "")
    })

    import re
    if not nombre or not cedula:
        return jsonify({"success": False, "error": "Nombre y cédula son requeridos."}), 400
    if not re.match(r"^\d{11}$", cedula):
        return jsonify({"success": False, "error": "Cédula inválida. Debe tener 11 dígitos."}), 400

    from sqlalchemy.exc import IntegrityError
    try:
        existente = db.session.execute(text("SELECT id FROM entidades WHERE cedula = :c"), {"c": cedula}).scalar()
        if existente:
            return jsonify({"success": False, "error": f"La cédula {cedula} ya está registrada."}), 400

        codigo = f"EMP-{db.session.execute(text('SELECT COALESCE(MAX(id), 0) + 1 FROM entidades')).scalar():04d}"

        db.session.execute(
            text("""
                INSERT INTO entidades (codigo, nombre, apellido, cedula, posicion, nivel,
                    tipo, empresa, activo, atributos_extra, tipo_persona, aplica_itbis,
                    fecha_nacimiento, fecha_ingreso, posee_vehiculo, vehiculo_datos, direccion)
                VALUES (:cod, :nom, :ape, :ced, :pos, :niv,
                    'Interno', 'DLAB', :activo, :extra, :tp, :ai,
                    :fn, COALESCE(:fi, CURRENT_DATE), :pv, :vd, :d)
            """),
            {"cod": codigo, "nom": nombre, "ape": apellido, "ced": cedula, "pos": rol, "niv": nivel,
             "activo": estatus, "extra": atributos_extra,
             "tp": tipo_persona, "ai": int(aplica_itbis),
             "fn": fecha_nacimiento, "fi": fecha_ingreso, "pv": posee_vehiculo,
             "vd": vehiculo_datos, "d": direccion}
        )

        existe_captador = db.session.execute(text("SELECT id FROM cat_captadores WHERE nombre = :nom"), {"nom": nombre}).scalar()
        if not existe_captador:
            db.session.execute(text("INSERT INTO cat_captadores (nombre) VALUES (:nom)"), {"nom": nombre})

        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"IntegrityError en {request.endpoint}: {e}")
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único (RNC, Cédula o Nombre)."}), 409
    from app.core.auditoria import registrar_auditoria
    registrar_auditoria(1, 'admin', 'crear_empleado', 'MAESTROS', f'Empleado {nombre} registrado')
    return jsonify({"success": True, "message": f"Empleado {nombre} registrado exitosamente con código {codigo}."})

@maestros_api_bp.route("/empleados/<int:empleado_id>", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def get_empleado(empleado_id):
    row = db.session.execute(text("SELECT id, nombre, apellido FROM entidades WHERE id = :id"), {"id": empleado_id}).mappings().first()
    if row:
        return jsonify({"success": True, "item": dict(row)})
    return jsonify({"success": False, "error": "No encontrado"}), 404


@maestros_api_bp.route("/empleados/<int:empleado_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_empleado(empleado_id):
    data = request.get_json() or {}

    import json
    import re

    nombre = data.get("nombre", "").strip()
    if not nombre:
        return jsonify({"success": False, "error": "Nombre es requerido."}), 400

    updates = []
    params = {"id": empleado_id}

    if "apellido" in data:
        updates.append("apellido = :apellido")
        params["apellido"] = data.get("apellido", "")

    if "cedula" in data:
        cedula = str(data.get("cedula", "")).strip().replace("-", "")
        if cedula and not re.match(r"^\d{11}$", cedula):
            return jsonify({"success": False, "error": "Cédula inválida. Debe tener 11 dígitos."}), 400
        if cedula:
            existente = db.session.execute(
                text("SELECT id FROM entidades WHERE cedula = :c AND id != :id"),
                {"c": cedula, "id": empleado_id}
            ).scalar()
            if existente:
                return jsonify({"success": False, "error": f"La cédula {cedula} ya está registrada."}), 400
        updates.append("cedula = COALESCE(NULLIF(:cedula, ''), cedula)")
        params["cedula"] = cedula

    if "rol" in data or "posicion" in data:
        updates.append("posicion = :posicion")
        params["posicion"] = data.get("posicion") if "posicion" in data else data.get("rol")

    if "nivel" in data or "nivel_id" in data:
        updates.append("nivel = :nivel")
        params["nivel"] = data.get("nivel") if "nivel" in data else data.get("nivel_id")

    if "tipo_persona" in data:
        updates.append("tipo_persona = :tp")
        params["tp"] = data["tipo_persona"]

    if "aplica_itbis" in data:
        updates.append("aplica_itbis = :ai")
        params["ai"] = int(bool(data["aplica_itbis"]))

    if "fecha_nacimiento" in data:
        fecha_nacimiento = data.get("fecha_nacimiento") or None
        error_fecha = _validar_fecha(fecha_nacimiento, "fecha_nacimiento")
        if error_fecha:
            return jsonify({"success": False, "error": error_fecha}), 400
        updates.append("fecha_nacimiento = COALESCE(CAST(:fn AS TEXT), fecha_nacimiento)")
        params["fn"] = fecha_nacimiento

    if "fecha_ingreso" in data:
        fecha_ingreso = data.get("fecha_ingreso") or None
        error_fecha = _validar_fecha(fecha_ingreso, "fecha_ingreso")
        if error_fecha:
            return jsonify({"success": False, "error": error_fecha}), 400
        updates.append("fecha_ingreso = COALESCE(CAST(:fi AS TEXT), fecha_ingreso)")
        params["fi"] = fecha_ingreso

    if "posee_vehiculo" in data:
        updates.append("posee_vehiculo = :pv")
        params["pv"] = int(data["posee_vehiculo"])

    if "vehiculo_datos" in data:
        updates.append("vehiculo_datos = :vd")
        params["vd"] = data["vehiculo_datos"]

    if "direccion" in data:
        updates.append("direccion = :d")
        params["d"] = data["direccion"]

    if "estatus" in data or "activo" in data:
        estatus = int(data.get("estatus", data.get("activo", 1)))
        updates.append("activo = :activo")
        params["activo"] = estatus

    existing_extra_raw = db.session.execute(
        text("SELECT atributos_extra FROM entidades WHERE id = :id"),
        {"id": empleado_id}
    ).scalar()
    existing_extra = {}
    if existing_extra_raw:
        try:
            existing_extra = json.loads(existing_extra_raw)
        except (ValueError, TypeError):
            pass

    extras_cambiados = False

    if "comision_base" in data:
        comision_base = data.get("comision_base")
        if comision_base in [None, ""]:
            existing_extra.pop("comision_base", None)
        else:
            try:
                comision_base = float(comision_base)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "comision_base debe ser un número."}), 400
            if comision_base < 0:
                return jsonify({"success": False, "error": "comision_base no puede ser negativa."}), 400
            existing_extra["comision_base"] = comision_base
        extras_cambiados = True

    for campo in ("provincia", "municipio", "sector"):
        if campo in data:
            existing_extra[campo] = data.get(campo, "")
            extras_cambiados = True

    if extras_cambiados:
        updates.append("atributos_extra = :extra")
        params["extra"] = json.dumps(existing_extra)

    updates.append("nombre = :nombre")
    params["nombre"] = nombre

    db.session.execute(
        text(f"UPDATE entidades SET {', '.join(updates)} WHERE id = :id"),
        params
    )

    if params.get("activo") == 0:
        db.session.execute(
            text("UPDATE proyectos SET captador_id = NULL WHERE captador_id = :id"),
            {"id": empleado_id}
        )

    db.session.commit()
    return jsonify({"success": True, "message": "Empleado actualizado correctamente."})

@maestros_api_bp.route("/empleados/<int:empleado_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_empleado(empleado_id):
    try:
        db.session.execute(text("UPDATE entidades SET activo = 0 WHERE id = :id"), {"id": empleado_id})
        db.session.execute(text("UPDATE proyectos SET captador_id = NULL WHERE captador_id = :id"), {"id": empleado_id})
        db.session.commit()
        return jsonify({"success": True, "message": "Empleado desactivado correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en maestros_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

# --- CONSTRUCTORAS ---
@maestros_api_bp.route("/constructoras", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_constructoras():
    search_cols = ['nombre', 'rnc', 'contacto', 'telefono', 'provincia', 'direccion']
    sort_cols = ['nombre', 'rnc', 'provincia', 'activo', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    if not order_clause:
        order_clause = "ORDER BY id DESC"

    total_filtered = db.session.execute(text(f"SELECT COUNT(id) FROM contrapartes {where_clause}"), params).scalar() or 0
    total_records = db.session.execute(text("SELECT COUNT(id) FROM contrapartes WHERE activo = 1")).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"SELECT id, nombre, rnc, telefono, contacto, activo, atributos_extra FROM contrapartes {where_clause} {order_clause} LIMIT :limit OFFSET :offset"),
        params
    ).mappings().all()

    import json
    items = []
    for r in rows:
        extra = json.loads(r["atributos_extra"]) if r.get("atributos_extra") else {}
        items.append({
            "id": r["id"],
            "nombre": r["nombre"],
            "rnc": r["rnc"],
            "telefono": r["telefono"],
            "contacto": r["contacto"],
            "activo": bool(r["activo"]),
            "email": extra.get("email", ""),
            "direccion": extra.get("direccion", ""),
            "provincia": extra.get("provincia", ""),
            "representante_legal": extra.get("representante_legal", ""),
            "especialidad": extra.get("especialidad", [])
        })

    if is_dt:
        return jsonify({"draw": draw, "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items})
    return jsonify({"success": True, "items": items, "total": total_filtered, "constructoras": items})


@maestros_api_bp.route("/constructoras", methods=["POST"])
@requiere_rol("Admin")
def crear_constructora():
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()
    rnc = data.get("rnc", "").strip()
    telefono = data.get("telefono")
    contacto = data.get("contacto")
    activo = int(data.get("activo", 1))

    if not nombre:
        return jsonify({"success": False, "error": "El nombre de la constructora es requerido."}), 400

    import json
    extra = {
        "email": data.get("email", ""),
        "direccion": data.get("direccion", ""),
        "provincia": data.get("provincia", ""),
        "representante_legal": data.get("representante_legal", ""),
        "especialidad": data.get("especialidad", [])
    }

    from sqlalchemy.exc import IntegrityError
    try:
        db.session.execute(
            text("""
                INSERT INTO contrapartes (nombre, rnc, telefono, contacto, activo, atributos_extra)
                VALUES (:nom, :rnc, :tel, :con, :act, :extra)
            """),
            {"nom": nombre, "rnc": rnc, "tel": telefono, "con": contacto, "act": activo, "extra": json.dumps(extra)}
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"IntegrityError en {request.endpoint}: {e}")
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único (RNC, Cédula o Nombre)."}), 409
    return jsonify({"success": True, "message": f"Constructora '{nombre}' registrada exitosamente."})

@maestros_api_bp.route("/constructoras/<int:constructora_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_constructora(constructora_id):
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()
    rnc = data.get("rnc", "").strip()
    telefono = data.get("telefono")
    contacto = data.get("contacto")
    activo = int(data.get("activo", 1))

    if not nombre:
        return jsonify({"success": False, "error": "El nombre de la constructora es requerido."}), 400

    import json
    existing_extra_raw = db.session.execute(text("SELECT atributos_extra FROM contrapartes WHERE id = :id"), {"id": constructora_id}).scalar()
    existing_extra = {}
    if existing_extra_raw:
        try:
            existing_extra = json.loads(existing_extra_raw)
        except:
            pass
    existing_extra["email"] = data.get("email", existing_extra.get("email", ""))
    existing_extra["direccion"] = data.get("direccion", existing_extra.get("direccion", ""))
    existing_extra["provincia"] = data.get("provincia", existing_extra.get("provincia", ""))
    existing_extra["representante_legal"] = data.get("representante_legal", existing_extra.get("representante_legal", ""))
    if "especialidad" in data:
        existing_extra["especialidad"] = data.get("especialidad", [])

    resultado = db.session.execute(
        text("""
            UPDATE contrapartes 
            SET nombre = :nombre, rnc = :rnc, telefono = :telefono, contacto = :contacto, activo = :act, atributos_extra = :extra
            WHERE id = :id
        """),
        {"nombre": nombre, "rnc": rnc, "telefono": telefono, "contacto": contacto, "act": activo, "extra": json.dumps(existing_extra), "id": constructora_id}
    )
    if resultado.rowcount == 0:
        db.session.rollback()
        return jsonify({"success": False, "error": "Constructora no encontrada."}), 404
    db.session.commit()
    return jsonify({"success": True, "message": "Constructora actualizada correctamente."})

@maestros_api_bp.route("/constructoras/<int:constructora_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_constructora(constructora_id):
    try:
        db.session.execute(text("UPDATE contrapartes SET activo = 0 WHERE id = :id"), {"id": constructora_id})
        db.session.commit()
        return jsonify({"success": True, "message": "Constructora desactivada correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en maestros_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

# --- PROYECTOS ---
@maestros_api_bp.route("/proyectos", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_proyectos():
    search_cols = ['p.nombre', 'c.nombre', 'p.etapa']
    sort_cols = ['p.nombre', 'c.nombre', 'p.etapa', 'p.tipo_inmueble', 'p.unidades_totales', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols, active_prefix='p')
    
    if not order_clause:
        order_clause = "ORDER BY p.nombre"
    
    total_filtered = db.session.execute(text(f"SELECT COUNT(p.id) FROM proyectos p LEFT JOIN contrapartes c ON p.contraparte_id = c.id {where_clause}"), params).scalar() or 0
    total_records = db.session.execute(text("SELECT COUNT(id) FROM proyectos WHERE activo = 1")).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset
        
    es_exclusivo_sql = ", p.es_exclusivo" if _proyectos_tiene_es_exclusivo() else ""

    rows = db.session.execute(
        text(f"""SELECT p.id, p.nombre, p.etapa, p.tipo_inmueble, p.provincia, p.municipio,
               p.unidades_totales, c.nombre as constructora, p.contraparte_id,
               p.sector, p.direccion, p.financiamiento, p.institucion_bancaria,
               p.fecha_captacion, p.captador_id, p.correos_ventas, p.forma_registro,
               p.encargado_id{es_exclusivo_sql},
               enc.nombre || ' ' || enc.apellido as encargado_nombre,
               cap.nombre || ' ' || cap.apellido as captador_nombre
               FROM proyectos p
               LEFT JOIN contrapartes c ON p.contraparte_id = c.id
               LEFT JOIN entidades enc ON p.encargado_id = enc.id
               LEFT JOIN entidades cap ON p.captador_id = cap.id
               {where_clause} {order_clause} LIMIT :limit OFFSET :offset"""),
        params
    ).mappings().all()

    items = [dict(r) for r in rows]
    for item in items:
        item["es_exclusivo"] = item.get("es_exclusivo", False)
    if is_dt:
        return jsonify({"draw": draw, "recordsTotal": total_records, "recordsFiltered": total_filtered, "data": items})
    return jsonify({"success": True, "items": items, "total": total_filtered, "proyectos": items})


@maestros_api_bp.route("/proyectos", methods=["POST"])
@requiere_rol("Admin")
def crear_proyecto():
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()
    def get_int_or_none(val):
        return int(val) if val not in [None, ""] else None

    contraparte_id = get_int_or_none(data.get("contraparte_id"))
    encargado_id = get_int_or_none(data.get("encargado_id"))
    captador_id = get_int_or_none(data.get("captador_id"))
    etapa = data.get("etapa", "En Planos")
    tipo_inmueble = data.get("tipo_inmueble", "Apartamento")
    provincia = data.get("provincia", "Santo Domingo")
    municipio = data.get("municipio", "Santo Domingo Este")
    unidades_totales = get_int_or_none(data.get("unidades_totales")) or 24
    
    sector = data.get("sector", "")
    direccion = data.get("direccion", "")
    financiamiento = 1 if data.get("financiamiento") in [True, 1, "1", "true"] else 0
    institucion_bancaria = data.get("institucion_bancaria", "")
    fecha_captacion = data.get("fecha_captacion") or None
    correos_ventas = data.get("correos_ventas", "")
    forma_registro = data.get("forma_registro", "")
    es_exclusivo = 1 if data.get("es_exclusivo", False) in [True, 1, "1", "true"] else 0

    if not nombre:
        return jsonify({"success": False, "error": "El nombre del proyecto es requerido."}), 400

    from sqlalchemy.exc import IntegrityError
    try:
        tiene_es_exclusivo = _proyectos_tiene_es_exclusivo()
        es_excl_col = ", es_exclusivo" if tiene_es_exclusivo else ""
        es_excl_val = ", :es_exclusivo" if tiene_es_exclusivo else ""
        params_insert = {
            "nom": nombre, "cid": contraparte_id, "etapa": etapa, "tipo": tipo_inmueble,
            "prov": provincia, "mun": municipio, "uni": unidades_totales,
            "sector": sector, "direccion": direccion, "financiamiento": financiamiento,
            "institucion_bancaria": institucion_bancaria, "fecha_captacion": fecha_captacion,
            "captador_id": captador_id, "encargado_id": encargado_id,
            "correos_ventas": correos_ventas, "forma_registro": forma_registro
        }
        if tiene_es_exclusivo:
            params_insert["es_exclusivo"] = es_exclusivo

        db.session.execute(
            text(f"""
                INSERT INTO proyectos (nombre, contraparte_id, etapa, tipo_inmueble, provincia, municipio, unidades_totales, 
                sector, direccion, financiamiento, institucion_bancaria, fecha_captacion, captador_id, encargado_id, correos_ventas, forma_registro{es_excl_col}, activo, amenidades)
                VALUES (:nom, :cid, :etapa, :tipo, :prov, :mun, :uni, :sector, :direccion, :financiamiento, :institucion_bancaria, :fecha_captacion, :captador_id, :encargado_id, :correos_ventas, :forma_registro{es_excl_val}, 1, '[]')
            """),
            params_insert
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"IntegrityError en {request.endpoint}: {e}")
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único (RNC, Cédula o Nombre)."}), 409
    registrar_auditoria(1, 'admin', 'crear_proyecto', 'MAESTROS', f'Proyecto {nombre} registrado')
    return jsonify({"success": True, "message": f"Proyecto '{nombre}' registrado exitosamente."})

@maestros_api_bp.route("/proyectos/<int:proyecto_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_proyecto(proyecto_id):
    data = request.get_json() or {}

    def get_int_or_none(val):
        return int(val) if val not in [None, ""] else None

    updates = {}
    if "nombre" in data:
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return jsonify({"success": False, "error": "El nombre del proyecto es requerido."}), 400
        updates["nombre"] = nombre
    if "etapa" in data:
        updates["etapa"] = data.get("etapa")
    if "unidades_totales" in data:
        updates["unidades_totales"] = get_int_or_none(data.get("unidades_totales")) or 24
    if "contraparte_id" in data and data.get("contraparte_id") not in [None, ""]:
        updates["contraparte_id"] = get_int_or_none(data.get("contraparte_id"))
    for campo in ("sector", "direccion", "provincia", "municipio", "institucion_bancaria",
                  "correos_ventas", "forma_registro"):
        if campo in data:
            updates[campo] = data.get(campo) or ""
    if "tipo_inmueble" in data:
        updates["tipo_inmueble"] = data.get("tipo_inmueble")
    if "financiamiento" in data:
        updates["financiamiento"] = 1 if data.get("financiamiento") in [True, 1, "1", "true"] else 0
    if "fecha_captacion" in data:
        updates["fecha_captacion"] = data.get("fecha_captacion") or None
    if "captador_id" in data:
        updates["captador_id"] = get_int_or_none(data.get("captador_id"))
    if "encargado_id" in data:
        updates["encargado_id"] = get_int_or_none(data.get("encargado_id"))
    if _proyectos_tiene_es_exclusivo() and "es_exclusivo" in data:
        updates["es_exclusivo"] = 1 if data.get("es_exclusivo") in [True, 1, "1", "true"] else 0

    if not updates:
        return jsonify({"success": False, "error": "Nada para actualizar."}), 400

    updates["id"] = proyecto_id
    columnas = ", ".join(f"{c} = :{c}" for c in updates if c != "id")

    try:
        resultado = db.session.execute(
            text(f"UPDATE proyectos SET {columnas} WHERE id = :id"),
            updates
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"IntegrityError en {request.endpoint}: {e}")
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único o hay un error de dependencia."}), 409

    if resultado.rowcount == 0:
        return jsonify({"success": False, "error": "Proyecto no encontrado."}), 404

    registrar_auditoria(1, 'admin', 'editar_proyecto', 'MAESTROS', f'Proyecto {proyecto_id} actualizado')
    return jsonify({"success": True, "message": "Proyecto actualizado correctamente."})

@maestros_api_bp.route("/proyectos/<int:proyecto_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_proyecto(proyecto_id):
    try:
        db.session.execute(text("UPDATE proyectos SET activo = 0 WHERE id = :id"), {"id": proyecto_id})
        db.session.commit()
        return jsonify({"success": True, "message": "Proyecto desactivado correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en maestros_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500

# --- PROVEEDORES ---
@maestros_api_bp.route("/proveedores", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_proveedores():
    search_cols = ['razon_social', 'ruc', 'telefono', 'email']
    sort_cols = ['razon_social', 'ruc', 'telefono', 'email', 'estado', None]
    is_dt, draw, where_clause, params, limit, offset, order_clause = dt_args(request, search_cols, sort_cols)
    
    if not order_clause:
        order_clause = "ORDER BY id DESC"
        
    total_filtered = db.session.execute(text(f"SELECT COUNT(id) FROM proveedores {where_clause}"), params).scalar() or 0
    total_records = db.session.execute(text("SELECT COUNT(id) FROM proveedores")).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset

    rows = db.session.execute(
        text(f"SELECT * FROM proveedores {where_clause} {order_clause} LIMIT :limit OFFSET :offset"),
        params
    ).mappings().all()

    return jsonify({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": total_filtered,
        "data": [dict(r) for r in rows]
    })

@maestros_api_bp.route("/proveedores", methods=["POST"])
@requiere_rol("Admin")
def crear_proveedor():
    data = request.get_json() or {}
    razon_social = data.get("razon_social", "").strip()
    ruc = data.get("ruc", "").strip()
    telefono = data.get("telefono", "")
    email = data.get("email", "")
    direccion = data.get("direccion", "")
    descripcion = data.get("descripcion", "").strip()
    estado = data.get("estado", "activo").strip()

    import re
    if not razon_social:
        return jsonify({"success": False, "error": "Razón social requerida."}), 400

    ruc_clean = ruc.replace("-", "").replace(" ", "")
    if ruc_clean and ruc_clean != "0000000000" and not re.match(r"^(\d{9}|\d{11})$", ruc_clean):
        return jsonify({"success": False, "error": "RNC inválido. Debe tener 9 u 11 dígitos."}), 400
    ruc = ruc_clean

    if ruc and ruc != "0000000000":
        existente = db.session.execute(text("SELECT id FROM proveedores WHERE ruc = :ruc"), {"ruc": ruc}).scalar()
        if existente:
            return jsonify({"success": False, "error": f"El RNC {ruc} ya está registrado."}), 400

    from sqlalchemy.exc import IntegrityError
    try:
        db.session.execute(
            text("""
            INSERT INTO proveedores (razon_social, ruc, telefono, email, direccion, descripcion, estado, fecha_registro)
            VALUES (:razon_social, :ruc, :telefono, :email, :direccion, :descripcion, :estado, CURRENT_DATE)
            """),
            {"razon_social": razon_social, "ruc": ruc, "telefono": telefono, "email": email,
             "direccion": direccion, "descripcion": descripcion, "estado": estado}
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"IntegrityError en {request.endpoint}: {e}")
        return jsonify({"success": False, "error": "Ya existe un registro con este identificador único (RNC, Cédula o Nombre)."}), 409
    registrar_auditoria(1, 'admin', 'crear_proveedor', 'MAESTROS', f'Proveedor {razon_social} registrado')
    return jsonify({"success": True, "message": "Proveedor creado exitosamente."})

@maestros_api_bp.route("/proveedores/<int:proveedor_id>", methods=["PUT"])
@requiere_rol("Admin")
def actualizar_proveedor(proveedor_id):
    data = request.get_json() or {}
    razon_social = data.get("razon_social", "").strip()
    ruc = data.get("ruc", "").strip()
    telefono = data.get("telefono", "")
    email = data.get("email", "")
    direccion = data.get("direccion", "")
    descripcion = data.get("descripcion", "").strip()
    estado = data.get("estado", "activo").strip()

    import re
    if not razon_social:
        return jsonify({"success": False, "error": "Razón social requerida."}), 400

    ruc_clean = ruc.replace("-", "").replace(" ", "")
    if ruc_clean and ruc_clean != "0000000000" and not re.match(r"^(\d{9}|\d{11})$", ruc_clean):
        return jsonify({"success": False, "error": "RNC inválido. Debe tener 9 u 11 dígitos."}), 400
    ruc = ruc_clean

    if ruc and ruc != "0000000000":
        existente = db.session.execute(text("SELECT id FROM proveedores WHERE ruc = :ruc AND id != :id"), {"ruc": ruc, "id": proveedor_id}).scalar()
        if existente:
            return jsonify({"success": False, "error": f"El RNC {ruc} ya está registrado en otro proveedor."}), 400

    resultado = db.session.execute(
        text("""
        UPDATE proveedores
        SET razon_social = :razon_social, ruc = :ruc, telefono = :telefono, email = :email,
            direccion = :direccion, descripcion = :descripcion, estado = :estado
        WHERE id = :id
        """),
        {"razon_social": razon_social, "ruc": ruc, "telefono": telefono, "email": email,
         "direccion": direccion, "descripcion": descripcion, "estado": estado, "id": proveedor_id}
    )
    if resultado.rowcount == 0:
        db.session.rollback()
        return jsonify({"success": False, "error": "Proveedor no encontrado."}), 404
    db.session.commit()
    registrar_auditoria(1, 'admin', 'editar_proveedor', 'MAESTROS', f'Proveedor {proveedor_id} actualizado')
    return jsonify({"success": True, "message": "Proveedor actualizado correctamente."})


# --- INMOBILIARIAS (para dropdown en Empleados Externos) ---
@maestros_api_bp.route("/inmobiliarias", methods=["GET"])
@requiere_rol("Admin", "Gerente Comercial", "Gerente Financiera", "Gerente General", "CEO")
def listar_inmobiliarias():
    rows = db.session.execute(
        text("SELECT id, nombre FROM contrapartes WHERE activo = 1 ORDER BY nombre")
    ).mappings().all()
    items = [{"id": r["id"], "nombre": r["nombre"].upper()} for r in rows]
    return jsonify({"success": True, "items": items})

@maestros_api_bp.route("/proveedores/<int:proveedor_id>", methods=["DELETE"])
@requiere_rol("Admin")
def borrar_proveedor(proveedor_id):
    try:
        db.session.execute(text("UPDATE proveedores SET estado = 'inactivo' WHERE id = :id"), {"id": proveedor_id})
        db.session.commit()
        return jsonify({"success": True, "message": "Proveedor desactivado correctamente."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error en maestros_api: %s", repr(e))
        return jsonify({"success": False, "error": "Error interno al procesar la solicitud. Intente nuevamente."}), 500
