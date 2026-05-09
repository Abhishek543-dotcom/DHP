"""Lineage service entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ModuleNotFoundError:  # pragma: no cover
    Instrumentator = None

from app.config import get_settings
from app.db import close_db
from app.logging_config import RequestIDMiddleware, configure_logging
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import health, lineage

settings = get_settings()
configure_logging(service="lineage-service", level="DEBUG" if settings.debug else "INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Lineage Service...")
    yield
    logger.info("Shutting down Lineage Service...")
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Persists OpenLineage events from DHP Spark jobs.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

allowed_origins = [
    o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
app.add_middleware(RequestIDMiddleware)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

if Instrumentator is not None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
else:
    logger.warning("prometheus_fastapi_instrumentator not installed; /metrics disabled")

app.include_router(health.router)
app.include_router(lineage.router)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
