import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test envs
    Instrumentator = None

from app.config import get_settings
from app.db.session import init_db, close_db
from app.routers import health, jobs
from app.services.kafka_client import close_kafka_producer

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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

if Instrumentator is not None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
else:
    logger.warning("prometheus_fastapi_instrumentator not installed; /metrics disabled")

# Register routers
app.include_router(health.router)
app.include_router(jobs.router)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }

