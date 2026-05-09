"""
Shared structured-logging setup for DHP services.

Emits JSON to stdout with: timestamp, level, logger, service, env, request_id (when set).
Use `configure_logging(service="job-service")` once at process startup.
"""
from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from typing import Optional

from pythonjsonlogger import jsonlogger

# Per-request context populated by the request-id middleware.
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
job_id_ctx: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


class ContextFilter(logging.Filter):
    """Inject request/job context into every record."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service
        self.environment = os.getenv("ENVIRONMENT", "local")

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service
        record.environment = self.environment
        record.request_id = request_id_ctx.get()
        record.job_id = job_id_ctx.get()
        return True


def configure_logging(*, service: str, level: str | int = "INFO") -> None:
    """Replace root logger handlers with a single JSON stdout handler."""
    if isinstance(level, str):
        level = level.upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "%(service)s %(environment)s %(request_id)s %(job_id)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    )
    handler.addFilter(ContextFilter(service=service))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Tame noisy libraries
    for noisy in ("botocore", "boto3", "urllib3", "aiokafka.consumer", "aiokafka.producer"):
        logging.getLogger(noisy).setLevel("WARNING")
