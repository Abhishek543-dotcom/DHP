"""Lineage HTTP API.

Routes:
  POST /api/v1/lineage              - ingest an OpenLineage event
  GET  /api/v1/lineage/jobs/{id}/runs        - runs for a DHP job
  GET  /api/v1/lineage/datasets/{ns}/{name}  - dataset metadata
  GET  /api/v1/lineage/datasets/{ns}/{name}/upstream
  GET  /api/v1/lineage/datasets/{ns}/{name}/downstream
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.metrics import LINEAGE_EVENTS_TOTAL, LINEAGE_GRAPH_QUERIES_TOTAL
from app.models import (
    DatasetResponse,
    LineageGraphResponse,
    LineageNode,
    OpenLineageEvent,
    RunResponse,
)
from app.security import require_api_key
from app.services.lineage_service import LineageService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/lineage",
    tags=["Lineage"],
    dependencies=[Depends(require_api_key)],
)


def _svc(db: AsyncSession = Depends(get_db)) -> LineageService:
    return LineageService(db)


@router.post("/", status_code=201)
async def ingest(event: OpenLineageEvent, svc: LineageService = Depends(_svc)):
    try:
        run_id = await svc.ingest(event)
        LINEAGE_EVENTS_TOTAL.labels(
            event_type=event.eventType.upper(), outcome="success"
        ).inc()
        return {"run_id": str(run_id), "ingested": True}
    except Exception:
        LINEAGE_EVENTS_TOTAL.labels(
            event_type=event.eventType.upper(), outcome="error"
        ).inc()
        raise


@router.get("/jobs/{dhp_job_id}/runs", response_model=list[RunResponse])
async def runs_for_job(dhp_job_id: str, svc: LineageService = Depends(_svc)):
    rows = await svc.runs_for_dhp_job(dhp_job_id)
    return [RunResponse.model_validate(r) for r in rows]


@router.get("/datasets/{namespace}/{name:path}", response_model=DatasetResponse)
async def get_dataset(
    namespace: str, name: str, svc: LineageService = Depends(_svc)
):
    ds = await svc.get_dataset(namespace, name)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return DatasetResponse.model_validate(ds)


@router.get(
    "/datasets/{namespace}/{name:path}/upstream",
    response_model=LineageGraphResponse,
)
async def upstream(
    namespace: str,
    name: str,
    max_depth: int = Query(5, ge=1, le=10),
    svc: LineageService = Depends(_svc),
):
    return await _graph(svc, namespace, name, "upstream", max_depth)


@router.get(
    "/datasets/{namespace}/{name:path}/downstream",
    response_model=LineageGraphResponse,
)
async def downstream(
    namespace: str,
    name: str,
    max_depth: int = Query(5, ge=1, le=10),
    svc: LineageService = Depends(_svc),
):
    return await _graph(svc, namespace, name, "downstream", max_depth)


async def _graph(
    svc: LineageService, namespace: str, name: str, direction: str, max_depth: int
) -> LineageGraphResponse:
    root = await svc.get_dataset(namespace, name)
    if not root:
        LINEAGE_GRAPH_QUERIES_TOTAL.labels(direction=direction, outcome="not_found").inc()
        raise HTTPException(404, "Dataset not found")
    rows = await svc.graph(
        namespace=namespace, name=name, direction=direction, max_depth=max_depth
    )
    LINEAGE_GRAPH_QUERIES_TOTAL.labels(direction=direction, outcome="success").inc()
    return LineageGraphResponse(
        root=DatasetResponse.model_validate(root),
        direction=direction,
        nodes=[LineageNode(**r) for r in rows],
    )
