"""Custom Prometheus business metrics for log-service."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

LOG_QUERIES_TOTAL = Counter(
    "dhp_log_queries_total",
    "Log queries handled by the log service.",
    labelnames=("source", "outcome"),  # source: range|stream
)

LOKI_ERRORS_TOTAL = Counter(
    "dhp_loki_errors_total",
    "Errors raised when calling Loki upstream.",
)

LOG_QUERY_SECONDS = Histogram(
    "dhp_log_query_seconds",
    "Wall-clock seconds for a log range query.",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


__all__ = ["LOG_QUERIES_TOTAL", "LOKI_ERRORS_TOTAL", "LOG_QUERY_SECONDS"]
