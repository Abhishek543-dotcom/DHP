"""Liveness and readiness probes for metadata-service.

`/health`        — cheap liveness check.
`/health/ready`  — deep readiness check pinging Postgres.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db import async_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

_READINESS_TIMEOUT = 2.0


async def _check_db() -> tuple[bool, str | None]:
    try:
        async with async_session_factory() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), _READINESS_TIMEOUT)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


@router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "healthy", "service": "metadata-service"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, Any]:
    db_ok, db_err = await _check_db()
    checks = {"database": {"ok": db_ok, "error": db_err}}
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("readiness failed: %s", checks)
    return {
        "status": "ready" if db_ok else "not_ready",
        "service": "metadata-service",
        "checks": checks,
    }
