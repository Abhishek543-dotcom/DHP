"""
Shared structured-logging + request-id middleware for DHP FastAPI services.

Usage in main.py:

    from app.logging_config import configure_logging, RequestIDMiddleware

    configure_logging(service="job-service")
    app = FastAPI(...)
    app.add_middleware(RequestIDMiddleware)
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

from pythonjsonlogger import jsonlogger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
job_id_ctx: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


class _ContextFilter(logging.Filter):
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
    handler.addFilter(_ContextFilter(service=service))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for noisy in ("botocore", "boto3", "urllib3", "aiokafka.consumer", "aiokafka.producer"):
        logging.getLogger(noisy).setLevel("WARNING")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign or propagate a request id, expose it on logs and the response header."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
