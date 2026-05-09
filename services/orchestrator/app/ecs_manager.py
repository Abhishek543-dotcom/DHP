"""
ECS task manager for launching Spark jobs on AWS ECS Fargate via RunTask.

Replaces the previous Kubernetes-based job manager. Jobs are launched as
ECS tasks using a pre-registered task definition (TF-managed). Per-job
overrides (script URI, arguments, env, resources) are passed via the
RunTask `overrides` parameter so we don't need a new task definition per job.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ECSJobManager:
    """Launch and manage Spark jobs as ECS Fargate tasks."""

    def __init__(self) -> None:
        # boto3 picks up region/credentials from the task role (via IMDS).
        boto_cfg = BotoConfig(retries={"max_attempts": 5, "mode": "standard"})
        self.ecs = boto3.client("ecs", region_name=settings.aws_region, config=boto_cfg)
        self.cluster = settings.ecs_cluster
        self.task_definition = settings.spark_task_definition
        self.subnets = [s for s in settings.spark_subnets.split(",") if s]
        self.security_groups = [
            s for s in settings.spark_security_group.split(",") if s
        ]
        self.container_name = settings.spark_container_name

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    def create_spark_job(self, job_event: dict) -> str:
        """Launch a Spark task on ECS. Returns the ECS task ARN."""
        job_id = job_event["job_id"]
        retry_count = int(job_event.get("retry_count", 0))
        arguments = job_event.get("arguments", [])
        spark_config = job_event.get("spark_config", {})
        spark_conf_str = " ".join(f"--conf {k}={v}" for k, v in spark_config.items())

        runtime_kafka_brokers = (
            settings.runtime_kafka_brokers or settings.kafka_brokers
        )
        runtime_job_service_url = (
            settings.runtime_job_service_url or settings.job_service_url
        )

        env_overrides = [
            {"name": "JOB_ID", "value": job_id},
            {"name": "JOB_RETRY_COUNT", "value": str(retry_count)},
            {"name": "ENTRYPOINT_SCRIPT", "value": job_event["entrypoint"]},
            {"name": "ARGUMENTS", "value": " ".join(arguments)},
            {"name": "SPARK_EXTRA_CONF", "value": spark_conf_str},
            {"name": "KAFKA_BROKERS", "value": runtime_kafka_brokers},
            {
                "name": "CALLBACK_URL",
                "value": f"{runtime_job_service_url}/api/v1/jobs/{job_id}/status",
            },
            {"name": "INTERNAL_API_TOKEN", "value": settings.internal_api_token},
        ]

        container_override = {
            "name": self.container_name,
            "environment": env_overrides,
        }

        # Per-job CPU/memory: ECS Fargate must use a discrete pair, so we
        # round up to the nearest valid combination via the task def's
        # registered values; per-task tuning is handled by registering
        # additional task definitions (left for a follow-up).

        try:
            response = self.ecs.run_task(
                cluster=self.cluster,
                taskDefinition=self.task_definition,
                count=1,
                launchType="FARGATE",
                platformVersion="LATEST",
                propagateTags="TASK_DEFINITION",
                overrides={"containerOverrides": [container_override]},
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": self.subnets,
                        "securityGroups": self.security_groups,
                        "assignPublicIp": "DISABLED",
                    }
                },
                tags=[
                    {"key": "job-id", "value": job_id},
                    {"key": "retry", "value": str(retry_count)},
                    {"key": "app", "value": "dhp-spark"},
                ],
                startedBy=f"dhp-orchestrator/{job_id[:8]}",
            )
        except ClientError as e:
            logger.error("RunTask failed for job_id=%s: %s", job_id, e)
            raise

        failures = response.get("failures") or []
        if failures:
            raise RuntimeError(f"ECS RunTask failures: {failures}")

        tasks = response.get("tasks") or []
        if not tasks:
            raise RuntimeError("ECS RunTask returned no tasks")

        task_arn = tasks[0]["taskArn"]
        logger.info("Launched ECS task for job_id=%s arn=%s", job_id, task_arn)
        return task_arn

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    def delete_spark_job(self, job_id: str) -> bool:
        """Stop all running ECS tasks tagged with job-id=<job_id>."""
        try:
            arns = self._list_running_tasks_for_job(job_id)
        except ClientError as e:
            logger.error("ListTasks failed for job_id=%s: %s", job_id, e)
            raise

        if not arns:
            logger.warning("No ECS tasks found for job_id=%s", job_id)
            return False

        for arn in arns:
            try:
                self.ecs.stop_task(
                    cluster=self.cluster,
                    task=arn,
                    reason=f"User cancelled job {job_id}",
                )
                logger.info("Stopped ECS task: %s", arn)
            except ClientError as e:
                logger.error("StopTask failed for arn=%s: %s", arn, e)
        return True

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Return the latest task status for the given job_id."""
        arns = self._list_tasks_for_job(job_id)
        if not arns:
            return None

        described = self.ecs.describe_tasks(cluster=self.cluster, tasks=arns)
        tasks = described.get("tasks") or []
        if not tasks:
            return None

        # Sort by createdAt descending; fallback to epoch for tasks missing it.
        epoch = datetime.fromtimestamp(0, tz=timezone.utc)
        tasks.sort(key=lambda t: t.get("createdAt") or epoch, reverse=True)
        latest = tasks[0]

        return {
            "task_arn": latest["taskArn"],
            "last_status": latest.get("lastStatus"),
            "desired_status": latest.get("desiredStatus"),
            "started_at": _iso(latest.get("startedAt")),
            "stopped_at": _iso(latest.get("stoppedAt")),
            "stop_code": latest.get("stopCode"),
            "stopped_reason": latest.get("stoppedReason"),
            "exit_code": _exit_code(latest, self.container_name),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _list_tasks_for_job(self, job_id: str) -> list[str]:
        # ECS doesn't filter ListTasks by tag, so we paginate by startedBy
        # which we set to "dhp-orchestrator/<job_id_prefix>".
        prefix = f"dhp-orchestrator/{job_id[:8]}"
        arns: list[str] = []
        for desired in ("RUNNING", "STOPPED"):
            paginator = self.ecs.get_paginator("list_tasks")
            for page in paginator.paginate(
                cluster=self.cluster, startedBy=prefix, desiredStatus=desired
            ):
                arns.extend(page.get("taskArns", []))
        return arns

    def _list_running_tasks_for_job(self, job_id: str) -> list[str]:
        prefix = f"dhp-orchestrator/{job_id[:8]}"
        arns: list[str] = []
        paginator = self.ecs.get_paginator("list_tasks")
        for page in paginator.paginate(
            cluster=self.cluster, startedBy=prefix, desiredStatus="RUNNING"
        ):
            arns.extend(page.get("taskArns", []))
        return arns


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _exit_code(task: dict, container_name: str) -> Optional[int]:
    for c in task.get("containers", []):
        if c.get("name") == container_name:
            return c.get("exitCode")
    return None
