"""
Kafka consumer that processes job submission events and launches Spark
tasks on AWS ECS Fargate.

On terminal failure (retry budget exhausted), the original event is forwarded
to the DLQ topic via ``DLQProducer`` so it can be inspected and replayed.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
from aiokafka import AIOKafkaConsumer

from app.config import get_settings
from app.dlq_producer import DLQProducer
from app.ecs_manager import ECSJobManager
from app.metrics import (
    ECS_RUNTASK_SECONDS,
    ORCHESTRATOR_CANCELLATIONS_TOTAL,
    ORCHESTRATOR_DLQ_TOTAL,
    ORCHESTRATOR_LAUNCHES_TOTAL,
    ORCHESTRATOR_RETRIES_TOTAL,
)
from app.msk_auth import kafka_client_kwargs

logger = logging.getLogger(__name__)
settings = get_settings()


def _build_consumer(*, topic: str, group: str, offset_reset: str) -> AIOKafkaConsumer:
    kwargs = kafka_client_kwargs(
        brokers=settings.kafka_brokers,
        region=settings.aws_region,
        use_iam=settings.msk_use_iam,
    )
    return AIOKafkaConsumer(
        topic,
        group_id=group,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset=offset_reset,
        enable_auto_commit=True,
        **kwargs,
    )


class JobConsumer:
    """Consumes job events from Kafka and launches ECS Spark tasks."""

    def __init__(self, ecs_manager: ECSJobManager, dlq: DLQProducer | None = None):
        self.ecs_manager = ecs_manager
        self.dlq = dlq or DLQProducer()
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self.consumer = _build_consumer(
            topic=settings.kafka_job_topic,
            group=settings.kafka_consumer_group,
            offset_reset="earliest",
        )
        await self.consumer.start()
        await self.dlq.start()
        logger.info(
            "Orchestrator consumer started topic=%s group=%s",
            settings.kafka_job_topic,
            settings.kafka_consumer_group,
        )

        try:
            async for message in self.consumer:
                await self._process_message(message)
        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled")
        finally:
            await self.consumer.stop()
            await self.dlq.stop()
            await self.http_client.aclose()

    async def _process_message(self, message) -> None:
        job_event = message.value
        job_id = job_event.get("job_id", "unknown")
        max_retries = int(job_event.get("max_retries", settings.default_max_retries))

        last_error: Exception | None = None
        # Attempts are 1-indexed for log clarity. On AWS the ECS-side retry
        # is what handles per-attempt restarts; this loop guards against
        # transient `RunTask` API errors (throttling, network blips).
        for attempt in range(1, max_retries + 1):
            try:
                await self._update_job_status(job_id, status="PROVISIONING")
                # Launch is sync (boto3) — run in thread to avoid blocking event loop.
                with ECS_RUNTASK_SECONDS.time():
                    task_arn = await asyncio.to_thread(
                        self.ecs_manager.create_spark_job, job_event
                    )
                await self._update_job_status(
                    job_id, status="PROVISIONING", container_id=task_arn
                )
                ORCHESTRATOR_LAUNCHES_TOTAL.labels(outcome="success").inc()
                logger.info(
                    "Launched task arn=%s job_id=%s attempt=%d", task_arn, job_id, attempt
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                ORCHESTRATOR_LAUNCHES_TOTAL.labels(outcome="retry").inc()
                logger.warning(
                    "Launch failed job_id=%s attempt=%d/%d error=%s",
                    job_id, attempt, max_retries, exc,
                )
                # Backoff before retry; skip after final attempt.
                if attempt < max_retries:
                    ORCHESTRATOR_RETRIES_TOTAL.inc()
                    await asyncio.sleep(min(2 ** attempt, 30))

        # Retry budget exhausted — terminal failure.
        err_msg = f"Task launch failed after {max_retries} attempts: {last_error}"
        logger.exception("DLQ-bound: %s", err_msg)
        ORCHESTRATOR_LAUNCHES_TOTAL.labels(outcome="dlq").inc()
        ORCHESTRATOR_DLQ_TOTAL.inc()
        await self._update_job_status(job_id, status="FAILED", error_message=err_msg)
        await self.dlq.publish(
            original_event=job_event,
            error=err_msg,
            attempts=max_retries,
        )

    async def _update_job_status(
        self,
        job_id: str,
        *,
        status: str,
        container_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        url = f"{settings.job_service_url}/api/v1/jobs/{job_id}/status"
        payload: dict = {"status": status}
        if container_id:
            payload["container_id"] = container_id
        if error_message:
            payload["error_message"] = error_message
        try:
            response = await self.http_client.put(
                url,
                json=payload,
                headers={"X-Internal-Token": settings.internal_api_token},
            )
            response.raise_for_status()
        except Exception:
            logger.exception("Failed to update job %s status to %s", job_id, status)


class CancellationConsumer:
    """Consumes cancellation events and stops the corresponding ECS tasks."""

    def __init__(self, ecs_manager: ECSJobManager):
        self.ecs_manager = ecs_manager
        self.consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self.consumer = _build_consumer(
            topic=settings.kafka_job_topic.replace("submissions", "status"),
            group=f"{settings.kafka_consumer_group}-cancellation",
            offset_reset="latest",
        )
        await self.consumer.start()
        logger.info("Cancellation consumer started")

        try:
            async for message in self.consumer:
                event = message.value
                if event.get("action") == "cancel":
                    job_id = event.get("job_id")
                    logger.info("Cancelling job: %s", job_id)
                    try:
                        await asyncio.to_thread(
                            self.ecs_manager.delete_spark_job, job_id
                        )
                        ORCHESTRATOR_CANCELLATIONS_TOTAL.labels(outcome="success").inc()
                    except Exception:
                        ORCHESTRATOR_CANCELLATIONS_TOTAL.labels(outcome="error").inc()
                        logger.exception("Failed to cancel job %s", job_id)
        except asyncio.CancelledError:
            pass
        finally:
            await self.consumer.stop()
