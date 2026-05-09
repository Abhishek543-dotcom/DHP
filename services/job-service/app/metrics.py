"""Custom Prometheus business metrics for job-service.

Metrics register on the default ``prometheus_client`` registry and are
exposed automatically by ``prometheus_fastapi_instrumentator`` at
``/metrics``.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

JOBS_SUBMITTED_TOTAL = Counter(
    "dhp_jobs_submitted_total",
    "Total jobs accepted by the job-service API.",
    labelnames=("job_type", "submitted_by"),
)

JOBS_QUEUED_TOTAL = Counter(
    "dhp_jobs_queued_total",
    "Jobs successfully published to Kafka after acceptance.",
    labelnames=("job_type",),
)

JOBS_FAILED_TOTAL = Counter(
    "dhp_jobs_failed_total",
    "Jobs that reached a terminal failure state (FAILED or DEAD).",
    labelnames=("reason",),
)

JOBS_COMPLETED_TOTAL = Counter(
    "dhp_jobs_completed_total",
    "Jobs reaching a terminal success state.",
    labelnames=("job_type",),
)

JOBS_ACTIVE = Gauge(
    "dhp_jobs_active",
    "Jobs currently in non-terminal states (PENDING|QUEUED|RUNNING). "
    "Sampled on every status update so the orchestrator + API agree.",
)

JOB_SUBMISSION_SECONDS = Histogram(
    "dhp_job_submission_seconds",
    "Wall-clock seconds for the job-service create_job API path.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

JOB_RETRIES_TOTAL = Counter(
    "dhp_job_retries_total",
    "Job retries scheduled by update_job_status.",
)


__all__ = [
    "JOBS_SUBMITTED_TOTAL",
    "JOBS_QUEUED_TOTAL",
    "JOBS_FAILED_TOTAL",
    "JOBS_COMPLETED_TOTAL",
    "JOBS_ACTIVE",
    "JOB_SUBMISSION_SECONDS",
    "JOB_RETRIES_TOTAL",
]
