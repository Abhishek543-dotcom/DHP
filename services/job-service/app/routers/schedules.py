"""Schedules API: cron-driven job submissions.

Schedules are stored in the ``scheduled_jobs`` table. The orchestrator's
scheduler loop polls this table and materializes due rows into Kafka job
events, so this router only handles CRUD; it never publishes events itself
(except via the explicit /trigger endpoint, which delegates to JobService).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScheduledJob
from app.db.session import get_db
from app.models.job import JobCreateRequest, JobResponse
from app.models.schedule import (
    ScheduleCreateRequest,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleUpdateRequest,
)
from app.security import require_api_key
from app.services.job_service import JobService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/schedules",
    tags=["Schedules"],
    dependencies=[Depends(require_api_key)],
)


def _next_run(cron_expr: str, tz_name: str, base: datetime | None = None) -> datetime:
    """Compute the next fire timestamp (UTC) for a cron expression.

    croniter accepts a timezone-aware ``base`` datetime and returns aware
    datetimes when constructed with one, so the math survives DST.
    """
    from croniter import croniter
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    base = base or datetime.now(tz=tz)
    if base.tzinfo is None:
        base = base.replace(tzinfo=tz)
    itr = croniter(cron_expr, base.astimezone(tz))
    nxt = itr.get_next(datetime)
    # Always store/return UTC for consistency.
    return nxt.astimezone(timezone.utc)


@router.post("/", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    request: ScheduleCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(select(ScheduledJob).where(ScheduledJob.name == request.name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"Schedule '{request.name}' already exists")

    next_run = _next_run(request.cron_expression, request.timezone)
    record = ScheduledJob(
        name=request.name,
        cron_expression=request.cron_expression,
        timezone=request.timezone,
        job_template=request.job_template.model_dump(mode="json"),
        enabled=request.enabled,
        next_run_at=next_run,
        created_by=request.created_by,
    )
    db.add(record)
    await db.flush()
    return ScheduleResponse.model_validate(record)


@router.get("/", response_model=ScheduleListResponse)
async def list_schedules(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(ScheduledJob).order_by(ScheduledJob.name))
    ).scalars().all()
    return ScheduleListResponse(
        total=len(rows),
        schedules=[ScheduleResponse.model_validate(r) for r in rows],
    )


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: UUID, db: AsyncSession = Depends(get_db)):
    record = (
        await db.execute(
            select(ScheduledJob).where(ScheduledJob.schedule_id == schedule_id)
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Schedule not found")
    return ScheduleResponse.model_validate(record)


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: UUID,
    request: ScheduleUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    record = (
        await db.execute(
            select(ScheduledJob).where(ScheduledJob.schedule_id == schedule_id)
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Schedule not found")

    if request.cron_expression is not None:
        record.cron_expression = request.cron_expression
    if request.timezone is not None:
        record.timezone = request.timezone
    if request.job_template is not None:
        record.job_template = request.job_template.model_dump(mode="json")
    if request.enabled is not None:
        record.enabled = request.enabled

    # Cron or timezone change invalidates the previously-computed next_run_at.
    if request.cron_expression is not None or request.timezone is not None:
        record.next_run_at = _next_run(record.cron_expression, record.timezone)

    await db.flush()
    return ScheduleResponse.model_validate(record)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: UUID, db: AsyncSession = Depends(get_db)):
    record = (
        await db.execute(
            select(ScheduledJob).where(ScheduledJob.schedule_id == schedule_id)
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Schedule not found")
    await db.delete(record)
    await db.flush()


@router.post("/{schedule_id}/trigger", response_model=JobResponse, status_code=202)
async def trigger_schedule(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Manually fire a schedule once, bypassing cron timing.

    Useful for testing the schedule's job_template without waiting for the
    next cron tick. The schedule's next_run_at is NOT advanced — that remains
    the orchestrator's job.
    """
    record = (
        await db.execute(
            select(ScheduledJob).where(ScheduledJob.schedule_id == schedule_id)
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Schedule not found")

    template = JobCreateRequest.model_validate(record.job_template)
    svc = JobService(db)
    response = await svc.create_job(template)

    record.last_run_at = datetime.now(timezone.utc)
    record.last_run_job_id = UUID(response.job_id)
    await db.flush()
    return response
