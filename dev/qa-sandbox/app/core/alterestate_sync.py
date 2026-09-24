"""
alterestate_sync.py — Motor de sincronizacion DLAB CRM ↔ AlterEstate.

Orquesta la sincronizacion de entidades entre la API de AlterEstate y las tablas DLAB.
Usa api_entity_mapping para trackear la correspondencia external↔internal.

Entidades soportadas:
    - countries   → cat_paises          (upsert by codigo)
    - cities      → cat_ciudades        (upsert by ae_city_id)
    - sectors     → cat_sectores        (upsert by ae_sector_id)
    - properties  → proyectos + mapping (upsert by ae_uid)
    - agents      → entidades + mapping (upsert by ae_uid → mapear a entidad)
    - leads       → POST reverse (enviar lead a AE)
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.extensions import db
from app.core.auditoria import registrar_auditoria
from app.core.logger import log_info, log_warn, log_error

logger = logging.getLogger(__name__)

# ─── Constantes ────────────────────────────────────────────────────────────────
SYNC_MODULE = "ALTERESTATE_SYNC"


# ═══════════════════════════════════════════════════════════════════════════════
# A) GENERIC UPSERT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def upsert_entity(
    provider: str,
    entity_type: str,
    external_data: dict,
    dlab_table: str,
    match_config: dict,
    field_mapping: dict,
    defaults: dict = None,
    extra_meta: dict = None,
) -> dict:
    """
    Upsert generico: inserta o actualiza una entidad DLAB desde datos externos.
    
    Flujo:
    1. Buscar en api_entity_mapping por (provider, entity_type, external_id)
    2. Si existe → UPDATE con COALESCE en la tabla DLAB
    3. Si no existe → buscar por match natural (email, cedula, nombre)
    4. Si tampoco → INSERT nuevo registro
    5. Crear/actualizar registro en api_entity_mapping
    6. Retornar stats: {action, internal_id, external_id}
    
    Args:
        provider: 'alterestate'
        entity_type: 'country', 'city', 'sector', 'property', 'agent'
        external_data: dict con los datos de la API externa
        dlab_table: nombre de la tabla DLAB destino
        match_config: {
            'external_id_key': 'uid',           # key en external_data para el ID externo
            'external_uid_key': None,            # key secundaria (slug, etc.)
            'natural_key': 'nombre',             # fallback: buscar por este campo natural
            'natural_key_2': None,               # segundo campo natural opcional
        }
        field_mapping: {
            'dlab_col': 'external_key',          # mapeo de columnas
            # o callable: 'dlab_col': lambda ext: ext.get('key', '').upper()
        }
        defaults: dict de valores por defecto para INSERTs
    
    Returns:
        dict: {action: 'insert'|'update'|'skip', internal_id: int, external_id: str, 
               match_method: 'mapping'|'natural'|'new'}
    """
    defaults = defaults or {}
    stats = {"action": "skip", "internal_id": None, "external_id": None, "match_method": None}

    # 1. Extraer external_id
    ext_id_key = match_config.get("external_id_key", "id")
    ext_uid_key = match_config.get("external_uid_key")
    external_id = str(external_data.get(ext_id_key, ""))
    external_uid = str(external_data.get(ext_uid_key, "")) if ext_uid_key else None

    if not external_id:
        stats["action"] = "error"
        stats["error"] = f"external_id vacio (key: {ext_id_key})"
        return stats

    stats["external_id"] = external_id

    # 2. Buscar en api_entity_mapping
    existing_mapping = _find_mapping(provider, entity_type, external_id)

    if existing_mapping:
        # UPDATE existente
        internal_id = existing_mapping["internal_id"]
        _update_dlab_entity(dlab_table, internal_id, external_data, field_mapping, defaults)
        _upsert_mapping(provider, entity_type, external_id, external_uid, internal_id, dlab_table, extra_meta)
        stats["action"] = "update"
        stats["internal_id"] = internal_id
        stats["match_method"] = "mapping"
        return stats

    # 3. Buscar por match natural
    natural_key = match_config.get("natural_key")
    natural_key_2 = match_config.get("natural_key_2")

    if natural_key:
        internal_id = _find_by_natural_key(dlab_table, natural_key, natural_key_2, external_data)
        if internal_id:
            _update_dlab_entity(dlab_table, internal_id, external_data, field_mapping, defaults)
            _upsert_mapping(provider, entity_type, external_id, external_uid, internal_id, dlab_table, extra_meta)
            stats["action"] = "update"
            stats["internal_id"] = internal_id
            stats["match_method"] = "natural"
            return stats

    # 4. INSERT nuevo
    internal_id = _insert_dlab_entity(dlab_table, external_data, field_mapping, defaults)
    if internal_id:
        _upsert_mapping(provider, entity_type, external_id, external_uid, internal_id, dlab_table, extra_meta)
        stats["action"] = "insert"
        stats["internal_id"] = internal_id
        stats["match_method"] = "new"
    else:
        stats["action"] = "error"
        stats["error"] = "INSERT falló"

    return stats


def _compute_sync_hash(data: dict) -> str:
    """Hash MD5 de los datos para detectar cambios."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ─── Mapping helpers ────────────────────────────────────────────────────────────

