"""Custom Prometheus business metrics for metadata-service."""

from __future__ import annotations

from prometheus_client import Counter, Gauge

CATALOG_WRITES_TOTAL = Counter(
    "dhp_catalog_writes_total",
    "Catalog write operations (database/table CRUD).",
    labelnames=("entity", "op", "outcome"),  # entity: database|table; op: create|update|drop
)

CATALOG_DATABASES = Gauge(
    "dhp_catalog_databases",
    "Number of databases tracked in the DHP metadata catalog.",
)

CATALOG_TABLES = Gauge(
    "dhp_catalog_tables",
    "Number of tables tracked in the DHP metadata catalog.",
)

CATALOG_GLUE_SYNC_TOTAL = Counter(
    "dhp_catalog_glue_sync_total",
    "Glue write-through attempts from the metadata-service.",
    labelnames=("op", "outcome"),  # op: create_table|update_table|drop_table; outcome: success|skipped|error
)


__all__ = [
    "CATALOG_WRITES_TOTAL",
    "CATALOG_DATABASES",
    "CATALOG_TABLES",
    "CATALOG_GLUE_SYNC_TOTAL",
]
