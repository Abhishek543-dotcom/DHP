"""Pydantic schemas for the scheduled-jobs API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.job import JobCreateRequest


def _validate_cron(value: str) -> str:
    # Defer import so the package import graph stays light for unit tests
    # that don't touch scheduling.
    from croniter import CroniterBadCronError, croniter

    try:
        croniter(value)
    except (CroniterBadCronError, ValueError) as e:
        raise ValueError(f"Invalid cron expression: {e}") from e
    return value


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Unique schedule name")
    cron_expression: str = Field(
        ..., description="5-field cron expression in the schedule's timezone"
    )
    timezone: str = Field("UTC", max_length=64)
    job_template: JobCreateRequest = Field(
        ..., description="Job payload materialized on every cron fire"
    )
    enabled: bool = True
    created_by: Optional[str] = None

    @field_validator("cron_expression")
    @classmethod
    def _check_cron(cls, v: str) -> str:
        return _validate_cron(v)


class ScheduleUpdateRequest(BaseModel):
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    job_template: Optional[JobCreateRequest] = None
    enabled: Optional[bool] = None

    @field_validator("cron_expression")
    @classmethod
    def _check_cron(cls, v: Optional[str]) -> Optional[str]:
        return _validate_cron(v) if v is not None else v


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schedule_id: UUID
    name: str
    cron_expression: str
    timezone: str
    job_template: dict
    enabled: bool
    last_run_at: Optional[datetime]
    last_run_job_id: Optional[UUID]
    next_run_at: datetime
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime


class ScheduleListResponse(BaseModel):
    total: int
    schedules: list[ScheduleResponse]
