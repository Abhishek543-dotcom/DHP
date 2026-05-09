"""Custom Prometheus business metrics for storage-service."""

from __future__ import annotations

from prometheus_client import Counter

STORAGE_PRESIGNED_URLS_TOTAL = Counter(
    "dhp_storage_presigned_urls_total",
    "Presigned URLs minted by the storage service.",
    labelnames=("operation",),  # get_object, put_object
)

STORAGE_BUCKET_OPS_TOTAL = Counter(
    "dhp_storage_bucket_ops_total",
    "S3 bucket-level operations performed via the storage API.",
    labelnames=("op", "outcome"),  # op: create/list/list_objects/delete_object
)


__all__ = ["STORAGE_PRESIGNED_URLS_TOTAL", "STORAGE_BUCKET_OPS_TOTAL"]
