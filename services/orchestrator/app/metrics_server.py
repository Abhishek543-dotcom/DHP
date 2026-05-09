"""Lightweight aiohttp HTTP server exposing ``/metrics`` for Prometheus scrapes.

The orchestrator runs as a Kafka consumer (no FastAPI), so we cannot reuse
``prometheus_fastapi_instrumentator``. Instead we serve the default
``prometheus_client`` registry on a dedicated port (default 9000) — Prometheus
or the ECS scrape sidecar can reach this via the task's awsvpc ENI.

The server also exposes ``/health`` for ECS readiness checks; it returns
200 unconditionally because liveness for the orchestrator is "process is
running" — Kafka group rebalance handles consumer-side health.
"""

from __future__ import annotations

import logging
from typing import Optional

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

logger = logging.getLogger(__name__)


async def _metrics(_: web.Request) -> web.Response:
    body = generate_latest()
    return web.Response(body=body, headers={"Content-Type": CONTENT_TYPE_LATEST})


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


class MetricsServer:
    """Run an aiohttp app on a background asyncio task."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9000) -> None:
        self.host = host
        self.port = port
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.BaseSite] = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/metrics", _metrics)
        app.router.add_get("/health", _health)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.host, port=self.port)
        await self._site.start()
        logger.info("Metrics server listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        logger.info("Metrics server stopped")
