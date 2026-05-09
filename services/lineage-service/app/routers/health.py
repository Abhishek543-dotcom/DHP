"""Health endpoints for lineage-service."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.db import async_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

_READINESS_TIMEOUT = 3.0


@router.get("/health")
async def health():
    return {"status": "ok", "service": "lineage-service"}


@router.get("/health/ready")
async def ready():
    try:
        async with async_session_factory() as session:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")), _READINESS_TIMEOUT
            )
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("Readiness DB check failed: %s", exc)
        return {"status": "not_ready", "error": f"{type(exc).__name__}"}, 503
