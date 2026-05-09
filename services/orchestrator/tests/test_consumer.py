"""Unit tests for orchestrator JobConsumer with mocked ECS + DLQ producer."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Settings need env defaults BEFORE the consumer module is imported.
os.environ.setdefault("ECS_CLUSTER", "test-cluster")
os.environ.setdefault("SPARK_TASK_DEFINITION", "dhp-spark:1")
os.environ.setdefault("SPARK_SUBNETS", "subnet-aaa")
os.environ.setdefault("SPARK_SECURITY_GROUP", "sg-xyz")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture
def fake_ecs():
    m = MagicMock()
    m.create_spark_job.return_value = "arn:aws:ecs:us-east-1:111:task/abc"
    return m


@pytest.fixture
def fake_dlq():
    dlq = MagicMock()
    dlq.start = AsyncMock()
    dlq.stop = AsyncMock()
    dlq.publish = AsyncMock()
    return dlq


@pytest.fixture
def consumer(fake_ecs, fake_dlq):
    from app.consumer import JobConsumer

    c = JobConsumer(ecs_manager=fake_ecs, dlq=fake_dlq)
    c._update_job_status = AsyncMock()  # bypass real httpx call
    return c


def _msg(value: dict) -> SimpleNamespace:
    return SimpleNamespace(value=value)


@pytest.mark.asyncio
async def test_success_path_no_dlq(consumer, fake_ecs, fake_dlq):
    await consumer._process_message(
        _msg({"job_id": "job-1", "entrypoint": "s3://x/y.py", "max_retries": 3})
    )
    fake_ecs.create_spark_job.assert_called_once()
    fake_dlq.publish.assert_not_awaited()
    # Status updates: 1x PROVISIONING (initial) + 1x PROVISIONING with arn.
    assert consumer._update_job_status.await_count == 2


@pytest.mark.asyncio
async def test_retry_then_success(consumer, fake_ecs, fake_dlq):
    fake_ecs.create_spark_job.side_effect = [RuntimeError("throttled"), "arn:aws:ecs:::task/ok"]
    await consumer._process_message(
        _msg({"job_id": "job-2", "max_retries": 3})
    )
    assert fake_ecs.create_spark_job.call_count == 2
    fake_dlq.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_exhausted_publishes_to_dlq(consumer, fake_ecs, fake_dlq):
    fake_ecs.create_spark_job.side_effect = RuntimeError("perma-fail")
    event = {"job_id": "job-3", "max_retries": 2}
    await consumer._process_message(_msg(event))

    assert fake_ecs.create_spark_job.call_count == 2
    fake_dlq.publish.assert_awaited_once()
    kwargs = fake_dlq.publish.await_args.kwargs
    assert kwargs["original_event"] == event
    assert kwargs["attempts"] == 2
    assert "perma-fail" in kwargs["error"]
    # Final status update flips the job to FAILED.
    final_call = consumer._update_job_status.await_args_list[-1]
    assert final_call.kwargs["status"] == "FAILED"


@pytest.mark.asyncio
async def test_dlq_producer_errors_propagate_from_consumer(fake_ecs):
    """The consumer relies on DLQProducer.publish() to swallow Kafka errors
    internally (see dlq_producer.py). If a DLQ test double raises, the
    error surfaces — confirming the consumer itself does not silently
    swallow DLQ failures.
    """
    from app.consumer import JobConsumer

    flaky_dlq = MagicMock()
    flaky_dlq.start = AsyncMock()
    flaky_dlq.stop = AsyncMock()
    flaky_dlq.publish = AsyncMock(side_effect=RuntimeError("kafka unreachable"))

    c = JobConsumer(ecs_manager=fake_ecs, dlq=flaky_dlq)
    c._update_job_status = AsyncMock()
    fake_ecs.create_spark_job.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await c._process_message(_msg({"job_id": "job-x", "max_retries": 1}))
