import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from app.loki_client import LokiClient, get_loki_client
from app.metrics import LOG_QUERIES_TOTAL, LOG_QUERY_SECONDS, LOKI_ERRORS_TOTAL
from app.security import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/logs",
    tags=["Logs"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/{job_id}")
async def get_job_logs(
    job_id: str,
    source: str = Query("all", description="Log source: stdout, stderr, driver, executor, all"),
    tail: int = Query(500, ge=1, le=10000, description="Number of log lines to retrieve"),
    loki: LokiClient = Depends(get_loki_client),
):
    """
    Get logs for a specific Spark job by Job ID.

    Queries Grafana Loki using the job_id label for log isolation.
    """
    with LOG_QUERY_SECONDS.time():
        try:
            logs = await loki.query_logs(job_id=job_id, source=source, tail=tail)
        except Exception:
            LOKI_ERRORS_TOTAL.inc()
            LOG_QUERIES_TOTAL.labels(source="range", outcome="error").inc()
            raise

    LOG_QUERIES_TOTAL.labels(source="range", outcome="success").inc()
    return {
        "job_id": job_id,
        "source": source,
        "log_count": len(logs),
        "entries": logs,
    }


@router.get("/{job_id}/stream")
async def stream_job_logs(
    job_id: str,
    source: str = Query("all", description="Log source filter"),
    loki: LokiClient = Depends(get_loki_client),
):
    """
    Stream logs for a running job using Server-Sent Events (SSE).

    This endpoint provides real-time log tailing for active jobs.
    """

    async def event_generator():
        last_timestamp = None
        LOG_QUERIES_TOTAL.labels(source="stream", outcome="started").inc()
        while True:
            try:
                logs = await loki.query_logs(
                    job_id=job_id, source=source, tail=50
                )
            except Exception:
                LOKI_ERRORS_TOTAL.inc()
                raise

            for log in logs:
                if last_timestamp is None or log["timestamp"] > last_timestamp:
                    yield {
                        "event": "log",
                        "data": f"[{log['timestamp']}] [{log['source']}] {log['message']}",
                    }
                    last_timestamp = log["timestamp"]

            await asyncio.sleep(2)  # Poll every 2 seconds

    return EventSourceResponse(event_generator())

