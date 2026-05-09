import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

import httpx
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Job
from app.metrics import (
    JOBS_SUBMITTED_TOTAL,
    JOBS_QUEUED_TOTAL,
    JOBS_FAILED_TOTAL,
    JOBS_COMPLETED_TOTAL,
    JOBS_ACTIVE,
    JOB_SUBMISSION_SECONDS,
    JOB_RETRIES_TOTAL,
)
from app.models.enums import JobStatus
from app.models.job import (
    JobCreateRequest,
    JobResponse,
    JobListResponse,
    JobStatusUpdate,
)
from app.services.kafka_client import send_job_event

logger = logging.getLogger(__name__)
settings = get_settings()


class JobService:
    """Business logic for job management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, request: JobCreateRequest) -> JobResponse:
        """Create a new job and enqueue it for execution."""
        with JOB_SUBMISSION_SECONDS.time():
            job_id = str(uuid4())

            JOBS_SUBMITTED_TOTAL.labels(
                job_type=request.job_type.value,
                submitted_by=request.submitted_by or "unknown",
            ).inc()

            # Create job record in database
            job = Job(
                job_id=job_id,
                job_name=request.job_name,
                job_type=request.job_type.value,
                status=JobStatus.PENDING.value,
                spark_config=request.spark_config,
                entrypoint=request.entrypoint,
                arguments=request.arguments,
                database_name=request.database_name,
                table_name=request.table_name,
                submitted_by=request.submitted_by,
                max_retries=request.max_retries,
            )

            self.db.add(job)
            await self.db.flush()

            # Send job to Kafka for orchestration
            job_event = {
                "job_id": job_id,
                "job_name": request.job_name,
                "job_type": request.job_type.value,
                "entrypoint": request.entrypoint,
                "arguments": request.arguments,
                "spark_config": request.spark_config,
                "database_name": request.database_name,
                "table_name": request.table_name,
                "max_retries": request.max_retries,
                "submitted_by": request.submitted_by,
            }

            queued = False
            queue_message = "Job accepted and queued for execution"

            try:
                await send_job_event(
                    topic=settings.kafka_job_topic,
                    job_id=job_id,
                    event=job_event,
                )
                job.status = JobStatus.QUEUED.value
                queued = True
                JOBS_QUEUED_TOTAL.labels(job_type=request.job_type.value).inc()
                JOBS_ACTIVE.inc()
                await self.db.flush()
            except Exception as e:
                logger.error(f"Failed to enqueue job {job_id}: {e}")
                JOBS_FAILED_TOTAL.labels(reason="kafka_enqueue_error").inc()
                job.status = JobStatus.PENDING.value
                job.error_message = "Kafka enqueue failed; job is still pending"
                queue_message = (
                    "Job accepted but not queued due to a messaging error. "
                    "Please retry once Kafka is healthy."
                )
                await self.db.flush()

            return JobResponse(
                job_id=job_id,
                job_name=job.job_name,
                job_type=job.job_type,
                status=JobStatus(job.status),
                spark_config=job.spark_config,
                entrypoint=job.entrypoint,
                arguments=job.arguments,
                database_name=job.database_name,
                table_name=job.table_name,
                submitted_by=job.submitted_by,
                submitted_at=job.submitted_at,
                error_message=job.error_message if not queued else None,
                max_retries=job.max_retries,
                message=queue_message,
            )

    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Get a job by ID."""
        result = await self.db.execute(
            select(Job).where(Job.job_id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            return None

        return JobResponse(
            job_id=str(job.job_id),
            job_name=job.job_name,
            job_type=job.job_type,
            status=JobStatus(job.status),
            spark_config=job.spark_config,
            entrypoint=job.entrypoint,
            arguments=job.arguments,
            database_name=job.database_name,
            table_name=job.table_name,
            container_id=job.container_id,
            submitted_by=job.submitted_by,
            submitted_at=job.submitted_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
        )

    async def list_jobs(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        submitted_by: Optional[str] = None,
    ) -> JobListResponse:
        """List jobs with pagination and filters."""
        query = select(Job)

        if status:
            query = query.where(Job.status == status)
        if job_type:
            query = query.where(Job.job_type == job_type)
        if submitted_by:
            query = query.where(Job.submitted_by == submitted_by)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.order_by(desc(Job.submitted_at))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        jobs = result.scalars().all()

        return JobListResponse(
            total=total,
            page=page,
            page_size=page_size,
            jobs=[
                JobResponse(
                    job_id=str(j.job_id),
                    job_name=j.job_name,
                    job_type=j.job_type,
                    status=JobStatus(j.status),
                    spark_config=j.spark_config,
                    entrypoint=j.entrypoint,
                    arguments=j.arguments,
                    database_name=j.database_name,
                    table_name=j.table_name,
                    container_id=j.container_id,
                    submitted_by=j.submitted_by,
                    submitted_at=j.submitted_at,
                    started_at=j.started_at,
                    completed_at=j.completed_at,
                    error_message=j.error_message,
                    retry_count=j.retry_count,
                    max_retries=j.max_retries,
                )
                for j in jobs
            ],
        )

    async def update_job_status(
        self, job_id: str, update: JobStatusUpdate
    ) -> Optional[JobResponse]:
        """Update job status (used by orchestrator callbacks)."""
        result = await self.db.execute(
            select(Job).where(Job.job_id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            return None

        job.status = update.status.value

        if update.container_id:
            job.container_id = update.container_id

        if update.error_message:
            job.error_message = update.error_message

        if update.status == JobStatus.RUNNING:
            job.started_at = datetime.utcnow()
        elif update.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD):
            job.completed_at = datetime.utcnow()
            JOBS_ACTIVE.dec()
            if update.status == JobStatus.SUCCESS:
                JOBS_COMPLETED_TOTAL.labels(job_type=job.job_type).inc()
            elif update.status == JobStatus.DEAD:
                JOBS_FAILED_TOTAL.labels(reason="max_retries_exceeded").inc()
            elif update.status == JobStatus.FAILED:
                # NOTE: only counts as failed when retries are exhausted below;
                # transient FAILED -> QUEUED retries are not counted here.
                pass
            elif update.status == JobStatus.CANCELLED:
                JOBS_FAILED_TOTAL.labels(reason="cancelled").inc()

        # Handle retry logic for failed jobs
        if update.status == JobStatus.FAILED and job.retry_count < job.max_retries:
            job.retry_count += 1
            job.status = JobStatus.QUEUED.value
            JOB_RETRIES_TOTAL.inc()
            # job stays active across the retry; revert the dec() above
            JOBS_ACTIVE.inc()
            # Re-enqueue
            job_event = {
                "job_id": str(job.job_id),
                "job_name": job.job_name,
                "job_type": job.job_type,
                "entrypoint": job.entrypoint,
                "arguments": job.arguments,
                "spark_config": job.spark_config,
                "database_name": job.database_name,
                "table_name": job.table_name,
                "max_retries": job.max_retries,
                "submitted_by": job.submitted_by,
                "retry": True,
                "retry_count": job.retry_count,
            }
            try:
                await send_job_event(
                    topic=settings.kafka_job_topic,
                    job_id=str(job.job_id),
                    event=job_event,
                )
                logger.info(f"Job {job_id} re-queued for retry ({job.retry_count}/{job.max_retries})")
            except Exception as e:
                logger.error(f"Failed to re-enqueue job {job_id}: {e}")
        elif update.status == JobStatus.FAILED and job.retry_count >= job.max_retries:
            job.status = JobStatus.DEAD.value
            JOBS_FAILED_TOTAL.labels(reason="max_retries_exceeded").inc()
            logger.warning(f"Job {job_id} exceeded max retries, marked as DEAD")

        await self.db.flush()

        return await self.get_job(str(job.job_id))

    async def cancel_job(self, job_id: str) -> Optional[JobResponse]:
        """Cancel a running or queued job."""
        result = await self.db.execute(
            select(Job).where(Job.job_id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            return None

        if job.status in (JobStatus.SUCCESS.value, JobStatus.DEAD.value, JobStatus.CANCELLED.value):
            logger.warning(f"Cannot cancel job {job_id} in terminal state: {job.status}")
            return await self.get_job(str(job.job_id))

        job.status = JobStatus.CANCELLED.value
        job.completed_at = datetime.utcnow()

        # Send cancellation event to orchestrator
        cancel_event = {
            "job_id": str(job.job_id),
            "action": "cancel",
            "container_id": job.container_id,
        }
        try:
            await send_job_event(
                topic=settings.kafka_job_status_topic,
                job_id=str(job.job_id),
                event=cancel_event,
            )
        except Exception as e:
            logger.error(f"Failed to send cancellation for job {job_id}: {e}")

        await self.db.flush()
        return await self.get_job(str(job.job_id))

    async def get_job_logs(
        self,
        job_id: str,
        source: str = "all",
        tail: int = 500,
    ) -> list[dict]:
        """Fetch logs from the log-service for the provided job."""
        url = f"{settings.log_service_url}/api/v1/logs/{job_id}"
        headers = {"X-API-Key": settings.log_service_api_key}
        params = {"source": source, "tail": tail}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
            payload = response.json()
            return payload.get("entries", [])
        except Exception as e:
            logger.error(f"Failed to fetch logs from log-service for job {job_id}: {e}")
            return []

