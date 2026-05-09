"""SQLAlchemy models for lineage tables.

Schema is a Marquez-compatible subset: jobs and runs as separate concepts,
datasets keyed by (namespace, name), and many-to-many run<->dataset edges
labeled by direction (input/output). Facets are stored as JSONB to preserve
arbitrary OpenLineage payloads without forcing a brittle column-per-facet
mapping.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LineageRun(Base):
    __tablename__ = "lineage_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    job_namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # DHP job_id (when a Spark job was launched via the orchestrator). Free-text
    # because OpenLineage emitters may not always populate this consistently.
    dhp_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)  # START | COMPLETE | FAIL | ABORT
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    facets: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LineageDataset(Base):
    __tablename__ = "lineage_datasets"
    __table_args__ = (
        UniqueConstraint("namespace", "name", name="uq_lineage_dataset_ns_name"),
    )

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    namespace: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    facets: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LineageRunInput(Base):
    __tablename__ = "lineage_run_inputs"
    __table_args__ = (
        UniqueConstraint("run_id", "dataset_id", name="uq_run_input"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lineage_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lineage_datasets.dataset_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class LineageRunOutput(Base):
    __tablename__ = "lineage_run_outputs"
    __table_args__ = (
        UniqueConstraint("run_id", "dataset_id", name="uq_run_output"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lineage_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lineage_datasets.dataset_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
