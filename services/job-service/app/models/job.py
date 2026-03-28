from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import JobStatus, JobType


class SparkConfig(BaseModel):
    """Spark configuration for a job."""
    executor_memory: str = Field(default="4g", alias="spark.executor.memory")
    executor_cores: int = Field(default=2, alias="spark.executor.cores")
    executor_instances: int = Field(default=2, alias="spark.executor.instances")
    extra_config: dict = Field(default_factory=dict, description="Additional Spark config key-value pairs")

    model_config = ConfigDict(populate_by_name=True)


class JobCreateRequest(BaseModel):
    """Request model for creating a new Spark job."""
    job_name: str = Field(..., min_length=1, max_length=255, description="Human-readable job name")
    job_type: JobType = Field(..., description="Type of Spark job")
    entrypoint: str = Field(..., description="Main script or class path (e.g., s3://scripts/etl/transform.py)")
    arguments: list[str] = Field(default_factory=list, description="Runtime arguments for the job")
    spark_config: dict = Field(default_factory=dict, description="Spark configuration overrides")
    database_name: Optional[str] = Field(None, description="Target database name")
    table_name: Optional[str] = Field(None, description="Target table name")
    submitted_by: str = Field(..., description="User or service submitting the job")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_name": "daily_sales_etl",
                "job_type": "spark_etl",
                "entrypoint": "s3://lakehouse-scripts/etl/sales_transform.py",
                "arguments": ["--date", "2026-03-22", "--mode", "incremental"],
                "spark_config": {
                    "spark.executor.memory": "4g",
                    "spark.executor.cores": 2,
                    "spark.executor.instances": 4,
                },
                "database_name": "sales_db",
                "table_name": "transactions",
                "submitted_by": "data_engineering_team",
                "max_retries": 3,
            },
        }
    )

class JobResponse(BaseModel):
    """Response model for job operations."""
    job_id: str
    job_name: str
    job_type: str
    status: JobStatus
    spark_config: dict = Field(default_factory=dict)
    entrypoint: str
    arguments: list[str] = Field(default_factory=list)
    database_name: Optional[str] = None
    table_name: Optional[str] = None
    container_id: Optional[str] = None
    submitted_by: str
    submitted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    message: Optional[str] = None


class JobListResponse(BaseModel):
    """Response model for listing jobs."""
    total: int
    page: int
    page_size: int
    jobs: list[JobResponse]


class JobStatusUpdate(BaseModel):
    """Request model for updating job status (internal/callback)."""
    status: JobStatus
    container_id: Optional[str] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None


class JobLogsResponse(BaseModel):
    """Response model for job logs."""
    job_id: str
    log_count: int
    entries: list[dict]

