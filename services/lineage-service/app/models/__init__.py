"""Pydantic schemas for the lineage API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetRef(BaseModel):
    """OpenLineage InputDataset / OutputDataset (subset)."""

    namespace: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    facets: dict[str, Any] = Field(default_factory=dict)


class JobRef(BaseModel):
    namespace: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    facets: dict[str, Any] = Field(default_factory=dict)


class RunRef(BaseModel):
    runId: UUID
    facets: dict[str, Any] = Field(default_factory=dict)


class OpenLineageEvent(BaseModel):
    """Subset of the OpenLineage RunEvent we accept.

    The official spec includes additional fields (eventTime, eventType,
    producer, schemaURL) — we keep them as raw extras via model_config so
    upstream emitters never get rejected for being too forward-compatible.
    """

    eventType: str = Field(..., description="START | COMPLETE | FAIL | ABORT | OTHER")
    eventTime: datetime
    run: RunRef
    job: JobRef
    inputs: list[DatasetRef] = Field(default_factory=list)
    outputs: list[DatasetRef] = Field(default_factory=list)
    producer: str | None = None

    model_config = ConfigDict(extra="allow")


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    job_namespace: str
    job_name: str
    dhp_job_id: str | None
    state: str
    started_at: datetime | None
    ended_at: datetime | None
    facets: dict
    created_at: datetime


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    namespace: str
    name: str
    facets: dict
    created_at: datetime
    updated_at: datetime


class LineageNode(BaseModel):
    """One hop in an upstream/downstream traversal."""

    namespace: str
    name: str
    depth: int


class LineageGraphResponse(BaseModel):
    root: DatasetResponse
    direction: str  # "upstream" | "downstream"
    nodes: list[LineageNode]
