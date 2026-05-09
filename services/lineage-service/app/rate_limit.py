"""Rate limiting using slowapi backed by ElastiCache Redis.

Identifies clients by API key (``X-API-Key`` header), falling back to remote IP
when the header is absent. Service-to-service traffic carrying the
``X-Internal-Token`` header bypasses the limiter entirely.

Defaults are applied to every route via ``SlowAPIMiddleware`` — no per-route
decorators required. Health and metrics paths are exempted so probes and
Prometheus scrapes are never throttled.

Wire into a FastAPI app with::

    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from app.rate_limit import limiter, rate_limit_exceeded_handler

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
"""
from __future__ import annotations

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()

# Per-service default; override via env without code change.
_DEFAULT_LIMIT = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
_EXEMPT_PATH_PREFIXES = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/")


def _client_key(request: Request) -> str:
    """Identify the caller for rate-limit bucketing."""
    api_key = request.headers.get("x-api-key")
    if api_key:
        # Prefix to avoid colliding with IP keys; truncate so we never log full keys.
        return f"key:{api_key[:32]}"
    return f"ip:{get_remote_address(request)}"


def is_internal_request(request: Request) -> bool:
    """Skip rate-limiting for service-to-service or probe traffic."""
    if request.headers.get("x-internal-token"):
        return True
    path = request.url.path
    # `/` is the root JSON page; everything below `/api/` is API traffic.
    if path == "/" or any(path == p or path.startswith(p + "/") for p in _EXEMPT_PATH_PREFIXES if p != "/"):
        return True
    return False


_storage_uri = _settings.redis_url if getattr(_settings, "redis_url", None) else "memory://"

limiter = Limiter(
    key_func=_client_key,
    storage_uri=_storage_uri,
    strategy="fixed-window",
    default_limits=[_DEFAULT_LIMIT],
    default_limits_exempt_when=is_internal_request,
    headers_enabled=True,
    swallow_errors=True,  # Never 500 because the limiter store is unavailable.
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    logger.warning(
        "rate_limit_exceeded",
        extra={"path": request.url.path, "client": _client_key(request)},
    )
    detail = getattr(exc, "detail", "rate limit exceeded")
    return JSONResponse(
        status_code=429,
        content={"detail": str(detail)},
        headers={"Retry-After": "60"},
    )
