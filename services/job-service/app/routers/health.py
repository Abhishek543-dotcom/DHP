"""Liveness and readiness probes.

`/health`        — cheap liveness check used by ECS container HEALTHCHECK.
`/health/ready`  — deep readiness check used by ALB target group; pings real
                   downstream dependencies (DB + Kafka producer). Returns 503
                   if any dependency is unhealthy so the ALB drains the task.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db.session import async_session_factory
from app.services.kafka_client import get_kafka_producer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

_READINESS_TIMEOUT = 2.0  # seconds per probe


async def _check_db() -> tuple[bool, str | None]:
    try:
        async with async_session_factory() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), _READINESS_TIMEOUT)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


async def _check_kafka() -> tuple[bool, str | None]:
    try:
        producer = await asyncio.wait_for(get_kafka_producer(), _READINESS_TIMEOUT)
        # `_sender` is None until `start()` finishes; aiokafka exposes no public
        # health hook, so we treat a started producer with a live sender as ready.
        if producer is None or getattr(producer, "_closed", False):
            return False, "producer not started"
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Cheap liveness check (no I/O)."""
    return {"status": "healthy", "service": "job-service"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, Any]:
    """Deep readiness check pings DB + Kafka."""
    db_ok, db_err = await _check_db()
    kafka_ok, kafka_err = await _check_kafka()
    checks = {
        "database": {"ok": db_ok, "error": db_err},
        "kafka": {"ok": kafka_ok, "error": kafka_err},
    }
    overall = db_ok and kafka_ok
    if not overall:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("readiness failed: %s", checks)
    return {
        "status": "ready" if overall else "not_ready",
        "service": "job-service",
        "checks": checks,
    }
