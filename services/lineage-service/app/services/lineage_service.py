"""Lineage ingestion + query logic.

Persistence rules:
  * ``runId`` is the dedup key for runs. A second event with the same runId
    UPDATEs the existing row (state, ended_at, facets), never duplicates.
  * Datasets are upserted by (namespace, name).
  * The same dataset appearing twice as an input on the same run is fine —
    UNIQUE(run_id, dataset_id) makes the second insert a no-op.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    LineageDataset,
    LineageRun,
    LineageRunInput,
    LineageRunOutput,
)
from app.models import DatasetRef, OpenLineageEvent

logger = logging.getLogger(__name__)


_TERMINAL_STATES = {"COMPLETE", "FAIL", "ABORT"}


def _extract_dhp_job_id(facets: dict[str, Any]) -> str | None:
    """Look for a DHP job_id under common OpenLineage facet locations."""
    for key in ("dhp", "spark.applicationId", "parent"):
        v = facets.get(key)
        if isinstance(v, dict) and "job_id" in v:
            return str(v["job_id"])
    # Spark emitters often place applicationId at the run level.
    app_id = facets.get("spark.applicationId")
    if isinstance(app_id, str):
        return app_id
    return None


class LineageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(self, event: OpenLineageEvent) -> UUID:
        run_id = event.run.runId

        # Upsert run row.
        is_terminal = event.eventType.upper() in _TERMINAL_STATES
        merged_facets = {**event.run.facets, **event.job.facets}
        dhp_job_id = _extract_dhp_job_id(merged_facets)

        existing = (
            await self.db.execute(
                select(LineageRun).where(LineageRun.run_id == run_id)
            )
        ).scalar_one_or_none()

        if existing:
            existing.state = event.eventType.upper()
            if event.eventType.upper() == "START":
                existing.started_at = event.eventTime
            if is_terminal:
                existing.ended_at = event.eventTime
            # Merge facets; keep newest wins.
            existing.facets = {**existing.facets, **merged_facets}
            if dhp_job_id and not existing.dhp_job_id:
                existing.dhp_job_id = dhp_job_id
        else:
            self.db.add(
                LineageRun(
                    run_id=run_id,
                    job_namespace=event.job.namespace,
                    job_name=event.job.name,
                    dhp_job_id=dhp_job_id,
                    state=event.eventType.upper(),
                    started_at=event.eventTime if event.eventType.upper() == "START" else None,
                    ended_at=event.eventTime if is_terminal else None,
                    facets=merged_facets,
                )
            )
            await self.db.flush()

        # Upsert datasets + edges.
        for ds in event.inputs:
            dataset_id = await self._upsert_dataset(ds)
            await self._link(run_id, dataset_id, direction="input")
        for ds in event.outputs:
            dataset_id = await self._upsert_dataset(ds)
            await self._link(run_id, dataset_id, direction="output")

        await self.db.flush()
        return run_id

    async def _upsert_dataset(self, ds: DatasetRef) -> UUID:
        stmt = (
            pg_insert(LineageDataset)
            .values(namespace=ds.namespace, name=ds.name, facets=ds.facets)
            .on_conflict_do_update(
                index_elements=["namespace", "name"],
                set_={"facets": LineageDataset.facets.op("||")(ds.facets)},
            )
            .returning(LineageDataset.dataset_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def _link(self, run_id: UUID, dataset_id: UUID, *, direction: str) -> None:
        model = LineageRunInput if direction == "input" else LineageRunOutput
        stmt = (
            pg_insert(model)
            .values(run_id=run_id, dataset_id=dataset_id)
            .on_conflict_do_nothing(
                index_elements=["run_id", "dataset_id"],
            )
        )
        await self.db.execute(stmt)

    # ----- Queries -----

    async def runs_for_dhp_job(self, dhp_job_id: str) -> list[LineageRun]:
        rows = (
            await self.db.execute(
                select(LineageRun)
                .where(LineageRun.dhp_job_id == dhp_job_id)
                .order_by(LineageRun.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def get_dataset(self, namespace: str, name: str) -> LineageDataset | None:
        return (
            await self.db.execute(
                select(LineageDataset).where(
                    LineageDataset.namespace == namespace,
                    LineageDataset.name == name,
                )
            )
        ).scalar_one_or_none()

    async def graph(
        self, *, namespace: str, name: str, direction: str, max_depth: int = 5
    ) -> list[dict[str, Any]]:
        """Recursive CTE bounded to ``max_depth`` hops.

        Direction ``upstream``: walk dataset <- output_of <- run <- input_of <- dataset.
        Direction ``downstream``: walk dataset -> input_to -> run -> output_of -> dataset.
        """
        if direction == "upstream":
            sql = """
            WITH RECURSIVE walk(dataset_id, namespace, name, depth) AS (
                SELECT d.dataset_id, d.namespace, d.name, 0
                FROM lineage_datasets d
                WHERE d.namespace = :ns AND d.name = :name

                UNION ALL

                SELECT src.dataset_id, src.namespace, src.name, walk.depth + 1
                FROM walk
                JOIN lineage_run_outputs lro ON lro.dataset_id = walk.dataset_id
                JOIN lineage_run_inputs lri ON lri.run_id = lro.run_id
                JOIN lineage_datasets src ON src.dataset_id = lri.dataset_id
                WHERE walk.depth < :max_depth
            )
            SELECT DISTINCT namespace, name, MIN(depth) AS depth
            FROM walk WHERE depth > 0
            GROUP BY namespace, name
            ORDER BY depth, namespace, name
            """
        elif direction == "downstream":
            sql = """
            WITH RECURSIVE walk(dataset_id, namespace, name, depth) AS (
                SELECT d.dataset_id, d.namespace, d.name, 0
                FROM lineage_datasets d
                WHERE d.namespace = :ns AND d.name = :name

                UNION ALL

                SELECT dst.dataset_id, dst.namespace, dst.name, walk.depth + 1
                FROM walk
                JOIN lineage_run_inputs lri ON lri.dataset_id = walk.dataset_id
                JOIN lineage_run_outputs lro ON lro.run_id = lri.run_id
                JOIN lineage_datasets dst ON dst.dataset_id = lro.dataset_id
                WHERE walk.depth < :max_depth
            )
            SELECT DISTINCT namespace, name, MIN(depth) AS depth
            FROM walk WHERE depth > 0
            GROUP BY namespace, name
            ORDER BY depth, namespace, name
            """
        else:
            raise ValueError(f"direction must be upstream|downstream, got {direction!r}")

        rows = (
            await self.db.execute(
                text(sql), {"ns": namespace, "name": name, "max_depth": max_depth}
            )
        ).mappings().all()
        return [dict(r) for r in rows]
