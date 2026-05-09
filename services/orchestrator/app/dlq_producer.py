"""Dead-letter producer for permanently failed Spark job launches.

When ``JobConsumer`` exhausts its retry budget for a job, the original event
plus failure metadata is published to ``KAFKA_DLQ_TOPIC`` (default
``spark-job-submissions-dlq``). On-call can replay/inspect the topic for root
cause without losing the original payload.

Uses the same MSK IAM auth path as the main consumer; falls back to plaintext
when ``MSK_USE_IAM=false`` (local docker-compose).
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any

from aiokafka import AIOKafkaProducer

from app.config import get_settings
from app.msk_auth import kafka_client_kwargs

logger = logging.getLogger(__name__)
settings = get_settings()

DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "spark-job-submissions-dlq")


class DLQProducer:
    """Async Kafka producer dedicated to the DLQ topic."""

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None
        self._host = socket.gethostname()

    async def start(self) -> None:
        if self._producer is not None:
            return
        kwargs = kafka_client_kwargs(
            brokers=settings.kafka_brokers,
            region=settings.aws_region,
            use_iam=settings.msk_use_iam,
        )
        self._producer = AIOKafkaProducer(
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            retry_backoff_ms=500,
            **kwargs,
        )
        await self._producer.start()
        logger.info("DLQ producer started topic=%s", DLQ_TOPIC)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(
        self,
        *,
        original_event: dict[str, Any],
        error: str,
        attempts: int,
    ) -> None:
        if self._producer is None:
            await self.start()
        assert self._producer is not None  # narrow type after start

        job_id = str(original_event.get("job_id", "unknown"))
        payload = {
            "job_id": job_id,
            "original_event": original_event,
            "error": error,
            "attempts": attempts,
            "host": self._host,
            "timestamp": time.time(),
        }
        try:
            await self._producer.send_and_wait(DLQ_TOPIC, key=job_id, value=payload)
            logger.warning(
                "dlq publish topic=%s job_id=%s attempts=%d", DLQ_TOPIC, job_id, attempts
            )
        except Exception:
            # Never let DLQ failure mask the original error.
            logger.exception("DLQ publish failed for job_id=%s", job_id)
