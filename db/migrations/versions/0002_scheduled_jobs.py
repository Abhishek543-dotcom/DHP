"""Scheduled jobs (cron-driven job submissions).

Adds the ``scheduled_jobs`` table consumed by the job-service ``/schedules``
API and the orchestrator scheduler loop. The scheduler picks up rows whose
``next_run_at <= now() AND enabled`` and materializes them into Kafka job
events, then advances ``next_run_at`` via croniter.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            schedule_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name             VARCHAR(255) NOT NULL UNIQUE,
            cron_expression  VARCHAR(255) NOT NULL,
            timezone         VARCHAR(64)  NOT NULL DEFAULT 'UTC',
            -- JSON payload matching JobCreateRequest. The scheduler clones it
            -- into a Kafka job event on each fire, with a fresh job_id.
            job_template     JSONB NOT NULL,
            enabled          BOOLEAN NOT NULL DEFAULT TRUE,
            last_run_at      TIMESTAMPTZ,
            last_run_job_id  UUID,
            -- next_run_at is recomputed by the API on create/update and by the
            -- scheduler after each successful fire.
            next_run_at      TIMESTAMPTZ NOT NULL,
            created_by       VARCHAR(255),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # Hot-path index for the scheduler's "due now" query.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduled_jobs_due
            ON scheduled_jobs (next_run_at)
            WHERE enabled = TRUE;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scheduled_jobs_due")
    op.execute("DROP TABLE IF EXISTS scheduled_jobs")
