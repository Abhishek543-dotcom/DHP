"""Custom Prometheus business metrics for the orchestrator."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

ORCHESTRATOR_LAUNCHES_TOTAL = Counter(
    "dhp_orchestrator_launches_total",
    "Spark job launches attempted by the orchestrator.",
    labelnames=("outcome",),  # success | retry | dlq
)

ORCHESTRATOR_RETRIES_TOTAL = Counter(
    "dhp_orchestrator_retries_total",
    "Per-attempt orchestrator launch retries.",
)

ORCHESTRATOR_DLQ_TOTAL = Counter(
    "dhp_orchestrator_dlq_total",
    "Job events forwarded to the DLQ topic after retry budget exhaustion.",
)

ECS_RUNTASK_SECONDS = Histogram(
    "dhp_ecs_runtask_seconds",
    "Wall-clock seconds for a single ECS RunTask call (per attempt).",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

ORCHESTRATOR_CANCELLATIONS_TOTAL = Counter(
    "dhp_orchestrator_cancellations_total",
    "Cancellation events processed by the orchestrator.",
    labelnames=("outcome",),  # success | error
)


__all__ = [
    "ORCHESTRATOR_LAUNCHES_TOTAL",
    "ORCHESTRATOR_RETRIES_TOTAL",
    "ORCHESTRATOR_DLQ_TOTAL",
    "ECS_RUNTASK_SECONDS",
    "ORCHESTRATOR_CANCELLATIONS_TOTAL",
]
