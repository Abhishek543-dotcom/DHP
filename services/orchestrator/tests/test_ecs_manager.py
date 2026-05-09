"""Tests for ECSJobManager using moto-mocked ECS."""
from __future__ import annotations

import json
import os

import pytest

# Set required env BEFORE importing the manager
os.environ.setdefault("ECS_CLUSTER", "test-cluster")
os.environ.setdefault("SPARK_TASK_DEFINITION", "dhp-spark:1")
os.environ.setdefault("SPARK_SUBNETS", "subnet-aaa,subnet-bbb")
os.environ.setdefault("SPARK_SECURITY_GROUP", "sg-xyz")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture
def ecs_manager_with_mock(monkeypatch):
    moto = pytest.importorskip("moto")
    from moto import mock_aws

    with mock_aws():
        import boto3

        ecs = boto3.client("ecs", region_name="us-east-1")
        ecs.create_cluster(clusterName="test-cluster")
        ecs.register_task_definition(
            family="dhp-spark",
            networkMode="awsvpc",
            requiresCompatibilities=["FARGATE"],
            cpu="2048",
            memory="8192",
            containerDefinitions=[
                {"name": "spark", "image": "spark:latest", "essential": True}
            ],
        )

        # Reload settings & manager so they pick up env + the mocked ECS client.
        from app import config as cfg

        cfg.get_settings.cache_clear()
        from app.ecs_manager import ECSJobManager

        yield ECSJobManager()


def test_create_spark_job_returns_task_arn(ecs_manager_with_mock):
    arn = ecs_manager_with_mock.create_spark_job(
        {
            "job_id": "abc12345-aaaa-bbbb-cccc-1234567890ab",
            "entrypoint": "s3://scripts/job.py",
            "arguments": ["--date", "2025-01-01"],
            "spark_config": {"spark.executor.memory": "4g"},
        }
    )
    assert arn.startswith("arn:aws:ecs:")


def test_get_job_status_none_when_no_tasks(ecs_manager_with_mock):
    assert ecs_manager_with_mock.get_job_status("does-not-exist") is None


def test_delete_spark_job_returns_false_when_no_tasks(ecs_manager_with_mock):
    assert ecs_manager_with_mock.delete_spark_job("does-not-exist") is False
