"""Unit tests for DLQProducer. AIOKafkaProducer is mocked."""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("ECS_CLUSTER", "test-cluster")
os.environ.setdefault("SPARK_TASK_DEFINITION", "dhp-spark:1")
os.environ.setdefault("SPARK_SUBNETS", "subnet-aaa")
os.environ.setdefault("SPARK_SECURITY_GROUP", "sg-xyz")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.mark.asyncio
async def test_publish_payload_shape():
    from app import dlq_producer as dlq_mod

    with patch.object(dlq_mod, "AIOKafkaProducer") as fake_cls, \
         patch.object(dlq_mod, "kafka_client_kwargs", return_value={"bootstrap_servers": "x:9092"}):
        producer = fake_cls.return_value
        producer.start = AsyncMock()
        producer.stop = AsyncMock()
        producer.send_and_wait = AsyncMock()

        d = dlq_mod.DLQProducer()
        original = {"job_id": "abc", "entrypoint": "s3://x/y.py"}
        await d.publish(original_event=original, error="boom", attempts=3)

        producer.start.assert_awaited_once()
        producer.send_and_wait.assert_awaited_once()
        topic, *_ = producer.send_and_wait.await_args.args
        assert topic == dlq_mod.DLQ_TOPIC

        payload = producer.send_and_wait.await_args.kwargs["value"]
        assert payload["job_id"] == "abc"
        assert payload["original_event"] == original
        assert payload["error"] == "boom"
        assert payload["attempts"] == 3
        assert "timestamp" in payload
        assert "host" in payload


@pytest.mark.asyncio
async def test_publish_swallows_kafka_errors():
    from app import dlq_producer as dlq_mod

    with patch.object(dlq_mod, "AIOKafkaProducer") as fake_cls, \
         patch.object(dlq_mod, "kafka_client_kwargs", return_value={"bootstrap_servers": "x:9092"}):
        producer = fake_cls.return_value
        producer.start = AsyncMock()
        producer.send_and_wait = AsyncMock(side_effect=RuntimeError("kafka down"))

        d = dlq_mod.DLQProducer()
        # Must not raise — DLQ failure should never mask the original error.
        await d.publish(original_event={"job_id": "z"}, error="x", attempts=1)
