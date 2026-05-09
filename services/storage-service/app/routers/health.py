"""Liveness and readiness probes for storage-service."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Response, status

from app.s3_client import get_s3_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

_READINESS_TIMEOUT = 2.0


async def _check_s3() -> tuple[bool, str | None]:
    try:
        client = get_s3_client().client
        # boto3 is sync; offload to thread to keep the event loop responsive.
        await asyncio.wait_for(asyncio.to_thread(client.list_buckets), _READINESS_TIMEOUT)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


@router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "healthy", "service": "storage-service"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, Any]:
    s3_ok, s3_err = await _check_s3()
    checks = {"s3": {"ok": s3_ok, "error": s3_err}}
    if not s3_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("readiness failed: %s", checks)
    return {
        "status": "ready" if s3_ok else "not_ready",
        "service": "storage-service",
        "checks": checks,
    }
