"""Baseline schema: jobs + catalog tables.

Mirrors scripts/init-db.sql so existing local databases (created from
init-db.sql) can be stamped at this revision instead of re-running:

    cd db && alembic stamp 0001

For fresh AWS deploys, this runs from an empty RDS database.

Revision ID: 0001
Revises:
Create Date: 2026-05-07
"""
from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ---- Jobs ----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            job_name        VARCHAR(255) NOT NULL,
            job_type        VARCHAR(50) NOT NULL CHECK (job_type IN ('spark_sql', 'spark_etl', 'spark_ml', 'spark_streaming')),
            status          VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'QUEUED', 'PROVISIONING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED', 'DEAD')),
            spark_config    JSONB DEFAULT '{}',
            entrypoint      TEXT NOT NULL,
            arguments       JSONB DEFAULT '[]',
            database_name   VARCHAR(255),
            table_name      VARCHAR(255),
            container_id    VARCHAR(255),
            submitted_by    VARCHAR(255) NOT NULL,
            submitted_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            started_at      TIMESTAMP WITH TIME ZONE,
            completed_at    TIMESTAMP WITH TIME ZONE,
            error_message   TEXT,
            retry_count     INT DEFAULT 0,
            max_retries     INT DEFAULT 3,
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS job_log_refs (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            job_id          UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            log_stream_id   VARCHAR(255),
            log_source      VARCHAR(50) NOT NULL CHECK (log_source IN ('stdout', 'stderr', 'driver', 'executor')),
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(job_id, log_source)
        )
        """
    )

    # ---- Catalog ----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_databases (
            db_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            db_name         VARCHAR(255) UNIQUE NOT NULL,
            location        TEXT,
            owner           VARCHAR(255),
            description     TEXT,
            properties      JSONB DEFAULT '{}',
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_tables (
            table_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            db_id           UUID NOT NULL REFERENCES catalog_databases(db_id) ON DELETE CASCADE,
            table_name      VARCHAR(255) NOT NULL,
            table_type      VARCHAR(50) DEFAULT 'ICEBERG' CHECK (table_type IN ('ICEBERG', 'DELTA', 'HIVE', 'PARQUET')),
            location        TEXT,
            schema_json     JSONB NOT NULL,
            partition_spec  JSONB DEFAULT '[]',
            sort_order      JSONB DEFAULT '[]',
            current_snapshot_id BIGINT,
            properties      JSONB DEFAULT '{}',
            description     TEXT,
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(db_id, table_name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS table_snapshots (
            snapshot_id     BIGINT PRIMARY KEY,
            table_id        UUID NOT NULL REFERENCES catalog_tables(table_id) ON DELETE CASCADE,
            parent_id       BIGINT,
            operation       VARCHAR(50) CHECK (operation IN ('append', 'overwrite', 'delete', 'replace')),
            manifest_list   TEXT,
            summary         JSONB DEFAULT '{}',
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_history (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            table_id        UUID NOT NULL REFERENCES catalog_tables(table_id) ON DELETE CASCADE,
            version         INT NOT NULL,
            schema_json     JSONB NOT NULL,
            change_summary  TEXT,
            changed_by      VARCHAR(255),
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )

    # ---- Indexes ----
    for stmt in [
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_submitted_by ON jobs(submitted_by)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_submitted_at ON jobs(submitted_at)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type)",
        "CREATE INDEX IF NOT EXISTS idx_job_log_refs_job_id ON job_log_refs(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_catalog_tables_db_id ON catalog_tables(db_id)",
        "CREATE INDEX IF NOT EXISTS idx_table_snapshots_table_id ON table_snapshots(table_id)",
        "CREATE INDEX IF NOT EXISTS idx_schema_history_table_id ON schema_history(table_id)",
    ]:
        op.execute(stmt)

    # ---- updated_at trigger ----
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql'
        """
    )
    for tbl in ("jobs", "catalog_databases", "catalog_tables"):
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger WHERE tgname = 'update_{tbl}_updated_at'
                ) THEN
                    CREATE TRIGGER update_{tbl}_updated_at
                        BEFORE UPDATE ON {tbl}
                        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for tbl in ("jobs", "catalog_databases", "catalog_tables"):
        op.execute(f"DROP TRIGGER IF EXISTS update_{tbl}_updated_at ON {tbl}")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    for tbl in (
        "schema_history",
        "table_snapshots",
        "catalog_tables",
        "catalog_databases",
        "job_log_refs",
        "jobs",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
