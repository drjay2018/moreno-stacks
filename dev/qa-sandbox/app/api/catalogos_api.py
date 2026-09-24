"""
catalogos_api.py — Endpoint API para servir listas oficiales de negocio y geografía.
"""

from flask import Blueprint, jsonify
from sqlalchemy import text
from app.extensions import db
from app.core.auth_middleware import requiere_rol, requiere_login
from app.core.catalogos import (
    PAISES, PROVINCIAS_RD, MUNICIPIOS_POR_PROVINCIA, GENEROS, ESTADOS_CIVILES,
    VIAS_REFERIDAS, ETAPAS_EMBUDO, MOTIVOS_COMPRA, METODOS_PAGO_PREFERIDO,
    TIEMPOS_MUDANZA, AMENIDADES_DISPONIBLES, MONEDAS, OCUPACIONES, RANGOS_INGRESO_MENSUAL,
    TIPOS_INMUEBLE,
)

catalogos_api_bp = Blueprint("catalogos_api", __name__, url_prefix="/api/catalogos")


def _obtener_catalogo_db(tabla, activo=True):
    """Lee registros de una tabla de catalogo AE desde la DB."""
    try:
        where = "WHERE activo = 1" if activo else ""
        rows = db.session.execute(text(f"SELECT * FROM {tabla} {where} ORDER BY id")).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


@catalogos_api_bp.route("", methods=["GET"])
@requiere_login
def obtener_catalogos():
    # === Catalogos desde DB (AlterEstate) — fuente primaria ===
    cat_paises = _obtener_catalogo_db("cat_paises")
    cat_ciudades = _obtener_catalogo_db("cat_ciudades")
    cat_sectores = _obtener_catalogo_db("cat_sectores")

    # Paises como lista de strings (para dropdowns)
    paises_db = [p["nombre"] for p in cat_paises if p.get("nombre")]

    # Mapa: pais_id → nombre del país
    pais_id_to_name = {p["id"]: p["nombre"] for p in cat_paises if p.get("id") and p.get("nombre")}

    # === Agrupar ciudades por país → provincia → ciudades ===
    # geo_data = { "Dominican Republic": { "provincias": ["Santo Domingo", ...], "ciudades": {"Santo Domingo": ["SDN", "SDE", ...]} } }
    geo_data = {}
    for c in cat_ciudades:
        pais_id = c.get("pais_id")
        pais_name = pais_id_to_name.get(pais_id, "Otro")
        prov = c.get("provincia") or "Sin Provincia"
        nombre = c.get("nombre")
        if not nombre:
            continue
        if pais_name not in geo_data:
            geo_data[pais_name] = {"provincias": set(), "ciudades": {}}
        geo_data[pais_name]["provincias"].add(prov)
        geo_data[pais_name]["ciudades"].setdefault(prov, []).append(nombre)

    # Convertir sets a listas ordenadas
    for pais_name in geo_data:
        geo_data[pais_name]["provincias"] = sorted(geo_data[pais_name]["provincias"])
        for prov in geo_data[pais_name]["ciudades"]:
            geo_data[pais_name]["ciudades"][prov] = sorted(geo_data[pais_name]["ciudades"][prov])

    # === Agrupar sectores por ciudad_nombre ===
    sectores_por_ciudad = {}
    for s in cat_sectores:
        ciudad_nombre = s.get("ciudad_nombre")
        nombre = s.get("nombre")
        if ciudad_nombre and nombre:
            sectores_por_ciudad.setdefault(ciudad_nombre, []).append(nombre)
    for k in sectores_por_ciudad:
        sectores_por_ciudad[k] = sorted(sectores_por_ciudad[k])

    return jsonify({
        "success": True,
        # === Catalogos estaticos existentes (backward compat) ===
        "paises": PAISES,
        "provincias_rd": PROVINCIAS_RD,
        "municipios_por_provincia": MUNICIPIOS_POR_PROVINCIA,
        "generos": GENEROS,
        "estados_civiles": ESTADOS_CIVILES,
        "vias_referidas": VIAS_REFERIDAS,
        "etapas_embudo": ETAPAS_EMBUDO,
        "motivos_compra": MOTIVOS_COMPRA,
        "metodos_pago_preferido": METODOS_PAGO_PREFERIDO,
        "tiempos_mudanza": TIEMPOS_MUDANZA,
        "amenidades_disponibles": AMENIDADES_DISPONIBLES,
        "monedas": MONEDAS,
        "ocupaciones": OCUPACIONES,
        "rangos_ingreso_mensual": RANGOS_INGRESO_MENSUAL,
        "tipos_inmueble": TIPOS_INMUEBLE,
        # === Catalogos desde DB (datos completos) ===
        "cat_paises": cat_paises,
        "cat_ciudades": cat_ciudades,
        "cat_sectores": cat_sectores,
        "cat_tipos_inmueble": _obtener_catalogo_db("cat_tipos_inmueble"),
        "cat_tipos_listado": _obtener_catalogo_db("cat_tipos_listado"),
        "cat_estados_unidad": _obtener_catalogo_db("cat_estados_unidad"),
        "cat_condiciones_inmueble": _obtener_catalogo_db("cat_condiciones_inmueble"),
        "cat_amenidades_db": _obtener_catalogo_db("cat_amenidades"),
        "cat_monedas": _obtener_catalogo_db("cat_monedas"),
        # === Datos geográficos agrupados por país ===
        "geo_data": geo_data,
        "sectores_por_ciudad": sectores_por_ciudad,
        "paises_db": paises_db,
    })
