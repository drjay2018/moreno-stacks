"""
clarodom_client.py — Cliente HTTP para la API de ClaroDom.
Gestiona autenticacion por Bearer token (configurable), rate limiting, timeouts,
reintentos y manejo de errores tipificado.

ClaroDom expone un esquema propio de API; este cliente es generico:
    client = ClaroDomClient(provider_config)
    result = client.get('/algo')
    result = client.post('/algo', payload={...})

Configuracion soportada (claves en app_config con prefijo clarodom_):
    - base_url:     URL base de la API (ej: 'https://appgestionnegocio.claro.com.do')
    - api_token:    Token de autenticacion (JWT), cifrado al guardarse
    - auth_scheme:  Formato del header Authorization: 'bearer', 'token' o 'raw' (default: bearer)
    - test_path:    Ruta usada para probar conexion/auth (default: '/')
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Constantes ────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 30          # segundos por request
MAX_RETRIES = 3               # reintentos en errores transitorios
RETRY_BACKOFF_BASE = 2.0      # exponential backoff base
RATE_LIMIT_RPS = 2.0          # maximo requests por segundo
RATE_LIMIT_WINDOW = 1.0       # ventana de rate limiting en segundos

# Errores HTTP que justifican reintentos (transitorios)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class ClaroDomError(Exception):
    """Error base para el cliente ClaroDom."""

    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(self.message)


class ClaroDomRateLimitError(ClaroDomError):
    """Error de rate limiting (HTTP 429)."""
    pass


class ClaroDomAuthError(ClaroDomError):
    """Error de autenticacion (HTTP 401/403)."""
    pass


class ClaroDomClient:
    """
    Cliente HTTP generico para la API de ClaroDom.

    Soporta:
    - Endpoints publicos y protegidos (Bearer token)
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
                - base_url: URL base de la API (ej: 'https://api.clarodom.example')
                - api_token: Token de autenticacion (opcional)
                - test_path: Ruta para probar conexion/auth (default: '/')
                - timeout: Timeout en segundos (default: 30)
                - rate_limit_rps: Maximo requests/segundo (default: 2.0)
        """
        self._config = provider_config or {}
        self._base_url = self._config.get("base_url", "").rstrip("/")
        self._api_token = self._config.get("api_token", "")
        self._test_path = self._config.get("test_path") or "/"
        self._auth_scheme = (self._config.get("auth_scheme") or "bearer").strip().lower()
        self._timeout = int(self._config.get("timeout", DEFAULT_TIMEOUT))
        self._rate_limit_rps = float(self._config.get("rate_limit_rps", RATE_LIMIT_RPS))

        # Estado del rate limiter (sliding window)
        self._request_timestamps: List[float] = []
        self._rate_limit_window = RATE_LIMIT_WINDOW

        if not self._base_url:
            logger.warning("[CD_CLIENT] base_url no configurada. El cliente no funcionara correctamente.")

    # ─── Rate Limiter ──────────────────────────────────────────────────────────

    def _wait_for_rate_limit(self):
        """Espera si es necesario para respetar el rate limit (sliding window)."""
        now = time.time()
        self._request_timestamps = [
            ts for ts in self._request_timestamps
            if now - ts < self._rate_limit_window
        ]
        if len(self._request_timestamps) >= self._rate_limit_rps:
            oldest = self._request_timestamps[0]
            wait_time = self._rate_limit_window - (now - oldest)
            if wait_time > 0:
                logger.debug(f"[CD_CLIENT] Rate limit: esperando {wait_time:.2f}s")
                time.sleep(wait_time)
        self._request_timestamps.append(time.time())

    # ─── Construccion de requests ─────────────────────────────────────────────

    def _build_url(self, path: str, params: Dict[str, Any] = None) -> str:
        """Construye la URL completa con query params."""
        url = f"{self._base_url}{path}"
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                url += "?" + urllib.parse.urlencode(clean_params)
        return url

    def _build_headers(self, include_auth: bool = False) -> Dict[str, str]:
        """Construye los headers HTTP.

        auth_scheme:
            - "bearer": Authorization: Bearer <token>
            - "token":  Authorization: Token <token>
            - "raw":    Authorization: <token>
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DLAB-CRM-Integration/1.0",
        }
        if include_auth and self._api_token:
            if self._auth_scheme == "token":
                headers["Authorization"] = f"Token {self._api_token}"
            elif self._auth_scheme == "raw":
                headers["Authorization"] = self._api_token
            else:
                headers["Authorization"] = f"Bearer {self._api_token}"
        return headers

    # ─── Ejecucion de requests ────────────────────────────────────────────────

    def _execute_request(
        self,
        method: str,
        path: str,
        params: Dict[str, Any] = None,
        data: dict = None,
        include_auth: bool = False,
        retries: int = MAX_RETRIES,
    ) -> Dict[str, Any]:
        """Ejecuta un request HTTP con reintentos, rate limiting y manejo de errores."""
        url = self._build_url(path, params)
        headers = self._build_headers(include_auth)
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

                    try:
                        response_data = json.loads(response_body) if response_body else {}
                    except json.JSONDecodeError:
                        response_data = {"raw": response_body}

                    logger.info(
                        f"[CD_CLIENT] {method} {path} → {status_code} ({elapsed_ms}ms) "
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
                    f"[CD_CLIENT] {method} {path} → HTTP {status_code} ({elapsed_ms}ms) "
                    f"[attempt {attempt}/{retries}] body={error_body[:200]}"
                )

                # Errores de autenticacion → no reintentar
                if status_code in (401, 403):
                    raise ClaroDomAuthError(
                        f"Error de autenticacion HTTP {status_code}: {error_body[:200]}",
                        status_code=status_code,
                        response_data={"body": error_body},
                    )

                # Rate limiting → esperar y reintentar
                if status_code == 429:
                    retry_after = 5
                    if hasattr(e, "headers") and e.headers:
                        retry_after = int(e.headers.get("Retry-After", 5))
                    if attempt < retries:
                        logger.info(f"[CD_CLIENT] Rate limited, esperando {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    raise ClaroDomRateLimitError(
                        f"Rate limit persistente tras {retries} reintentos",
                        status_code=429,
                    )

                # Errores transitorios → reintentar
                if status_code in RETRYABLE_STATUS_CODES and attempt < retries:
                    backoff = RETRY_BACKOFF_BASE ** attempt
                    logger.info(f"[CD_CLIENT] Retry en {backoff:.1f}s (HTTP {status_code})")
                    time.sleep(backoff)
                    continue

                # Error fatal
                raise ClaroDomError(
                    f"HTTP {status_code}: {error_body[:200]}",
                    status_code=status_code,
                    response_data={"body": error_body},
                )

            except urllib.error.URLError as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                last_error = str(e.reason) if hasattr(e, "reason") else str(e)
                logger.warning(
                    f"[CD_CLIENT] {method} {path} → URL Error: {last_error} ({elapsed_ms}ms) "
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
                    f"[CD_CLIENT] {method} {path} → Error inesperado: {last_error} ({elapsed_ms}ms)",
                    exc_info=True,
                )
                if attempt < retries:
                    backoff = RETRY_BACKOFF_BASE ** attempt
                    time.sleep(backoff)
                    continue

        # Agotados todos los reintentos
        raise ClaroDomError(
            f"Agotados {retries} reintentos para {method} {path}. Ultimo error: {last_error}"
        )

    # ─── API Publica (sin auth) ───────────────────────────────────────────────

    def get_public(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """GET a endpoint publico (sin token)."""
        return self._execute_request("GET", path, params=params, include_auth=False)

    # ─── API Protegida (con Bearer token) ─────────────────────────────────────

    def get(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """GET a endpoint protegido (con token)."""
        return self._execute_request("GET", path, params=params, include_auth=True)

    def post(self, path: str, data: dict = None) -> Dict[str, Any]:
        """POST a endpoint protegido.

        NOTA: preparado para la futura sincronizacion de negocio con ClaroDom
        (modulo `clarodom_sync.py`, aun no implementado). Hoy no tiene ningun
        caller: no se borra porque es la base sobre la que se construira el
        envio de datos hacia ClaroDom cuando esa sincronizacion se implemente.
        """
        return self._execute_request("POST", path, data=data, include_auth=True)

    def put(self, path: str, data: dict = None) -> Dict[str, Any]:
        """PUT a endpoint protegido.

        NOTA: preparado para la futura sincronizacion de negocio con ClaroDom
        (modulo `clarodom_sync.py`, aun no implementado). Hoy no tiene ningun
        caller: no se borra porque es la base sobre la que se construira la
        actualizacion de registros existentes en ClaroDom.
        """
        return self._execute_request("PUT", path, data=data, include_auth=True)

    def get_paginated(
        self, path: str, params: Dict[str, Any] = None, page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """Descarga todos los registros de un endpoint paginado protegido.

        NOTA: preparado para la futura sincronizacion de negocio con ClaroDom
        (modulo `clarodom_sync.py`, aun no implementado). Hoy no tiene ningun
        caller: no se borra porque es la base sobre la que se construira la
        descarga masiva de registros (ej. clientes, cobros) desde ClaroDom.
        """
        all_results = []
        page = 1
        current_params = dict(params or {})

        while True:
            current_params["page"] = page
            current_params["page_size"] = page_size

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
                logger.warning(f"[CD_CLIENT] Safety break: mas de 500 paginas en {path}")
                break

        return all_results

    # ─── Utilidades ───────────────────────────────────────────────────────────

    def test_connection(self) -> Dict[str, Any]:
        """Verifica conectividad con la API usando la ruta de prueba configurada.

        NOTA/LIMITACION: antes esta funcion llamaba a get_public() (sin token).
        No se ha podido confirmar, sin mas documentacion de la API externa de
        ClaroDom, que exista una ruta verdaderamente publica; si no la hay,
        get_public() siempre devuelve 401/403 aunque el token configurado sea
        valido, dando un falso "no conectado". Por eso ahora se usa el metodo
        autenticado (get(), que aplica el auth_scheme configurado: bearer,
        token o raw) contra el mismo test_path. Se considera "conectado"
        cualquier respuesta HTTP del servidor, incluido un 401/403 (eso
        significa que el servidor esta vivo y respondio; si el token es
        invalido, ese matiz lo reporta test_auth()). Solo se marca
        connected=False cuando no hubo respuesta HTTP en absoluto (timeout,
        DNS, conexion rechazada, etc. tras agotar los reintentos).
        """
        try:
            resp = self.get(self._test_path)
            return {
                "connected": True,
                "status_code": resp.get("status_code"),
                "elapsed_ms": resp.get("elapsed_ms"),
                "base_url": self._base_url,
            }
        except ClaroDomAuthError as e:
            # El servidor respondio (401/403): hay conectividad real, aunque
            # las credenciales hayan sido rechazadas. El detalle de auth lo
            # reporta test_auth() por separado.
            return {
                "connected": True,
                "status_code": e.status_code,
                "note": "Servidor alcanzado; credenciales rechazadas (ver resultado de autenticacion)",
                "base_url": self._base_url,
            }
        except ClaroDomError as e:
            return {
                "connected": False,
                "error": e.message,
                "status_code": e.status_code,
                "base_url": self._base_url,
            }

    def test_auth(self) -> Dict[str, Any]:
        """Verifica que el token funcione contra la ruta de prueba con Bearer auth."""
        if not self._api_token:
            return {"authenticated": False, "error": "No hay token configurado"}
        try:
            resp = self.get(self._test_path)
            return {
                "authenticated": True,
                "status_code": resp.get("status_code"),
                "elapsed_ms": resp.get("elapsed_ms"),
            }
        except ClaroDomAuthError as e:
            return {
                "authenticated": False,
                "error": e.message,
                "status_code": e.status_code,
            }
        except ClaroDomError as e:
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