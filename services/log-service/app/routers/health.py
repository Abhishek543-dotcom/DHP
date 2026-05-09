"""Liveness and readiness probes for log-service."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Response, status

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])
settings = get_settings()

_READINESS_TIMEOUT = 2.0


async def _check_loki() -> tuple[bool, str | None]:
    try:
        async with httpx.AsyncClient(timeout=_READINESS_TIMEOUT) as client:
            r = await client.get(f"{settings.loki_url}/ready")
            if r.status_code == 200:
                return True, None
            return False, f"loki /ready returned {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


@router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "healthy", "service": "log-service"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, Any]:
    loki_ok, loki_err = await _check_loki()
    checks = {"loki": {"ok": loki_ok, "error": loki_err}}
    if not loki_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("readiness failed: %s", checks)
    return {
        "status": "ready" if loki_ok else "not_ready",
        "service": "log-service",
        "checks": checks,
    }
