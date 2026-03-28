import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.enums import LogSource
from app.models.job import (
    JobCreateRequest,
    JobResponse,
    JobListResponse,
    JobStatusUpdate,
    JobLogsResponse,
)
from app.security import require_api_key, require_internal_token
from app.services.job_service import JobService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])


def get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    return JobService(db)


@router.post(
    "/",
    response_model=JobResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
async def submit_job(
    request: JobCreateRequest,
    svc: JobService = Depends(get_job_service),
):
    """
    Submit a new Spark job for execution.

    The job will be enqueued to Kafka and picked up by the orchestrator
    for container-based execution.
    """
    logger.info(f"Submitting job: {request.job_name} by {request.submitted_by}")
    job = await svc.create_job(request)
    return job


@router.get(
    "/",
    response_model=JobListResponse,
    dependencies=[Depends(require_api_key)],
)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    submitted_by: Optional[str] = Query(None, description="Filter by submitter"),
    svc: JobService = Depends(get_job_service),
):
    """List all jobs with optional filters and pagination."""
    return await svc.list_jobs(
        page=page,
        page_size=page_size,
        status=status,
        job_type=job_type,
        submitted_by=submitted_by,
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
):
    """Get job details by ID."""
    job = await svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.delete(
    "/{job_id}",
    status_code=200,
    response_model=JobResponse,
    dependencies=[Depends(require_api_key)],
)
async def cancel_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
):
    """Cancel a running or queued job."""
    job = await svc.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.put(
    "/{job_id}/status",
    response_model=JobResponse,
    dependencies=[Depends(require_internal_token)],
)
async def update_job_status(
    job_id: str,
    update: JobStatusUpdate,
    svc: JobService = Depends(get_job_service),
):
    """
    Update job status (internal endpoint for orchestrator callbacks).

    This endpoint is called by the Spark container entrypoint script
    when a job completes or fails.
    """
    job = await svc.update_job_status(job_id, update)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get(
    "/{job_id}/logs",
    response_model=JobLogsResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_job_logs(
    job_id: str,
    source: LogSource = Query(LogSource.ALL, description="Log source filter"),
    tail: int = Query(500, ge=1, le=10000, description="Number of log lines"),
    svc: JobService = Depends(get_job_service),
):
    """
    Get logs for a specific job by Job ID.

    Logs are retrieved from the centralized log store (Loki/ELK)
    and filtered by job_id label.
    """
    # Verify job exists
    job = await svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    log_entries = await svc.get_job_logs(
        job_id=job_id,
        source=source.value,
        tail=tail,
    )

    return JobLogsResponse(
        job_id=job_id,
        log_count=len(log_entries),
        entries=log_entries,
    )

