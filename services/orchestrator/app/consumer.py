"""
Kafka consumer that processes job submission events and launches Spark containers.
"""
import json
import asyncio
import logging

import httpx
from aiokafka import AIOKafkaConsumer

from app.config import get_settings
from app.k8s_manager import K8sJobManager

logger = logging.getLogger(__name__)
settings = get_settings()


class JobConsumer:
    """Consumes job events from Kafka and delegates to K8s."""

    def __init__(self):
        self.k8s_manager = K8sJobManager()
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.consumer: AIOKafkaConsumer | None = None

    async def start(self):
        """Start the Kafka consumer loop."""
        self.consumer = AIOKafkaConsumer(
            settings.kafka_job_topic,
            bootstrap_servers=settings.kafka_brokers,
            group_id=settings.kafka_consumer_group,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

        await self.consumer.start()
        logger.info(
            f"Orchestrator consumer started — listening on '{settings.kafka_job_topic}'"
        )

        try:
            async for message in self.consumer:
                await self._process_message(message)
        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled")
        finally:
            await self.consumer.stop()
            await self.http_client.aclose()
            logger.info("Consumer stopped")

    async def _process_message(self, message):
        """Process a single job event from Kafka."""
        job_event = message.value
        job_id = job_event.get("job_id", "unknown")

        logger.info(f"Processing job event: job_id={job_id}")

        try:
            # Update job status to PROVISIONING
            await self._update_job_status(
                job_id, status="PROVISIONING"
            )

            # Launch Spark container on K8s
            container_id = self.k8s_manager.create_spark_job(job_event)

            # Keep the job in PROVISIONING until the Spark container
            # explicitly reports RUNNING from inside the runtime.
            await self._update_job_status(
                job_id,
                status="PROVISIONING",
                container_id=container_id,
            )

            logger.info(
                f"[OK] Launched container '{container_id}' for job {job_id}"
            )

        except Exception as e:
            logger.error(f"[ERROR] Failed to launch job {job_id}: {e}")
            await self._update_job_status(
                job_id,
                status="FAILED",
                error_message=f"Container launch failed: {str(e)}",
            )

    async def _update_job_status(
        self,
        job_id: str,
        status: str,
        container_id: str = None,
        error_message: str = None,
    ):
        """Call back to Job Service to update job status."""
        url = f"{settings.job_service_url}/api/v1/jobs/{job_id}/status"
        payload = {"status": status}
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
            logger.info(f"Updated job {job_id} status to {status}")
        except Exception as e:
            logger.error(
                f"Failed to update job {job_id} status to {status}: {e}"
            )


class CancellationConsumer:
    """Consumes job cancellation events and kills K8s jobs."""

    def __init__(self, k8s_manager: K8sJobManager):
        self.k8s_manager = k8s_manager
        self.consumer: AIOKafkaConsumer | None = None

    async def start(self):
        """Listen for cancellation events on the status topic."""
        self.consumer = AIOKafkaConsumer(
            settings.kafka_job_topic.replace("submissions", "status"),
            bootstrap_servers=settings.kafka_brokers,
            group_id=f"{settings.kafka_consumer_group}-cancellation",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )

        await self.consumer.start()
        logger.info("Cancellation consumer started")

        try:
            async for message in self.consumer:
                event = message.value
                if event.get("action") == "cancel":
                    job_id = event.get("job_id")
                    logger.info(f"Cancelling job: {job_id}")
                    try:
                        self.k8s_manager.delete_spark_job(job_id)
                    except Exception as e:
                        logger.error(f"Failed to cancel job {job_id}: {e}")
        except asyncio.CancelledError:
            pass
        finally:
            await self.consumer.stop()

