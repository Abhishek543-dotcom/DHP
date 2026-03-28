from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy", "service": "job-service"}


@router.get("/health/ready")
async def readiness_check():
    """Readiness check (can include DB/Kafka connectivity checks)."""
    return {"status": "ready", "service": "job-service"}