def _find_mapping(provider: str, entity_type: str, external_id: str) -> Optional[dict]:
    """Busca un registro en api_entity_mapping."""
    try:
        row = db.session.execute(
            text(
                "SELECT id, internal_id, internal_table, sync_hash "
                "FROM api_entity_mapping "
                "WHERE provider = :prov AND entity_type = :et AND external_id = :eid"
            ),
            {"prov": provider, "et": entity_type, "eid": external_id},
        ).mappings().first()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"[SYNC] Error buscando mapping {provider}/{entity_type}/{external_id}: {e}")
        return None


def _upsert_mapping(
    provider: str, entity_type: str, external_id: str,
    external_uid: str, internal_id: int, internal_table: str,
    extra_meta: dict = None,
):
    """Crea o actualiza el registro de mapping."""
    now = datetime.now().isoformat()
    meta = json.dumps(extra_meta or {})
    try:
        db.session.execute(
            text(
                "INSERT INTO api_entity_mapping "
                "(provider, entity_type, external_id, external_uid, internal_id, internal_table, "
                " last_synced_at, extra_meta, created_at, updated_at) "
                "VALUES (:prov, :et, :eid, :euid, :iid, :itable, :lsync, :meta, :now, :now) "
                "ON CONFLICT(provider, entity_type, external_id) DO UPDATE SET "
                " external_uid = COALESCE(excluded.external_uid, api_entity_mapping.external_uid), "
                " internal_id = excluded.internal_id, "
                " internal_table = excluded.internal_table, "
                " last_synced_at = excluded.last_synced_at, "
                " extra_meta = excluded.extra_meta, "
                " updated_at = excluded.updated_at"
            ),
            {
                "prov": provider, "et": entity_type, "eid": external_id,
                "euid": external_uid, "iid": internal_id, "itable": internal_table,
                "lsync": now, "meta": meta, "now": now,
            },
        )
    except Exception as e:
        logger.error(f"[SYNC] Error upserting mapping: {e}")


def _find_by_natural_key(
    dlab_table: str, natural_key: str, natural_key_2: str, external_data: dict
) -> Optional[int]:
    """Busca un registro por clave natural (email, cedula, nombre, etc.)."""
    value1 = external_data.get(natural_key)
    if not value1:
        return None

    try:
        query = f"SELECT id FROM {dlab_table} WHERE {natural_key} = :val1 AND activo = 1"
        params = {"val1": value1}

        if natural_key_2:
            value2 = external_data.get(natural_key_2)
            if value2:
                query += f" AND {natural_key_2} = :val2"
                params["val2"] = value2

        row = db.session.execute(text(query), params).mappings().first()
        return row["id"] if row else None
    except Exception as e:
        logger.error(f"[SYNC] Error busqueda natural key {dlab_table}.{natural_key}: {e}")
        return None


# ─── INSERT / UPDATE helpers ────────────────────────────────────────────────────

def _map_fields(external_data: dict, field_mapping: dict, defaults: dict) -> dict:
    """
    Mapea datos externos a columnas DLAB.
    field_mapping puede tener:
        - strings: 'dlab_col' → 'ext_key'
        - callables: 'dlab_col' → lambda ext_data: ...
    """
    mapped = {}

    for dlab_col, ext_key_or_fn in field_mapping.items():
        if callable(ext_key_or_fn):
            value = ext_key_or_fn(external_data)
        else:
            value = external_data.get(ext_key_or_fn)

        # Aplicar defaults si el valor es None o vacio
        if (value is None or value == "") and dlab_col in defaults:
            value = defaults[dlab_col]

        mapped[dlab_col] = value

    return mapped


def _insert_dlab_entity(
    dlab_table: str, external_data: dict, field_mapping: dict, defaults: dict
) -> Optional[int]:
    """INSERT un nuevo registro en la tabla DLAB. Retorna el ID insertado."""
    mapped = _map_fields(external_data, field_mapping, defaults)

    # Agregar activo=1 por defecto si no esta mapeado
    if "activo" not in mapped:
        mapped["activo"] = 1

    # Filtrar None de defaults (que no deberian ir al INSERT si no se setearon)
    cols = [k for k, v in mapped.items() if v is not None or k in defaults]

    if not cols:
        return None

    col_str = ", ".join(cols)
    placeholders = ", ".join([f":{c}" for c in cols])
    params = {c: mapped[c] for c in cols}

    try:
        db.session.execute(
            text(f"INSERT INTO {dlab_table} ({col_str}) VALUES ({placeholders})"),
            params,
        )
        db.session.flush()
        # Obtener el ultimo ID insertado
        row = db.session.execute(text(f"SELECT MAX(id) FROM {dlab_table}")).scalar()
        return row
    except Exception as e:
        db.session.rollback()
        logger.error(f"[SYNC] INSERT falló en {dlab_table}: {e}")
        return None


