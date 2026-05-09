"""Job Orchestrator entry point: launches Spark tasks on AWS ECS Fargate."""
from __future__ import annotations

import asyncio
import logging
import signal

from app.consumer import CancellationConsumer, JobConsumer
from app.ecs_manager import ECSJobManager
from app.logging_config import configure_logging
from app.metrics_server import MetricsServer
from app.scheduler import Scheduler

configure_logging(service="orchestrator")
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("DHP orchestrator starting")
    ecs_manager = ECSJobManager()

    job_consumer = JobConsumer(ecs_manager)
    cancel_consumer = CancellationConsumer(ecs_manager)
    metrics_server = MetricsServer()
    scheduler = Scheduler()

    await metrics_server.start()

    tasks = [
        asyncio.create_task(job_consumer.start()),
        asyncio.create_task(cancel_consumer.start()),
        asyncio.create_task(scheduler.start()),
    ]

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: [t.cancel() for t in tasks])
        except NotImplementedError:
            # Windows
            pass

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Orchestrator shutting down")
    finally:
        await metrics_server.stop()


if __name__ == "__main__":
    asyncio.run(main())
