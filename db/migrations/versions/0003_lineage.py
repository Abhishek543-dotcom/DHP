"""Lineage tables: runs, datasets, run_inputs, run_outputs.

Schema is a Marquez-compatible subset that captures OpenLineage RunEvents
from Spark jobs. Facets stored as JSONB to preserve forward-compat fields.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07
"""
from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lineage_runs (
            run_id          UUID PRIMARY KEY,
            job_namespace   VARCHAR(255) NOT NULL,
            job_name        VARCHAR(255) NOT NULL,
            dhp_job_id      VARCHAR(255),
            state           VARCHAR(32)  NOT NULL,
            started_at      TIMESTAMPTZ,
            ended_at        TIMESTAMPTZ,
            facets          JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_lineage_runs_dhp_job_id
            ON lineage_runs (dhp_job_id);
        CREATE INDEX IF NOT EXISTS ix_lineage_runs_job_ns_name
            ON lineage_runs (job_namespace, job_name);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lineage_datasets (
            dataset_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            namespace       VARCHAR(512)  NOT NULL,
            name            VARCHAR(1024) NOT NULL,
            facets          JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_lineage_dataset_ns_name UNIQUE (namespace, name)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lineage_run_inputs (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            run_id      UUID NOT NULL REFERENCES lineage_runs(run_id) ON DELETE CASCADE,
            dataset_id  UUID NOT NULL REFERENCES lineage_datasets(dataset_id) ON DELETE CASCADE,
            CONSTRAINT uq_run_input UNIQUE (run_id, dataset_id)
        );
        CREATE INDEX IF NOT EXISTS ix_lineage_run_inputs_run ON lineage_run_inputs (run_id);
        CREATE INDEX IF NOT EXISTS ix_lineage_run_inputs_dataset ON lineage_run_inputs (dataset_id);

        CREATE TABLE IF NOT EXISTS lineage_run_outputs (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            run_id      UUID NOT NULL REFERENCES lineage_runs(run_id) ON DELETE CASCADE,
            dataset_id  UUID NOT NULL REFERENCES lineage_datasets(dataset_id) ON DELETE CASCADE,
            CONSTRAINT uq_run_output UNIQUE (run_id, dataset_id)
        );
        CREATE INDEX IF NOT EXISTS ix_lineage_run_outputs_run ON lineage_run_outputs (run_id);
        CREATE INDEX IF NOT EXISTS ix_lineage_run_outputs_dataset ON lineage_run_outputs (dataset_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lineage_run_outputs")
    op.execute("DROP TABLE IF EXISTS lineage_run_inputs")
    op.execute("DROP TABLE IF EXISTS lineage_datasets")
    op.execute("DROP TABLE IF EXISTS lineage_runs")