def _update_dlab_entity(
    dlab_table: str, internal_id: int, external_data: dict,
    field_mapping: dict, defaults: dict,
):
    """UPDATE un registro existente con patron COALESCE (preserva valores no nulos)."""
    mapped = _map_fields(external_data, field_mapping, defaults)

    set_clauses = []
    params = {"_id": internal_id}

    for col, value in mapped.items():
        if value is not None and value != "":
            # COALESCE preserva el valor existente si el nuevo es None
            set_clauses.append(f"{col} = COALESCE(:{col}, {col})")
            params[col] = value
        # Si value es None → NO tocar la columna existente (preservar)

    if not set_clauses:
        return

    try:
        db.session.execute(
            text(f"UPDATE {dlab_table} SET {', '.join(set_clauses)} WHERE id = :_id"),
            params,
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"[SYNC] UPDATE falló en {dlab_table} id={internal_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# B) ENTITY-SPECIFIC SYNC FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def sync_countries(client) -> dict:
    """
    Sincroniza paises de AE → upsert en cat_paises (by codigo).
    
    AE no tiene endpoint /api/v1/countries/. Usamos los IDs documentados:
        149: Dominican Republic
        60: Panama
        198: Colombia
        199: Guatemala
        201: Chile
        202: Ecuador
        203: Mexico
        208: Peru
        209: United States
        212: Puerto Rico
    """
    log_info(SYNC_MODULE, "Iniciando sync de paises (desde doc AE)...")
    
    # IDs documentados en https://dev.alterestate.com/locations.md
    ae_countries = [
        {"id": 149, "name": "Dominican Republic"},
        {"id": 60, "name": "Panama"},
        {"id": 198, "name": "Colombia"},
        {"id": 199, "name": "Guatemala"},
        {"id": 201, "name": "Chile"},
        {"id": 202, "name": "Ecuador"},
        {"id": 203, "name": "Mexico"},
        {"id": 208, "name": "Peru"},
        {"id": 209, "name": "United States"},
        {"id": 212, "name": "Puerto Rico"},
    ]
    
    stats = {"insertados": 0, "actualizados": 0, "errores": 0}
    
    for c in ae_countries:
        result = upsert_entity(
            provider="alterestate",
            entity_type="country",
            external_data=c,
            dlab_table="cat_paises",
            match_config={
                "external_id_key": "id",
                "external_uid_key": None,
                "natural_key": "codigo",
                "natural_key_2": None,
            },
            field_mapping={
                "codigo": "id",
                "nombre": "name",
            },
            defaults={
                "codigo": str(c["id"]),
                "nombre": c["name"],
                "activo": 1,
            },
        )
        
        if result["action"] == "insert":
            stats["insertados"] += 1
        elif result["action"] == "update":
            stats["actualizados"] += 1
        elif result["action"] == "error":
            stats["errores"] += 1
    
    db.session.commit()
    log_info(SYNC_MODULE, f"Paises sync: {stats}")
    return stats


def sync_cities(client, country_id: int = None) -> dict:
    """
    Descarga ciudades de AE → upsert en cat_ciudades (by ae_city_id).
    
    Endpoint: GET /api/v1/cities/?country=<id>  (requiere country ID)
    
    Mapeo:
        AE → DLAB
        id → ae_city_id
        name → nombre
        province.name → provincia
    """
    # Si no se especifica pais, descargar de todos los paises soportados
    if country_id is None:
        country_ids = [149, 60, 198, 199, 201, 202, 203, 208, 209, 212]
    else:
        country_ids = [country_id]

    log_info(SYNC_MODULE, f"Iniciando sync de ciudades (paises: {country_ids})...")

    stats = {"insertados": 0, "actualizados": 0, "errores": 0}

    for cid in country_ids:
        try:
            # Cities endpoint es publico (no necesita auth)
            response = client.get_public(f"/api/v1/cities/", params={"country": cid})
            raw_data = response.get("data", {})
            cities = raw_data if isinstance(raw_data, list) else raw_data.get("results", [])

            for city in cities:
                # Resolver pais_id desde cat_paises por codigo AE
                pais_id = _resolve_pais_id(str(cid))

                result = upsert_entity(
                    provider="alterestate",
                    entity_type="city",
                    external_data=city,
                    dlab_table="cat_ciudades",
                    match_config={
                        "external_id_key": "id",
                        "external_uid_key": None,
                        "natural_key": "nombre",
                        "natural_key_2": "pais_id",
                    },
                    field_mapping={
                        "ae_city_id": lambda d: str(d.get("id", "")),
                        "nombre": "name",
                        "pais_id": lambda d: pais_id,
                        "provincia": lambda d: d.get("province", {}).get("name", "") if isinstance(d.get("province"), dict) else "",
                    },
                    defaults={
                        "ae_city_id": str(city.get("id", "")),
                        "nombre": city.get("name", ""),
                        "pais_id": pais_id or 1,
                        "activo": 1,
                    },
                )

                if result["action"] == "insert":
                    stats["insertados"] += 1
                elif result["action"] == "update":
                    stats["actualizados"] += 1
                elif result["action"] == "error":
                    stats["errores"] += 1

        except Exception as e:
            log_warn(SYNC_MODULE, f"Error descargando ciudades para pais {cid}: {e}")
            stats["errores"] += 1

    db.session.commit()
    log_info(SYNC_MODULE, f"Ciudades sync: {stats}")
    return stats


def sync_sectors(client, city_id: int = None) -> dict:
    """
    Descarga sectores de AE → upsert en cat_sectores (by ae_sector_id).
    
    Mapeo:
        AE → DLAB
        id → ae_sector_id
        name → nombre
        city (string name from AE) → ciudad_nombre
        city_id param → ciudad_id (FK a cat_ciudades, resolved via ae_city_id)
    """
    log_info(SYNC_MODULE, f"Iniciando sync de sectores (city_id={city_id})...")

    try:
        params = {}
        if city_id:
            params["city"] = city_id

        response = client.get_paginated_public("/api/v1/sectors/", params=params)
        sectors = response if isinstance(response, list) else response.get("data", [])

        stats = {"insertados": 0, "actualizados": 0, "errores": 0}

        # Resolver ciudad_id (DLAB FK) desde el city_id param (AE ID)
        resolved_ciudad_id = None
        if city_id:
            mapping = _find_mapping("alterestate", "city", str(city_id))
            if mapping:
                resolved_ciudad_id = mapping["internal_id"]

        for s in sectors:
            # AE city field is a string (city name), not a dict
            city_name = s.get("city", "") if isinstance(s.get("city"), str) else ""

            result = upsert_entity(
                provider="alterestate",
                entity_type="sector",
                external_data=s,
                dlab_table="cat_sectores",
                match_config={
                    "external_id_key": "id",
                    "external_uid_key": None,
                    "natural_key": "nombre",
                    "natural_key_2": "ciudad_id",
                },
                field_mapping={
                    "ae_sector_id": lambda d: str(d.get("id", "")),
                    "nombre": "name",
                    "ciudad_id": lambda d: resolved_ciudad_id,
                    "ciudad_nombre": lambda d: city_name,
                },
                defaults={
                    "ae_sector_id": str(s.get("id", "")),
                    "nombre": s.get("name", ""),
                    "activo": 1,
                },
            )

            if result["action"] == "insert":
                stats["insertados"] += 1
            elif result["action"] == "update":
                stats["actualizados"] += 1
            elif result["action"] == "error":
                stats["errores"] += 1

        db.session.commit()
        log_info(SYNC_MODULE, f"Sectores sync: {stats}")
        return stats

    except Exception as e:
        db.session.rollback()
        log_error(SYNC_MODULE, f"Error en sync_sectors: {e}", exc_info=True)
        return {"error": str(e)}


def sync_properties(client) -> dict:
    """
    Descarga propiedades de AE → upsert en proyectos + api_entity_mapping.
    
    Mapeo (segunda documentacion AE):
        AE → DLAB
        uid → ae_uid (en mapping)
        slug → ae_slug (en mapping)
        name → nombre
        short_description → descripcion
        category.name → tipo_inmueble (category es dict anidado)
        city → municipio (STRING directo, no dict)
        sector → sector (STRING directo, no dict)
        sale_price → precio_min, precio_max
        currency_sale → moneda
        cid → ae_cid (en atributos_extra)
    """
    log_info(SYNC_MODULE, "Iniciando sync de propiedades...")

    try:
        response = client.get_paginated_public_with_token("/api/v1/properties/filter/")
        properties = response if isinstance(response, list) else response.get("data", [])

        stats = {"insertados": 0, "actualizados": 0, "errores": 0}

        for p in properties:
            ext_uid = str(p.get("uid", p.get("id", "")))
            ext_slug = p.get("slug", "")

            # Construir atributos_extra con datos de AE
            atributos_extra = {
                "ae_cid": p.get("cid"),
                "ae_uid": ext_uid,
                "ae_slug": ext_slug,
                "short_description": p.get("short_description", ""),
                "currency_sale": p.get("currency_sale"),
                "listing_type": p.get("listing_type"),
                "ae_created_at": p.get("created_at"),
                "ae_updated_at": p.get("updated_at"),
            }

            result = upsert_entity(
                provider="alterestate",
                entity_type="property",
                external_data=p,
                dlab_table="proyectos",
                match_config={
                    "external_id_key": "uid",
                    "external_uid_key": "slug",
                    "natural_key": "nombre",
                    "natural_key_2": None,
                },
                field_mapping={
                    "nombre": "name",
                    "contraparte_id": lambda d: 1,  # Default: primera contraparte
                    "etapa": lambda d: _map_property_status(d.get("status", "")),
                    "tipo_inmueble": lambda d: d.get("category", {}).get("name", "Apartamento") if isinstance(d.get("category"), dict) else "Apartamento",
                    "municipio": lambda d: d.get("city", ""),
                    "sector": lambda d: d.get("sector", ""),
                    "direccion": lambda d: d.get("address", ""),
                    "precio_min": lambda d: d.get("sale_price"),
                    "precio_max": lambda d: d.get("sale_price"),
                    "amenidades": lambda d: json.dumps(d.get("amenities", [])),
                    "atributos_extra": lambda d: json.dumps(atributos_extra),
                    "activo": lambda d: 1 if d.get("is_active", True) else 0,
                },
                defaults={
                    "nombre": p.get("name", "Sin nombre"),
                    "contraparte_id": 1,
                    "etapa": _map_property_status(p.get("status", "")),
                    "tipo_inmueble": p.get("category", {}).get("name", "Apartamento") if isinstance(p.get("category"), dict) else "Apartamento",
                    "activo": 1,
                    "amenidades": "[]",
                    "atributos_extra": json.dumps(atributos_extra),
                },
            )

            if result["action"] == "insert":
                stats["insertados"] += 1
            elif result["action"] == "update":
                stats["actualizados"] += 1
            elif result["action"] == "error":
                stats["errores"] += 1

        db.session.commit()
        log_info(SYNC_MODULE, f"Propiedades sync: {stats}")
        return stats

    except Exception as e:
        db.session.rollback()
        log_error(SYNC_MODULE, f"Error en sync_properties: {e}", exc_info=True)
        return {"error": str(e)}


def sync_agents(client) -> dict:
    """
    Descarga agentes de AE → upsert en entidades + api_entity_mapping.
    
    Mapeo (segunda documentacion AE):
        AE → DLAB
        uid → ae_uid (en mapping)
        email → email
        first_name → nombre
        last_name → apellido
        phone → telefono
        position → posicion
        company → empresa
        team → atributos_extra.team
        division → atributos_extra.division
        properties (count) → atributos_extra.properties_count
    """
    log_info(SYNC_MODULE, "Iniciando sync de agentes...")

    try:
        # Agents endpoint: GET /api/v1/agents/ (retorna array directo, no paginado)
        response = client.get_public_with_token("/api/v1/agents/")
        raw_data = response.get("data", {})
        agents = raw_data if isinstance(raw_data, list) else raw_data.get("results", raw_data.get("data", []))

        stats = {"insertados": 0, "actualizados": 0, "errores": 0}

        for a in agents:
            ext_uid = str(a.get("uid", a.get("id", "")))
            email = a.get("email", "")
            nombre = a.get("first_name", "")
            apellido = a.get("last_name", "")

            # Generar cedula placeholder si no existe (unico constraint)
            cedula_ae = f"AE-{ext_uid}"

            atributos_extra = {
                "avatar": a.get("avatar"),
                "ae_uid": ext_uid,
                "ae_slug": a.get("slug"),
                "full_name": a.get("full_name"),
                "team": a.get("team"),
                "division": a.get("division"),
                "position": a.get("position"),
                "properties_count": a.get("properties"),
                "company_domain": a.get("company_domain"),
                "facebook": a.get("facebook_username"),
                "instagram": a.get("instagram_username"),
            }

            # Generar codigo unico
            codigo = f"AE-{ext_uid[:8]}"

            result = upsert_entity(
                provider="alterestate",
                entity_type="agent",
                external_data=a,
                dlab_table="entidades",
                match_config={
                    "external_id_key": "uid",
                    "external_uid_key": "email",
                    "natural_key": "email",
                    "natural_key_2": None,
                },
                field_mapping={
                    "codigo": lambda d: f"AE-{str(d.get('uid', d.get('id', '')))[:8]}",
                    "nombre": lambda d: d.get("first_name", ""),
                    "apellido": lambda d: d.get("last_name", ""),
                    "cedula": lambda d: f"AE-{str(d.get('uid', d.get('id', '')))}",
                    "email": lambda d: d.get("email", ""),
                    "telefono": lambda d: d.get("phone", ""),
                    "posicion": lambda d: d.get("position", ""),
                    "nivel": lambda d: _map_agent_role(d.get("role", "")),
                    "tipo": lambda d: "Externo",
                    "empresa": lambda d: d.get("company", "AlterEstate"),
                    "atributos_extra": lambda d: json.dumps(atributos_extra),
                    "fecha_ingreso": lambda d: d.get("created_at", datetime.now().strftime("%Y-%m-%d")),
                    "activo": lambda d: 1 if d.get("is_active", True) else 0,
                },
                defaults={
                    "nombre": nombre or "Agente",
                    "apellido": apellido or "AE",
                    "cedula": cedula_ae,
                    "nivel": _map_agent_role(a.get("role", "")),
                    "tipo": "Externo",
                    "empresa": a.get("company", "AlterEstate"),
                    "atributos_extra": json.dumps(atributos_extra),
                    "fecha_ingreso": datetime.now().strftime("%Y-%m-%d"),
                    "activo": 1,
                },
            )

            if result["action"] == "insert":
                stats["insertados"] += 1
            elif result["action"] == "update":
                stats["actualizados"] += 1
            elif result["action"] == "error":
                stats["errores"] += 1

        db.session.commit()
        log_info(SYNC_MODULE, f"Agentes sync: {stats}")
        return stats

    except Exception as e:
        db.session.rollback()
        log_error(SYNC_MODULE, f"Error en sync_agents: {e}", exc_info=True)
        return {"error": str(e)}


def sync_property_detail(client, slug: str) -> dict:
    """
    Descarga el detalle completo de una propiedad por slug.
    Enriquece el registro existente con campos detallados.
    
    Endpoints: GET /api/v1/properties/{slug}/
    """
    log_info(SYNC_MODULE, f"Sync detalle propiedad: {slug}")

    try:
        response = client.get(f"/api/v1/properties/{slug}/")
        prop_data = response.get("data", {})

        if not prop_data:
            return {"error": "Propiedad no encontrada"}

        # Buscar el proyecto existente por slug
        mapping = _find_mapping("alterestate", "property", str(prop_data.get("uid", slug)))

        if not mapping:
            # Si no existe, hacer sync completo de esta propiedad
            return sync_properties(client)

        internal_id = mapping["internal_id"]

        # Enriquecer atributos_extra con datos detallados
        existing_extra_raw = db.session.execute(
            text("SELECT atributos_extra FROM proyectos WHERE id = :id"),
            {"id": internal_id},
        ).scalar()

        existing_extra = {}
        if existing_extra_raw:
            try:
                existing_extra = json.loads(existing_extra_raw)
            except Exception:
                pass

        # Merge de datos detallados
        detailed_fields = [
            "bedrooms", "bathrooms", "area_m2", "lot_area", "floor",
            "year_built", "parking_spaces", "furnished",
            "description_long", "description_short",
            "video_url", "virtual_tour_url",
            "plans", "materials", " finishes",
        ]

        for field in detailed_fields:
            value = prop_data.get(field)
            if value is not None:
                existing_extra[field] = value

        existing_extra["ae_detail_synced_at"] = datetime.now().isoformat()
        existing_extra["ae_detail_raw"] = prop_data

        db.session.execute(
            text("UPDATE proyectos SET atributos_extra = :extra WHERE id = :id"),
            {"extra": json.dumps(existing_extra), "id": internal_id},
        )
        db.session.commit()

        log_info(SYNC_MODULE, f"Detalle propiedad {slug} actualizado (id={internal_id})")
        return {"success": True, "internal_id": internal_id, "slug": slug}

    except Exception as e:
        db.session.rollback()
        log_error(SYNC_MODULE, f"Error sync_property_detail {slug}: {e}", exc_info=True)
        return {"error": str(e)}


def sync_units(client, slug: str) -> dict:
    """
    Descarga unidades/inventario de una propiedad.
    
    Opcion A: Si AE tiene endpoint /api/v1/properties/{slug}/units/
    Opcion B: Almacenar como JSON dentro de atributos_extra.unidades en proyectos
    
    Retorna stats de la sincronizacion.
    """
    log_info(SYNC_MODULE, f"Sync unidades propiedad: {slug}")

    try:
        # Intentar endpoint de unidades
        try:
            response = client.get(f"/api/v1/properties/{slug}/units/")
            units_data = response.get("data", [])
        except AlterEstateError:
            # Si el endpoint no existe, intentar extraer del detail
            response = client.get(f"/api/v1/properties/{slug}/")
            prop_data = response.get("data", {})
            units_data = prop_data.get("units", [])

        if not units_data:
            return {"units": 0, "message": "No se encontraron unidades"}

        # Buscar el proyecto
        mapping = _find_mapping("alterestate", "property", slug)
        if not mapping:
            return {"error": f"No hay mapping para propiedad {slug}"}

        internal_id = mapping["internal_id"]

        # Actualizar atributos_extra con unidades
        existing_extra_raw = db.session.execute(
            text("SELECT atributos_extra FROM proyectos WHERE id = :id"),
            {"id": internal_id},
        ).scalar()

        existing_extra = {}
        if existing_extra_raw:
            try:
                existing_extra = json.loads(existing_extra_raw)
            except Exception:
                pass

        existing_extra["unidades"] = units_data
        existing_extra["unidades_count"] = len(units_data)
        existing_extra["ae_units_synced_at"] = datetime.now().isoformat()

        # Actualizar unidades_totales si difiere
        db.session.execute(
            text("UPDATE proyectos SET unidades_totales = :total, atributos_extra = :extra WHERE id = :id"),
            {"total": len(units_data), "extra": json.dumps(existing_extra), "id": internal_id},
        )
        db.session.commit()

        log_info(SYNC_MODULE, f"Unidades {slug}: {len(units_data)} unidades sync")
        return {"success": True, "units": len(units_data), "internal_id": internal_id}

    except Exception as e:
        db.session.rollback()
        log_error(SYNC_MODULE, f"Error sync_units {slug}: {e}", exc_info=True)
        return {"error": str(e)}


def send_lead(client, lead_data: dict) -> dict:
    """
    Envia un lead/prospecto a AlterEstate via POST.
    
    Payload esperado por AE:
        - name, email, phone, message
        - property_uid (opcional)
        - source (siempre 'dlab_crm')
    """
    log_info(SYNC_MODULE, f"Enviando lead a AE: {lead_data.get('email', 'N/A')}")

    try:
        payload = {
            "name": lead_data.get("nombre", "") + " " + lead_data.get("apellido", ""),
            "email": lead_data.get("email", ""),
            "phone": lead_data.get("telefono", ""),
            "message": lead_data.get("mensaje", "Lead generado desde DLAB CRM"),
            "property_uid": lead_data.get("property_uid"),
            "source": "dlab_crm",
            "metadata": {
                "dlab_cliente_id": lead_data.get("cliente_id"),
                "dlab_proyecto_id": lead_data.get("proyecto_id"),
                "dlab_usuario": lead_data.get("usuario"),
                "timestamp": datetime.now().isoformat(),
            },
        }

        response = client.post("/api/v1/leads/", data=payload)

        log_info(SYNC_MODULE, f"Lead enviado exitosamente: {response.get('status_code')}")
        return {
            "success": True,
            "ae_response": response.get("data"),
            "status_code": response.get("status_code"),
        }

    except AlterEstateError as e:
        log_error(SYNC_MODULE, f"Error enviando lead: {e.message}")
        return {"success": False, "error": e.message, "status_code": e.status_code}

    except Exception as e:
        log_error(SYNC_MODULE, f"Error inesperado enviando lead: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# C) ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

def sync_all(client=None, steps: List[str] = None) -> dict:
    """
    Orquesta la sincronizacion completa en el orden correcto:
    1. paises    (cat_paises)
    2. ciudades  (cat_ciudades)      ← depende de paises
    3. sectores  (cat_sectores)      ← depende de ciudades
    4. agentes   (entidades)         ← independiente
    5. propiedades (proyectos)       ← depende de sectores/contrapartes
    
    Args:
        client: instancia de AlterEstateClient. Si es None, crea uno desde DB config.
        steps: lista de pasos a ejecutar. Si None, ejecuta todos.
    
    Returns:
        dict con stats consolidadas de cada paso.
    """
    from app.core.alterestate_client import AlterEstateClient, load_provider_config_from_db

    if client is None:
        config = load_provider_config_from_db("alterestate")
        if not config.get("base_url"):
            return {"error": "Configuracion de AlterEstate no encontrada en DB"}
        client = AlterEstateClient(config)

    # Verificar conexion primero
    conn_test = client.test_connection()
    if not conn_test.get("connected"):
        return {"error": f"No se pudo conectar a AE: {conn_test.get('error')}"}

    all_steps = steps or ["countries", "cities", "sectors", "agents", "properties"]
    results = {}
    start_time = datetime.now()

    log_info(SYNC_MODULE, f"=== INICIO SYNC ALL === Pasos: {all_steps}")

    for step in all_steps:
        log_info(SYNC_MODULE, f"--- Ejecutando paso: {step} ---")
        try:
            if step == "countries":
                results["countries"] = sync_countries(client)
            elif step == "cities":
                results["cities"] = sync_cities(client)
            elif step == "sectors":
                results["sectors"] = sync_sectors(client)
            elif step == "agents":
                results["agents"] = sync_agents(client)
            elif step == "properties":
                results["properties"] = sync_properties(client)
            else:
                log_warn(SYNC_MODULE, f"Paso desconocido: {step}")
                results[step] = {"error": f"Paso desconocido: {step}"}
        except Exception as e:
            log_error(SYNC_MODULE, f"Error en paso {step}: {e}", exc_info=True)
            results[step] = {"error": str(e)}

    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(SYNC_MODULE, f"=== FIN SYNC ALL === Duracion: {elapsed:.1f}s")

    # Registrar en auditoria
    try:
        from flask import session
        user = session.get("usuario", {}).get("username", "system") if session else "system"
    except RuntimeError:
        user = "system"

    try:
        registrar_auditoria(
            0, user, "sync_alterestate", "ALTERESTATE",
            f"Sync completado en {elapsed:.1f}s. Pasos: {json.dumps(results, default=str)}"
        )
    except Exception:
        pass

    return {
        "success": True,
        "elapsed_seconds": round(elapsed, 1),
        "steps": results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# D) MAPPING / TRANSFORM HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _map_property_status(ae_status: str) -> str:
    """Mapea el estado de AE al etapa DLAB."""
    status_map = {
        "pre_construction": "En Planos",
        "under_construction": "En Construccion",
        "construction": "En Construccion",
        "delivered": "Entregado",
        "completed": "Entregado",
        "ready": "Entregado",
        "selling": "En Venta",
        "sold_out": "Agotado",
        "resale": "Reventa",
    }
    return status_map.get(ae_status.lower().replace(" ", "_"), "En Planos")


def _map_agent_role(ae_role: str) -> str:
    """Mapea el rol de AE al nivel DLAB."""
    role_map = {
        "agent": "Asesor interno - Inmobiliario",
        "advisor": "Asesor interno - Inmobiliario",
        "senior_agent": "Asesor interno - Inmobiliario",
        "manager": "Gerente de Ventas",
        "director": "Gerente de Ventas",
        "admin": "Admin",
    }
    return role_map.get(ae_role.lower().replace(" ", "_"), "Asesor interno - Inmobiliario")


def _resolve_pais_id(ae_country_code: str) -> Optional[int]:
    """
    Resuelve el pais_id desde cat_paises buscando por codigo (ID de AE).
    """
    try:
        row = db.session.execute(
            text("SELECT id FROM cat_paises WHERE codigo = :code LIMIT 1"),
            {"code": ae_country_code}
        ).mappings().first()
        return row["id"] if row else None
    except Exception as e:
        logger.error(f"[SYNC] Error resolviendo pais para code {ae_country_code}: {e}")
        return None


def _resolve_contraparte_from_developer(property_data: dict) -> Optional[int]:
    """
    Resuelve el contraparte_id (constructora) desde el developer de la propiedad.
    Si el developer no existe en contrapartes, lo crea.
    """
    developer = property_data.get("developer")
    if not developer or not isinstance(developer, dict):
        return None

    dev_name = developer.get("name", "")
    if not dev_name:
        return None

    try:
        # Buscar si ya existe
        existing = db.session.execute(
            text("SELECT id FROM contrapartes WHERE nombre = :name AND activo = 1"),
            {"name": dev_name},
        ).scalar()

        if existing:
            return existing

        # Crear nueva contraparte
        db.session.execute(
            text(
                "INSERT INTO contrapartes (nombre, rnc, telefono, contacto, activo, atributos_extra) "
                "VALUES (:nombre, '', '', '', 1, :extra)"
            ),
            {
                "nombre": dev_name,
                "extra": json.dumps({
                    "ae_developer_id": developer.get("id"),
                    "ae_developer_uid": developer.get("uid"),
                    "fuente": "alterestate",
                }),
            },
        )
        db.session.flush()
        new_id = db.session.execute(text("SELECT MAX(id) FROM contrapartes")).scalar()
        log_info(SYNC_MODULE, f"Contraparte creada desde AE developer: {dev_name} (id={new_id})")
        return new_id

    except Exception as e:
        log_error(SYNC_MODULE, f"Error resolviendo contraparte para developer {dev_name}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# E) STATS / REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

def get_sync_stats() -> dict:
    """Retorna estadisticas de la ultima sincronizacion."""
    try:
        # Contar mappings por tipo
        rows = db.session.execute(
            text(
                "SELECT entity_type, COUNT(*) as cnt, "
                "MAX(last_synced_at) as last_sync "
                "FROM api_entity_mapping "
                "WHERE provider = 'alterestate' "
                "GROUP BY entity_type"
            )
        ).mappings().all()

        stats = {}
        for row in rows:
            stats[row["entity_type"]] = {
                "count": row["cnt"],
                "last_sync": row["last_sync"],
            }

        # Total de mapeos
        total = db.session.execute(
            text("SELECT COUNT(*) FROM api_entity_mapping WHERE provider = 'alterestate'")
        ).scalar() or 0

        # Ultimo sync completo
        last_full_sync = db.session.execute(
            text(
                "SELECT MAX(fecha) FROM auditoria "
                "WHERE modulo = 'ALTERESTATE' AND accion = 'sync_alterestate'"
            )
        ).scalar()

        return {
            "total_mappings": total,
            "by_type": stats,
            "last_full_sync": last_full_sync,
        }

    except Exception as e:
        return {"error": str(e)}


def get_mapped_entities(entity_type: str = None, limit: int = 50) -> List[dict]:
    """Retorna los mappings existentes, opcionalmente filtrado por tipo."""
    try:
        query = (
            "SELECT id, provider, entity_type, external_id, external_uid, "
            "internal_id, internal_table, last_synced_at, created_at "
            "FROM api_entity_mapping WHERE provider = 'alterestate'"
        )
        params = {}

        if entity_type:
            query += " AND entity_type = :et"
            params["et"] = entity_type

        query += " ORDER BY last_synced_at DESC LIMIT :limit"
        params["limit"] = limit

        rows = db.session.execute(text(query), params).mappings().all()
        return [dict(r) for r in rows]

    except Exception as e:
        return [{"error": str(e)}]
