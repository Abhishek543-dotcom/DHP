import json
import logging
from aiokafka import AIOKafkaProducer
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_producer: AIOKafkaProducer | None = None


async def get_kafka_producer() -> AIOKafkaProducer:
    """Get or create a Kafka producer instance."""
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            retry_backoff_ms=100,
            max_batch_size=16384,
        )
        await _producer.start()
        logger.info("Kafka producer started")
    return _producer


async def close_kafka_producer():
    """Close the Kafka producer."""
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer stopped")


async def send_job_event(topic: str, job_id: str, event: dict):
    """Send a job event to Kafka."""
    producer = await get_kafka_producer()
    try:
        await producer.send_and_wait(
            topic=topic,
            key=job_id,
            value=event,
        )
        logger.info(f"Job event sent to {topic}: job_id={job_id}")
    except Exception as e:
        logger.error(f"Failed to send job event to Kafka: {e}")
        raise

