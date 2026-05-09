"""AWS Glue Data Catalog client for Iceberg write-through.

The metadata-service writes catalog entries to its own Postgres tables AND
mirrors them to AWS Glue so external engines (Athena, EMR, Snowflake) can
query the same Iceberg datasets. The DHP catalog stays the source of truth;
Glue failures log a warning but never fail the API.

Iceberg table registration in Glue requires a marker table with two
properties:
  table_type        = "ICEBERG"
  metadata_location = "s3://.../metadata/<latest>.metadata.json"

Spark jobs write the actual metadata.json files via the iceberg-aws-bundle
GlueCatalog impl; this client only ever creates/drops the marker entries.
"""

from __future__ import annotations

import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings
from app.metrics import CATALOG_GLUE_SYNC_TOTAL

logger = logging.getLogger(__name__)


class GlueCatalogClient:
    """Thin wrapper around the boto3 ``glue`` client.

    All public methods are no-ops when ``glue_catalog_database`` is empty,
    keeping local development decoupled from AWS.
    """

    def __init__(self, database: Optional[str] = None, region: Optional[str] = None):
        settings = get_settings()
        self.database = database if database is not None else settings.glue_catalog_database
        self.region = region or settings.aws_region
        self._client = None
        if self.database:
            try:
                self._client = boto3.client("glue", region_name=self.region)
            except Exception:
                logger.exception(
                    "Failed to construct Glue client; write-through disabled"
                )
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None and bool(self.database)

    def register_table(
        self,
        *,
        table_name: str,
        location: str,
        metadata_location: Optional[str] = None,
    ) -> None:
        """Create (or update) the Iceberg marker entry in Glue.

        ``location`` is the table's S3 prefix (s3://bucket/db/table/).
        ``metadata_location`` is the latest metadata JSON; if unknown at
        creation time (Spark hasn't written the table yet), it is omitted —
        the first writer's GlueCatalog impl will populate it.
        """
        if not self.enabled:
            CATALOG_GLUE_SYNC_TOTAL.labels(op="create_table", outcome="skipped").inc()
            return

        params = {
            "DatabaseName": self.database,
            "TableInput": {
                "Name": table_name,
                "TableType": "EXTERNAL_TABLE",
                "Parameters": {
                    "table_type": "ICEBERG",
                    **({"metadata_location": metadata_location} if metadata_location else {}),
                },
                "StorageDescriptor": {
                    "Location": location.rstrip("/") + "/",
                    "Columns": [],  # Iceberg owns schema; Glue stores marker only.
                },
            },
        }
        try:
            self._client.create_table(**params)  # type: ignore[union-attr]
            CATALOG_GLUE_SYNC_TOTAL.labels(op="create_table", outcome="success").inc()
            logger.info("Glue: registered table %s.%s", self.database, table_name)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "AlreadyExistsException":
                # Idempotent path: table already registered. Optionally update.
                CATALOG_GLUE_SYNC_TOTAL.labels(op="create_table", outcome="exists").inc()
                logger.info("Glue: table %s.%s already exists", self.database, table_name)
            else:
                CATALOG_GLUE_SYNC_TOTAL.labels(op="create_table", outcome="error").inc()
                logger.warning(
                    "Glue: create_table %s.%s failed: %s; DHP catalog unaffected",
                    self.database, table_name, e,
                )
        except Exception:
            CATALOG_GLUE_SYNC_TOTAL.labels(op="create_table", outcome="error").inc()
            logger.exception(
                "Glue: unexpected failure registering %s.%s; DHP catalog unaffected",
                self.database, table_name,
            )

    def drop_table(self, *, table_name: str) -> None:
        if not self.enabled:
            CATALOG_GLUE_SYNC_TOTAL.labels(op="drop_table", outcome="skipped").inc()
            return
        try:
            self._client.delete_table(  # type: ignore[union-attr]
                DatabaseName=self.database, Name=table_name
            )
            CATALOG_GLUE_SYNC_TOTAL.labels(op="drop_table", outcome="success").inc()
            logger.info("Glue: deleted table %s.%s", self.database, table_name)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "EntityNotFoundException":
                CATALOG_GLUE_SYNC_TOTAL.labels(op="drop_table", outcome="not_found").inc()
                return
            CATALOG_GLUE_SYNC_TOTAL.labels(op="drop_table", outcome="error").inc()
            logger.warning(
                "Glue: delete_table %s.%s failed: %s", self.database, table_name, e
            )
        except Exception:
            CATALOG_GLUE_SYNC_TOTAL.labels(op="drop_table", outcome="error").inc()
            logger.exception("Glue: unexpected failure dropping %s.%s", self.database, table_name)


_singleton: Optional[GlueCatalogClient] = None


def get_glue_client() -> GlueCatalogClient:
    global _singleton
    if _singleton is None:
        _singleton = GlueCatalogClient()
    return _singleton
