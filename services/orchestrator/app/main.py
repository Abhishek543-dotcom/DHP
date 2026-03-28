"""
Job Orchestrator — Main entry point.

Starts the Kafka consumer that listens for job submissions
and launches Spark containers on Kubernetes.
"""
import asyncio
import logging
import signal

from app.consumer import JobConsumer, CancellationConsumer
from app.k8s_manager import K8sJobManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 60)
    logger.info("  Lakehouse Job Orchestrator Starting")
    logger.info("=" * 60)

    k8s_manager = K8sJobManager()

    # Start both consumers
    job_consumer = JobConsumer()
    cancel_consumer = CancellationConsumer(k8s_manager)

    # Run consumers as concurrent tasks
    tasks = [
        asyncio.create_task(job_consumer.start()),
        asyncio.create_task(cancel_consumer.start()),
    ]

    # Handle graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: [t.cancel() for t in tasks])
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Orchestrator shutting down gracefully")


if __name__ == "__main__":
    asyncio.run(main())

