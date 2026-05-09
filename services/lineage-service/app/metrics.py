"""Custom Prometheus business metrics for lineage-service."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

LINEAGE_EVENTS_TOTAL = Counter(
    "dhp_lineage_events_total",
    "OpenLineage events ingested by the lineage service.",
    labelnames=("event_type", "outcome"),
)

LINEAGE_GRAPH_QUERIES_TOTAL = Counter(
    "dhp_lineage_graph_queries_total",
    "Upstream/downstream graph queries served.",
    labelnames=("direction", "outcome"),
)

LINEAGE_INGEST_SECONDS = Histogram(
    "dhp_lineage_ingest_seconds",
    "Wall-clock seconds for OpenLineage event ingest.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


__all__ = [
    "LINEAGE_EVENTS_TOTAL",
    "LINEAGE_GRAPH_QUERIES_TOTAL",
    "LINEAGE_INGEST_SECONDS",
]
