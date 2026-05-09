import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test envs
    Instrumentator = None

from app.config import get_settings
from app.db.session import init_db, close_db
from app.logging_config import RequestIDMiddleware, configure_logging
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import health, jobs, schedules
from app.services.kafka_client import close_kafka_producer

settings = get_settings()

configure_logging(service="job-service", level="DEBUG" if settings.debug else "INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Job Service...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Job Service...")
    await close_kafka_producer()
    await close_db()
    logger.info("Cleanup complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for managing Spark jobs in DataHarbour Project (DHP)",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

allowed_origins = [
    origin.strip()
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Internal-Token"],
)
app.add_middleware(RequestIDMiddleware)

# Rate limiting (slowapi, Redis-backed). Per-route limits applied via decorator.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

if Instrumentator is not None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
else:
    logger.warning("prometheus_fastapi_instrumentator not installed; /metrics disabled")

# Register routers
app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(schedules.router)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }

