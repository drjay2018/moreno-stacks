"""
alterestate_api.py — Endpoint API para gestionar la integracion con AlterEstate.

Endpoints:
    GET  /api/alterestate/status        — Estado de la conexion y configuracion
    GET  /api/alterestate/config        — Obtener configuracion actual
    POST /api/alterestate/config        — Guardar configuracion
    POST /api/alterestate/test          — Probar conexion y auth
    POST /api/alterestate/sync          — Ejecutar sync completo
    POST /api/alterestate/sync/<entity> — Sync de entidad especifica
    GET  /api/alterestate/stats         — Estadisticas de sincronizacion
    GET  /api/alterestate/mappings      — Listar mappings existentes
    POST /api/alterestate/send-lead     — Enviar lead a AE
"""

import json
from flask import Blueprint, jsonify, request
from sqlalchemy import text

from app.extensions import db
from app.core.auditoria import registrar_auditoria
from app.core.auth_middleware import requiere_rol
from app.core.logger import log_info, log_error

alterestate_api_bp = Blueprint("alterestate_api", __name__, url_prefix="/api/alterestate")


@alterestate_api_bp.route("/status", methods=["GET"])
@requiere_rol("Admin")
def get_status():
    """Estado de la integracion AlterEstate."""
    try:
        from app.core.alterestate_sync import get_sync_stats

        # Verificar si hay configuracion
        config_rows = db.session.execute(
            text("SELECT clave FROM app_config WHERE clave LIKE 'alterestate_%'")
        ).fetchall()

        has_config = len(config_rows) > 0
        stats = get_sync_stats()

        # ─── Conteos directos de tablas DLAB ────────────────────────────────────
        counts = {}
        for table, key in [
            ("proyectos", "proyectos"),
            ("entidades", "entidades"),
            ("cat_paises", "paises"),
            ("cat_ciudades", "ciudades"),
            ("cat_sectores", "sectores"),
        ]:
            try:
                counts[key] = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).scalar() or 0
            except Exception:
                counts[key] = 0

        # ─── Ultimo sync por entidad (desde auditoria) ─────────────────────────
        last_syncs = {}
        try:
            rows = db.session.execute(
                text(
                    "SELECT accion, MAX(fecha) as ultima "
                    "FROM auditoria WHERE modulo = 'ALTERESTATE' "
                    "GROUP BY accion"
                )
            ).fetchall()
            for r in rows:
                last_syncs[r[0]] = r[1]
        except Exception:
            pass

        # ─── Freshness: cuanto tiempo paso desde el ultimo sync ─────────────────
        from datetime import datetime
        freshness = {}
        for entity_type, info in stats.get("by_type", {}).items():
            last = info.get("last_sync")
            if last:
                try:
                    if isinstance(last, str):
                        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    else:
                        last_dt = last
                    delta = datetime.now() - last_dt.replace(tzinfo=None)
                    hours = delta.total_seconds() / 3600
                    if hours < 1:
                        freshness[entity_type] = {"status": "reciente", "text": f"Hace {int(delta.total_seconds()/60)}min", "hours": round(hours, 1)}
                    elif hours < 24:
                        freshness[entity_type] = {"status": "ok", "text": f"Hace {int(hours)}h", "hours": round(hours, 1)}
                    elif hours < 168:
                        freshness[entity_type] = {"status": "antiguo", "text": f"Hace {int(hours/24)}d", "hours": round(hours, 1)}
                    else:
                        freshness[entity_type] = {"status": "muy_antiguo", "text": f"Hace {int(hours/24)}d", "hours": round(hours, 1)}
                except Exception:
                    freshness[entity_type] = {"status": "desconocido", "text": "Sin fecha", "hours": None}

        return jsonify({
            "success": True,
            "has_config": has_config,
            "config_keys": [r[0] for r in config_rows],
            "sync_stats": stats,
            "table_counts": counts,
            "last_syncs": last_syncs,
            "freshness": freshness,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/config", methods=["GET"])
@requiere_rol("Admin")
def get_config():
    """Obtiene la configuracion de AlterEstate (sin exponer tokens)."""
    try:
        from app.core.alterestate_client import load_provider_config_from_db

        config = load_provider_config_from_db("alterestate")

        # Enmascarar tokens
        safe_config = {}
        for k, v in config.items():
            if "token" in k or "secret" in k:
                safe_config[k] = f"{'*' * 8}{v[-4:]}" if v and len(v) > 4 else "(no configurado)"
            else:
                safe_config[k] = v

        return jsonify({"success": True, "config": safe_config})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/config", methods=["POST"])
@requiere_rol("Admin")
def save_config():
    """Guarda la configuracion de AlterEstate."""
    try:
        data = request.get_json() or {}

        required_fields = ["base_url"]
        for field in required_fields:
            if not data.get(field):
                return jsonify({"success": False, "error": f"Campo requerido: {field}"}), 400

        from app.core.alterestate_client import save_provider_config_to_db

        save_provider_config_to_db(data, "alterestate")

        registrar_auditoria(1, "admin", "configurar_alterestate", "ALTERESTATE",
                           "Configuracion de AlterEstate actualizada")

        return jsonify({"success": True, "message": "Configuracion guardada correctamente."})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/test", methods=["POST"])
@requiere_rol("Admin")
def test_connection():
    """Prueba la conexion y autenticacion con AlterEstate."""
    try:
        from app.core.alterestate_client import AlterEstateClient, load_provider_config_from_db

        config = load_provider_config_from_db("alterestate")
        if not config.get("base_url"):
            return jsonify({"success": False, "error": "No hay configuracion de base_url"}), 400

        client = AlterEstateClient(config)

        conn_result = client.test_connection()
        auth_result = client.test_auth()

        return jsonify({
            "success": True,
            "connection": conn_result,
            "authentication": auth_result,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/sync", methods=["POST"])
@requiere_rol("Admin")
def run_sync():
    """Ejecuta la sincronizacion completa con AlterEstate."""
    try:
        from app.core.alterestate_client import AlterEstateClient, load_provider_config_from_db
        from app.core.alterestate_sync import sync_all

        data = request.get_json() or {}
        steps = data.get("steps")  # Lista de pasos opcionales

        config = load_provider_config_from_db("alterestate")
        if not config.get("base_url"):
            return jsonify({"success": False, "error": "No hay configuracion de AlterEstate"}), 400

        client = AlterEstateClient(config)
        result = sync_all(client=client, steps=steps)

        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 500

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/sync/<entity_type>", methods=["POST"])
@requiere_rol("Admin")
def run_sync_entity(entity_type):
    """Ejecuta sync de una entidad especifica."""
    valid_entities = {
        "countries": "sync_countries",
        "cities": "sync_cities",
        "sectors": "sync_sectors",
        "properties": "sync_properties",
        "agents": "sync_agents",
    }

    if entity_type not in valid_entities:
        return jsonify({
            "success": False,
            "error": f"Entidad no valida. Opciones: {', '.join(valid_entities.keys())}"
        }), 400

    try:
        from app.core.alterestate_client import AlterEstateClient, load_provider_config_from_db
        from app.core.alterestate_sync import sync_all

        config = load_provider_config_from_db("alterestate")
        if not config.get("base_url"):
            return jsonify({"success": False, "error": "No hay configuracion de AlterEstate"}), 400

        client = AlterEstateClient(config)
        result = sync_all(client=client, steps=[entity_type])

        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 500

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/stats", methods=["GET"])
@requiere_rol("Admin")
def get_stats():
    """Estadisticas de sincronizacion."""
    try:
        from app.core.alterestate_sync import get_sync_stats

        stats = get_sync_stats()
        return jsonify({"success": True, "stats": stats})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/mappings", methods=["GET"])
@requiere_rol("Admin")
def list_mappings():
    """Lista los mappings existentes."""
    try:
        from app.core.alterestate_sync import get_mapped_entities

        entity_type = request.args.get("entity_type")
        try:
            limit = int(request.args.get("limit", 50))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "El parámetro 'limit' debe ser un número entero."}), 400

        mappings = get_mapped_entities(entity_type=entity_type, limit=limit)
        return jsonify({"success": True, "mappings": mappings, "count": len(mappings)})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/send-lead", methods=["POST"])
@requiere_rol("Admin")
def send_lead():
    """Envia un lead/prospecto a AlterEstate."""
    try:
        from app.core.alterestate_client import AlterEstateClient, load_provider_config_from_db
        from app.core.alterestate_sync import send_lead as ae_send_lead

        data = request.get_json() or {}

        required = ["nombre", "apellido", "email"]
        for field in required:
            if not data.get(field):
                return jsonify({"success": False, "error": f"Campo requerido: {field}"}), 400

        config = load_provider_config_from_db("alterestate")
        if not config.get("base_url"):
            return jsonify({"success": False, "error": "No hay configuracion de AlterEstate"}), 400

        client = AlterEstateClient(config)
        result = ae_send_lead(client, data)

        if result.get("success"):
            registrar_auditoria(1, "admin", "enviar_lead_ae", "ALTERESTATE",
                               f"Lead enviado: {data.get('email')}")
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/properties", methods=["GET"])
@requiere_rol("Admin")
def list_properties():
    """Lista propiedades sincronizadas desde AlterEstate (de la tabla proyectos)."""
    try:
        try:
            limit = int(request.args.get("limit", 200))
            offset = int(request.args.get("offset", 0))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Los parámetros 'limit' y 'offset' deben ser números enteros."}), 400

        rows = db.session.execute(
            text(
                "SELECT p.id, p.nombre, p.tipo_inmueble, p.municipio, p.sector, "
                "p.precio_min, p.precio_max, p.etapa, p.activo, "
                "p.atributos_extra, "
                "c.nombre as contraparte_nombre "
                "FROM proyectos p "
                "LEFT JOIN contrapartes c ON p.contraparte_id = c.id "
                "ORDER BY p.nombre "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset}
        ).mappings().all()

        total = db.session.execute(text("SELECT COUNT(*) FROM proyectos")).scalar() or 0

        import json as _json
        properties = []
        for r in rows:
            extra = {}
            if r["atributos_extra"]:
                try:
                    extra = _json.loads(r["atributos_extra"]) if isinstance(r["atributos_extra"], str) else r["atributos_extra"]
                except Exception:
                    pass
            properties.append({
                "id": r["id"],
                "nombre": r["nombre"],
                "tipo_inmueble": r["tipo_inmueble"],
                "municipio": r["municipio"],
                "sector": r["sector"],
                "precio_min": float(r["precio_min"]) if r["precio_min"] else None,
                "precio_max": float(r["precio_max"]) if r["precio_max"] else None,
                "etapa": r["etapa"],
                "activo": bool(r["activo"]),
                "contraparte_nombre": r["contraparte_nombre"],
                "ae_created_at": extra.get("ae_created_at"),
                "ae_updated_at": extra.get("ae_updated_at"),
            })

        return jsonify({"success": True, "properties": properties, "total": total})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/agents-list", methods=["GET"])
@requiere_rol("Admin")
def list_agents():
    """Lista agentes sincronizados desde AlterEstate (de la tabla entidades)."""
    try:
        try:
            limit = int(request.args.get("limit", 200))
            offset = int(request.args.get("offset", 0))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Los parámetros 'limit' y 'offset' deben ser números enteros."}), 400

        rows = db.session.execute(
            text(
                "SELECT e.id, e.nombre, e.apellido, e.email, e.telefono, "
                "e.posicion, e.empresa, e.activo, e.fecha_ingreso "
                "FROM entidades e "
                "WHERE e.tipo = 'Agente' OR e.empresa LIKE '%ALTERESTATE%' "
                "ORDER BY e.nombre "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset}
        ).mappings().all()

        total = db.session.execute(
            text("SELECT COUNT(*) FROM entidades WHERE tipo = 'Agente' OR empresa LIKE '%ALTERESTATE%'")
        ).scalar() or 0

        agents = []
        for r in rows:
            agents.append({
                "id": r["id"],
                "nombre": f"{r['nombre']} {r['apellido']}",
                "email": r["email"],
                "telefono": r["telefono"],
                "posicion": r["posicion"],
                "empresa": r["empresa"],
                "activo": bool(r["activo"]),
                "fecha_ingreso": str(r["fecha_ingreso"]) if r["fecha_ingreso"] else None,
            })

        return jsonify({"success": True, "agents": agents, "total": total})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@alterestate_api_bp.route("/imported-data", methods=["GET"])
@requiere_rol("Admin")
def get_imported_data():
    """Preview de las 10 ultimas filas de cada tabla importada desde AE."""
    try:
        tables = {
            "paises": {
                "sql": "SELECT codigo AS ae_id, nombre, codigo_iso AS iso, telefono_codigo AS telefono, activo FROM cat_paises ORDER BY id",
                "columns": ["AE_ID", "Nombre", "ISO", "Telefono", "Activo"],
            },
            "ciudades": {
                "sql": "SELECT ae_city_id AS ae_id, nombre, pais_id, provincia, activo FROM cat_ciudades ORDER BY id DESC LIMIT 10",
                "columns": ["AE_City_ID", "Nombre", "Pais_ID", "Provincia", "Activo"],
            },
            "sectores": {
                "sql": "SELECT ae_sector_id AS ae_id, nombre, ciudad_id, ciudad_nombre, activo FROM cat_sectores ORDER BY id DESC LIMIT 10",
                "columns": ["AE_Sector_ID", "Nombre", "Ciudad_ID", "Ciudad", "Activo"],
            },
        }

        result = {}
        for key, cfg in tables.items():
            rows = db.session.execute(text(cfg["sql"])).mappings().all()
            # Get total count (without LIMIT)
            count_sql = f"SELECT COUNT(*) FROM ({cfg['sql'].split('ORDER BY')[0].strip()})"
            total = db.session.execute(text(count_sql)).scalar() or 0
            result[key] = {
                "columns": cfg["columns"],
                "rows": [dict(r) for r in rows],
                "total": total,
            }

        return jsonify({"success": True, "data": result})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
