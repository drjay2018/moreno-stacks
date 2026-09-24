"""
alterestate_client.py — Cliente HTTP para la API de AlterEstate.
Gestiona autenticacion por Token, rate limiting, timeouts, reintentos y manejo de errores.

Patron de uso:
    client = AlterEstateClient(provider_config)
    data = client.get('/properties', params={'page': 1})
    result = client.post('/leads', payload={...})
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Constantes ────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 30          # segundos por request
MAX_RETRIES = 3               # reintentos en errores transitorios
RETRY_BACKOFF_BASE = 2.0      # exponential backoff base
RATE_LIMIT_RPS = 2.0          # maximo requests por segundo
RATE_LIMIT_WINDOW = 1.0       # ventana de rate limiting en segundos
MAX_PAGE_SIZE = 100           # page size maximo de AE

# Errores HTTP que justifican reintentos (transitorios)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class AlterEstateError(Exception):
    """Error base para el cliente AlterEstate."""

    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(self.message)


class AlterEstateRateLimitError(AlterEstateError):
    """Error de rate limiting (HTTP 429)."""
    pass


class AlterEstateAuthError(AlterEstateError):
    """Error de autenticacion (HTTP 401/403)."""
    pass


class AlterEstateClient:
    """
    Cliente HTTP para la API de AlterEstate.
    
    Soporta:
    - Endpoints publicos (sin auth): GET properties, countries, cities, sectors
    - Endpoints protegidos (Token auth): POST leads, syncs autenticados
    - Rate limiting por ventana temporal
    - Reintentos con exponential backoff
    - Timeout configurable
    - Logging de todas las requests/responses
    """

    def __init__(self, provider_config: Dict[str, str] = None):
        """
        Inicializa el cliente con configuracion del provider.
        
        Args:
            provider_config: dict con keys:
                - base_url: URL base de la API (ej: 'https://api.alterestate.com')
                - api_token: Token de autenticacion (opcional para endpoints publicos)
                - timeout: Timeout en segundos (default: 30)
                - rate_limit_rps: Maximo requests/segundo (default: 2.0)
        """
        self._config = provider_config or {}
        self._base_url = self._config.get("base_url", "").rstrip("/")
        self._api_token = self._config.get("api_token", "")
        self._timeout = int(self._config.get("timeout", DEFAULT_TIMEOUT))
        self._rate_limit_rps = float(self._config.get("rate_limit_rps", RATE_LIMIT_RPS))

        # Estado del rate limiter (sliding window)
        self._request_timestamps: List[float] = []
        self._rate_limit_window = RATE_LIMIT_WINDOW

        if not self._base_url:
            logger.warning("[AE_CLIENT] base_url no configurada. El cliente no funcionara correctamente.")

    # ─── Rate Limiter ──────────────────────────────────────────────────────────

    def _wait_for_rate_limit(self):
        """
        Espera si es necesario para respetar el rate limit.
        Usa sliding window: si hay mas requests de las permitidas en la ventana, espera.
        """
        now = time.time()
        # Limpiar timestamps fuera de la ventana
        self._request_timestamps = [
            ts for ts in self._request_timestamps
            if now - ts < self._rate_limit_window
        ]
        if len(self._request_timestamps) >= self._rate_limit_rps:
            # Calcular cuanto esperar
            oldest = self._request_timestamps[0]
            wait_time = self._rate_limit_window - (now - oldest)
            if wait_time > 0:
                logger.debug(f"[AE_CLIENT] Rate limit: esperando {wait_time:.2f}s")
                time.sleep(wait_time)
        self._request_timestamps.append(time.time())

    # ─── Construccion de requests ─────────────────────────────────────────────

    def _build_url(self, path: str, params: Dict[str, Any] = None) -> str:
        """Construye la URL completa con query params."""
        url = f"{self._base_url}{path}"
        if params:
            # Filtrar None values
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                url += "?" + urllib.parse.urlencode(clean_params)
        return url

    def _build_headers(self, include_auth: bool = False, auth_type: str = "auto") -> Dict[str, str]:
        """
        Construye los headers HTTP.
        
        auth_type:
            - "auto": usa Authorization para GET protegidos, aetoken para publicos
            - "aetoken": header aetoken (para endpoints publicos: properties, agents)
            - "bearer": header Authorization: Token (para leads, etc.)
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DLAB-CRM-Integration/1.0",
        }
        if include_auth and self._api_token:
            if auth_type == "aetoken":
                headers["aetoken"] = self._api_token
            elif auth_type == "bearer":
                headers["Authorization"] = f"Token {self._api_token}"
            else:
                # Auto: usar aetoken para lectura, bearer para escritura
                headers["aetoken"] = self._api_token
                headers["Authorization"] = f"Token {self._api_token}"
        return headers

    # ─── Ejecucion de requests ────────────────────────────────────────────────

    def _execute_request(
        self,
        method: str,
        path: str,
        params: Dict[str, Any] = None,
        data: dict = None,
        include_auth: bool = False,
        auth_type: str = "auto",
        retries: int = MAX_RETRIES,
    ) -> Dict[str, Any]:
        """
        Ejecuta un request HTTP con reintentos, rate limiting y manejo de errores.
        """
        url = self._build_url(path, params)
        headers = self._build_headers(include_auth, auth_type=auth_type)
        body_bytes = json.dumps(data).encode("utf-8") if data else None

        last_error = None
        for attempt in range(1, retries + 1):
            self._wait_for_rate_limit()
            start_time = time.time()

            try:
                req = urllib.request.Request(
                    url,
                    data=body_bytes,
                    headers=headers,
                    method=method,
                )

                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    response_body = resp.read().decode("utf-8")
                    status_code = resp.status

                    # Parsear JSON
                    try:
                        response_data = json.loads(response_body) if response_body else {}
                    except json.JSONDecodeError:
                        response_data = {"raw": response_body}

                    logger.info(
                        f"[AE_CLIENT] {method} {path} → {status_code} ({elapsed_ms}ms) "
                        f"[attempt {attempt}/{retries}]"
                    )

                    return {
                        "success": True,
                        "data": response_data,
                        "status_code": status_code,
                        "elapsed_ms": elapsed_ms,
                        "headers": dict(resp.headers),
                    }

            except urllib.error.HTTPError as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                status_code = e.code
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    pass

                logger.warning(
                    f"[AE_CLIENT] {method} {path} → HTTP {status_code} ({elapsed_ms}ms) "
                    f"[attempt {attempt}/{retries}] body={error_body[:200]}"
                )

                # Errores de autenticacion → no reintentar
                if status_code in (401, 403):
                    raise AlterEstateAuthError(
                        f"Error de autenticacion HTTP {status_code}: {error_body[:200]}",
                        status_code=status_code,
                        response_data={"body": error_body},
                    )

                # Rate limiting → esperar y reintentar
                if status_code == 429:
                    retry_after = int(e.headers.get("Retry-After", 5)) if hasattr(e, 'headers') else 5
                    if attempt < retries:
                        logger.info(f"[AE_CLIENT] Rate limited, esperando {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    raise AlterEstateRateLimitError(
                        f"Rate limit persistente tras {retries} reintentos",
                        status_code=429,
                    )

                # Errores transitorios → reintentar
                if status_code in RETRYABLE_STATUS_CODES and attempt < retries:
                    backoff = RETRY_BACKOFF_BASE ** attempt
                    logger.info(f"[AE_CLIENT] Retry en {backoff:.1f}s (HTTP {status_code})")
                    time.sleep(backoff)
                    continue

                # Error fatal
                raise AlterEstateError(
                    f"HTTP {status_code}: {error_body[:200]}",
                    status_code=status_code,
                    response_data={"body": error_body},
                )

            except urllib.error.URLError as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                last_error = str(e.reason) if hasattr(e, 'reason') else str(e)
                logger.warning(
                    f"[AE_CLIENT] {method} {path} → URL Error: {last_error} ({elapsed_ms}ms) "
                    f"[attempt {attempt}/{retries}]"
                )
                if attempt < retries:
                    backoff = RETRY_BACKOFF_BASE ** attempt
                    time.sleep(backoff)
                    continue

            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                last_error = str(e)
                logger.error(
                    f"[AE_CLIENT] {method} {path} → Error inesperado: {last_error} ({elapsed_ms}ms)",
                    exc_info=True,
                )
                if attempt < retries:
                    backoff = RETRY_BACKOFF_BASE ** attempt
                    time.sleep(backoff)
                    continue

        # Agotados todos los reintentos
        raise AlterEstateError(
            f"Agotados {retries} reintentos para {method} {path}. Ultimo error: {last_error}"
        )

    # ─── API Publica (sin auth) ───────────────────────────────────────────────

    def get_public(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """GET a endpoint publico (sin token)."""
        return self._execute_request("GET", path, params=params, include_auth=False)

    def get_public_with_token(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """GET a endpoint publico que requiere aetoken (properties, agents)."""
        return self._execute_request("GET", path, params=params, include_auth=True, auth_type="aetoken")

    def get_paginated_public(
        self, path: str, params: Dict[str, Any] = None, page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Descarga todos los registros de un endpoint paginado publico (sin auth).
        """
        all_results = []
        page = 1
        current_params = dict(params or {})

        while True:
            current_params["page"] = page
            current_params["page_size"] = min(page_size, MAX_PAGE_SIZE)

            response = self.get_public(path, params=current_params)
            data = response.get("data", {})

            results = []
            if isinstance(data, list):
                results = data
            elif isinstance(data, dict):
                results = data.get("results", data.get("data", data.get("items", [])))

            if not results:
                break

            all_results.extend(results)

            if isinstance(data, dict):
                next_url = data.get("next")
                if not next_url:
                    total_pages = data.get("total_pages", data.get("pages", 1))
                    if page >= total_pages:
                        break
                page += 1
            else:
                break

            if page > 500:
                logger.warning(f"[AE_CLIENT] Safety break: mas de 500 paginas en {path}")
                break

        return all_results

    def get_paginated_public_with_token(
        self, path: str, params: Dict[str, Any] = None, page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Descarga todos los registros de un endpoint paginado publico con aetoken.
        Usa para properties, agents, etc.
        """
        all_results = []
        page = 1
        current_params = dict(params or {})

        while True:
            current_params["page"] = page
            current_params["page_size"] = min(page_size, MAX_PAGE_SIZE)

            response = self.get_public_with_token(path, params=current_params)
            data = response.get("data", {})

            results = []
            if isinstance(data, list):
                results = data
            elif isinstance(data, dict):
                results = data.get("results", data.get("data", data.get("items", [])))

            if not results:
                break

            all_results.extend(results)

            if isinstance(data, dict):
                next_url = data.get("next")
                if not next_url:
                    total_pages = data.get("total_pages", data.get("pages", 1))
                    if page >= total_pages:
                        break
                page += 1
            else:
                break

            if page > 500:
                logger.warning(f"[AE_CLIENT] Safety break: mas de 500 paginas en {path}")
                break

        return all_results

    # ─── API Protegida (con Token) ────────────────────────────────────────────

    def get(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """GET a endpoint protegido (con token)."""
        return self._execute_request("GET", path, params=params, include_auth=True, auth_type="bearer")

    def post(self, path: str, data: dict = None) -> Dict[str, Any]:
        """POST a endpoint protegido."""
        return self._execute_request("POST", path, data=data, include_auth=True, auth_type="bearer")

    def put(self, path: str, data: dict = None) -> Dict[str, Any]:
        """PUT a endpoint protegido."""
        return self._execute_request("PUT", path, data=data, include_auth=True)

    def get_paginated(
        self, path: str, params: Dict[str, Any] = None, page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """Descarga todos los registros de un endpoint paginado protegido."""
        all_results = []
        page = 1
        current_params = dict(params or {})

        while True:
            current_params["page"] = page
            current_params["page_size"] = min(page_size, MAX_PAGE_SIZE)

            response = self.get(path, params=current_params)
            data = response.get("data", {})

            results = []
            if isinstance(data, list):
                results = data
            elif isinstance(data, dict):
                results = data.get("results", data.get("data", data.get("items", [])))

            if not results:
                break

            all_results.extend(results)

            if isinstance(data, dict):
                next_url = data.get("next")
                if not next_url:
                    total_pages = data.get("total_pages", data.get("pages", 1))
                    if page >= total_pages:
                        break
                page += 1
            else:
                break

            if page > 500:
                logger.warning(f"[AE_CLIENT] Safety break: mas de 500 paginas en {path}")
                break

        return all_results

    # ─── Utilidades ────────────────────────────────────────────────────────────

    def test_connection(self) -> Dict[str, Any]:
        """Verifica conectividad con la API usando cities (endpoint publico que funciona)."""
        try:
            resp = self.get_public("/api/v1/cities/", params={"country": 149})
            return {
                "connected": True,
                "status_code": resp.get("status_code"),
                "elapsed_ms": resp.get("elapsed_ms"),
                "base_url": self._base_url,
            }
        except AlterEstateError as e:
            return {
                "connected": False,
                "error": e.message,
                "status_code": e.status_code,
                "base_url": self._base_url,
            }

    def test_auth(self) -> Dict[str, Any]:
        """Verifica que el token funcione usando leads endpoint (POST test)."""
        if not self._api_token:
            return {"authenticated": False, "error": "No hay token configurado"}
        try:
            # Usar un GET a cities con aetoken para verificar auth
            resp = self.get_public_with_token("/api/v1/properties/filter/", params={"page_size": 1})
            # Si devuelve 200, auth funciona
            return {
                "authenticated": True,
                "status_code": resp.get("status_code"),
                "elapsed_ms": resp.get("elapsed_ms"),
            }
        except AlterEstateAuthError as e:
            return {
                "authenticated": False,
                "error": e.message,
                "status_code": e.status_code,
            }
        except AlterEstateError as e:
            # 404 puede significar que el endpoint no existe pero auth funciona
            if e.status_code == 404:
                return {
                    "authenticated": True,
                    "status_code": 404,
                    "note": "Token aceptado pero endpoint no encontrado (puede ser normal)",
                }
            return {
                "authenticated": False,
                "error": e.message,
            }


# ─── Helper: cargar configuracion desde DB ──────────────────────────────────────

def load_provider_config_from_db(provider: str = "alterestate") -> Dict[str, str]:
    """
    Carga la configuracion del provider desde app_config.
    Busca claves: alterestate_base_url, alterestate_api_token, etc.
    Descifra el token si esta cifrado.
    """
    from app.extensions import db
    from sqlalchemy import text
    from app.core.crypto import ensure_decrypted

    config = {}
    prefix = f"{provider}_"

    try:
        rows = db.session.execute(
            text("SELECT clave, valor FROM app_config WHERE clave LIKE :prefix"),
            {"prefix": f"{prefix}%"}
        ).mappings().all()

        for row in rows:
            key = row["clave"].replace(prefix, "")
            valor = row["valor"]
            # Descifrar tokens y secrets
            if "token" in key or "secret" in key:
                valor = ensure_decrypted(valor or "")
            config[key] = valor

    except Exception as e:
        logger.error(f"[AE_CLIENT] Error cargando config desde DB: {e}")

    return config


def save_provider_config_to_db(config: Dict[str, str], provider: str = "alterestate"):
    """
    Guarda la configuracion del provider en app_config.
    Cifra tokens y secrets antes de guardar.
    """
    from app.extensions import db
    from sqlalchemy import text
    from app.core.crypto import ensure_encrypted

    prefix = f"{provider}_"

    for key, valor in config.items():
        db_key = f"{prefix}{key}"
        # Cifrar tokens y secrets
        if "token" in key or "secret" in key:
            valor = ensure_encrypted(valor or "")

        try:
            db.session.execute(
                text(
                    "INSERT INTO app_config (clave, valor) VALUES (:k, :v) "
                    "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"
                ),
                {"k": db_key, "v": valor}
            )
        except Exception as e:
            logger.error(f"[AE_CLIENT] Error guardando config {db_key}: {e}")

    db.session.commit()
