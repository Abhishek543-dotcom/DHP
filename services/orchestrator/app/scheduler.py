"""Cron scheduler for materializing scheduled job submissions.

Runs as an asyncio task inside the orchestrator process. Once per
``SCHEDULER_TICK_SECONDS`` it:

  1. Acquires a session-level Postgres advisory lock (``pg_try_advisory_lock``)
     so only one orchestrator replica fires schedules — gives us a poor-man's
     leader election without ZooKeeper.
  2. Selects rows from ``scheduled_jobs`` where ``enabled AND next_run_at <= NOW()``.
  3. For each due row: clones ``job_template`` into a Kafka job event with
     a fresh ``job_id``, publishes to ``KAFKA_JOB_TOPIC``, advances
     ``next_run_at`` via croniter, and stamps ``last_run_at`` / ``last_run_job_id``.

The job-service catalog row is created lazily by the job's ECS callback path
and the existing /jobs/{id}/status updater. We do NOT call the job-service
API here; the scheduler is intentionally a pure DB→Kafka bridge so it stays
operational even if the API tier is down.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from aiokafka import AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.msk_auth import kafka_client_kwargs

logger = logging.getLogger(__name__)
settings = get_settings()

# Single 64-bit constant identifying the scheduler lease across replicas.
# Choose any value; using a fixed key in the dhp keyspace.
_SCHEDULER_LOCK_KEY = 0x4448505F5343484C  # 'DHP_SCHL'

_SCHEDULER_TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "30"))
_DATABASE_URL = os.getenv("DATABASE_URL", "")


def _engine():
    if not _DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required for the scheduler")
    # Convert a sync URL to async if needed (postgresql:// -> postgresql+asyncpg://).
    url = _DATABASE_URL
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return create_async_engine(url, pool_size=2, max_overflow=2, pool_pre_ping=True)


class Scheduler:
    """Polls ``scheduled_jobs`` and emits Kafka job events for due rows."""

    def __init__(self, kafka_topic: str | None = None):
        self._engine = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._producer: AIOKafkaProducer | None = None
        self._topic = kafka_topic or settings.kafka_job_topic
        self._host = socket.gethostname()

    async def start(self) -> None:
        if not _DATABASE_URL:
            logger.warning("Scheduler disabled: DATABASE_URL not configured")
            return

        self._engine = _engine()
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        kwargs = kafka_client_kwargs(
            brokers=settings.kafka_brokers,
            region=settings.aws_region,
            use_iam=settings.msk_use_iam,
        )
        self._producer = AIOKafkaProducer(
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            **kwargs,
        )
        await self._producer.start()
        logger.info(
            "Scheduler started topic=%s tick=%ds host=%s",
            self._topic, _SCHEDULER_TICK_SECONDS, self._host,
        )

        try:
            while True:
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Scheduler tick failed")
                await asyncio.sleep(_SCHEDULER_TICK_SECONDS)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    async def _tick(self) -> None:
        if self._session_factory is None or self._producer is None:
            return

        async with self._session_factory() as session:
            # Try to acquire the leader lock for the duration of this tick.
            # pg_try_advisory_lock returns true if acquired, false otherwise;
            # the lock is released when the session is closed.
            got_lock = (
                await session.execute(
                    text("SELECT pg_try_advisory_lock(:k)"),
                    {"k": _SCHEDULER_LOCK_KEY},
                )
            ).scalar()
            if not got_lock:
                logger.debug("Scheduler tick skipped: another replica holds the lease")
                return

            try:
                rows = (
                    await session.execute(
                        text(
                            "SELECT schedule_id, name, cron_expression, timezone, "
                            "       job_template "
                            "FROM scheduled_jobs "
                            "WHERE enabled = TRUE AND next_run_at <= NOW() "
                            "ORDER BY next_run_at ASC "
                            "LIMIT 50"
                        )
                    )
                ).mappings().all()

                for row in rows:
                    await self._fire(session, row)

                await session.commit()
            finally:
                await session.execute(
                    text("SELECT pg_advisory_unlock(:k)"),
                    {"k": _SCHEDULER_LOCK_KEY},
                )

    async def _fire(self, session: AsyncSession, row: Any) -> None:
        from croniter import croniter
        from zoneinfo import ZoneInfo

        schedule_id: UUID = row["schedule_id"]
        template: dict[str, Any] = dict(row["job_template"])
        job_id = str(uuid4())

        # Clone the template into a Kafka job event with a fresh job_id.
        # The orchestrator's existing JobConsumer will pick it up and launch ECS.
        event = {
            **template,
            "job_id": job_id,
            "scheduled": True,
            "schedule_id": str(schedule_id),
            "schedule_name": row["name"],
        }

        try:
            assert self._producer is not None
            await self._producer.send_and_wait(
                self._topic, key=job_id, value=event
            )
        except Exception:
            logger.exception(
                "Failed to publish scheduled job schedule_id=%s name=%s; "
                "will retry on next tick",
                schedule_id, row["name"],
            )
            # Don't advance next_run_at — so it stays "due" and we'll try again.
            return

        # Advance next_run_at using the row's tz; survives DST.
        tz = ZoneInfo(row["timezone"])
        now_local = datetime.now(tz=tz)
        nxt = croniter(row["cron_expression"], now_local).get_next(datetime)
        nxt_utc = nxt.astimezone(timezone.utc)

        await session.execute(
            text(
                "UPDATE scheduled_jobs "
                "SET last_run_at = NOW(), last_run_job_id = :job_id, "
                "    next_run_at = :nxt "
                "WHERE schedule_id = :sid"
            ),
            {"job_id": job_id, "nxt": nxt_utc, "sid": schedule_id},
        )
        logger.info(
            "Scheduled fire schedule_id=%s name=%s job_id=%s next_run=%s",
            schedule_id, row["name"], job_id, nxt_utc.isoformat(),
        )
