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
from app.db import init_db, close_db
from app.db.models import CatalogDatabase, CatalogTable
from app.logging_config import RequestIDMiddleware, configure_logging
from app.metrics import CATALOG_DATABASES, CATALOG_TABLES
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import databases, health, tables

settings = get_settings()

configure_logging(service="metadata-service", level="DEBUG" if settings.debug else "INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Metadata Service...")
    await init_db()
    logger.info("Database initialized")
    await _seed_catalog_gauges()
    yield
    logger.info("Shutting down Metadata Service...")
    await close_db()


async def _seed_catalog_gauges() -> None:
    """Initialize the catalog gauges from current DB state.

    Without this, gauges would only track deltas from process start, missing
    pre-existing rows after a deploy/restart.
    """
    from sqlalchemy import func, select

    from app.db import async_session_factory

    try:
        async with async_session_factory() as session:
            db_count = (
                await session.execute(select(func.count()).select_from(CatalogDatabase))
            ).scalar() or 0
            tbl_count = (
                await session.execute(select(func.count()).select_from(CatalogTable))
            ).scalar() or 0
        CATALOG_DATABASES.set(db_count)
        CATALOG_TABLES.set(tbl_count)
        logger.info(
            "Seeded catalog gauges: databases=%d tables=%d", db_count, tbl_count
        )
    except Exception:
        logger.exception("Failed to seed catalog gauges; will track deltas only")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for managing lakehouse catalog - databases, tables, and schemas",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

allowed_origins = [
    origin.strip()
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
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
app.include_router(databases.router)
app.include_router(tables.router)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }




