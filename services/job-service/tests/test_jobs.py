"""
Tests for Job Service API endpoints.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import JobStatus
from app.models.job import JobListResponse, JobResponse
from app.routers.jobs import get_job_service

API_HEADERS = {"X-API-Key": "dev-api-key-change-me"}
INTERNAL_HEADERS = {"X-Internal-Token": "dev-internal-token-change-me"}


def build_job_response(
    job_id: str = "job-123",
    status: JobStatus = JobStatus.QUEUED,
    message: str | None = None,
) -> JobResponse:
    return JobResponse(
        job_id=job_id,
        job_name="test_etl_job",
        job_type="spark_etl",
        status=status,
        spark_config={"spark.executor.memory": "2g"},
        entrypoint="s3://lakehouse-scripts/etl/test.py",
        arguments=["--date", "2026-03-24"],
        database_name="test_db",
        table_name="test_table",
        submitted_by="test_user",
        submitted_at=datetime.now(timezone.utc),
        max_retries=2,
        message=message,
    )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestHealthEndpoints:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_readiness(self, client):
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"


class TestJobEndpoints:
    SAMPLE_JOB_PAYLOAD = {
        "job_name": "test_etl_job",
        "job_type": "spark_etl",
        "entrypoint": "s3://lakehouse-scripts/etl/test.py",
        "arguments": ["--date", "2026-03-24"],
        "spark_config": {
            "spark.executor.memory": "2g",
            "spark.executor.cores": 1,
        },
        "database_name": "test_db",
        "table_name": "test_table",
        "submitted_by": "test_user",
        "max_retries": 2,
    }

    def test_submit_job(self, client):
        """Job submission should return 202 and include job_id."""
        mock_service = AsyncMock()
        mock_service.create_job.return_value = build_job_response(
            message="Job accepted and queued for execution"
        )
        app.dependency_overrides[get_job_service] = lambda: mock_service

        response = client.post(
            "/api/v1/jobs/",
            json=self.SAMPLE_JOB_PAYLOAD,
            headers=API_HEADERS,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-123"
        assert data["status"] == "QUEUED"
        mock_service.create_job.assert_awaited_once()

    def test_submit_job_requires_api_key(self, client):
        response = client.post("/api/v1/jobs/", json=self.SAMPLE_JOB_PAYLOAD)
        assert response.status_code == 401

    def test_submit_job_validation_error(self, client):
        """Invalid payload should return 422."""
        response = client.post(
            "/api/v1/jobs/",
            json={"invalid": "payload"},
            headers=API_HEADERS,
        )
        assert response.status_code == 422

    def test_get_nonexistent_job(self, client):
        """Fetching unknown job_id should return 404."""
        mock_service = AsyncMock()
        mock_service.get_job.return_value = None
        app.dependency_overrides[get_job_service] = lambda: mock_service

        response = client.get("/api/v1/jobs/not-found", headers=API_HEADERS)
        assert response.status_code == 404

    def test_list_jobs_default_pagination(self, client):
        """List endpoint should apply default pagination params."""
        mock_service = AsyncMock()
        mock_service.list_jobs.return_value = JobListResponse(
            total=0,
            page=1,
            page_size=20,
            jobs=[],
        )
        app.dependency_overrides[get_job_service] = lambda: mock_service

        response = client.get("/api/v1/jobs/", headers=API_HEADERS)
        assert response.status_code == 200
        payload = response.json()
        assert payload["page"] == 1
        assert payload["page_size"] == 20
        mock_service.list_jobs.assert_awaited_once_with(
            page=1,
            page_size=20,
            status=None,
            job_type=None,
            submitted_by=None,
        )

    def test_status_update_requires_internal_token(self, client):
        mock_service = AsyncMock()
        mock_service.update_job_status.return_value = build_job_response(
            status=JobStatus.RUNNING
        )
        app.dependency_overrides[get_job_service] = lambda: mock_service

        response = client.put(
            "/api/v1/jobs/job-123/status",
            json={"status": "RUNNING"},
            headers=API_HEADERS,
        )
        assert response.status_code == 401

        response = client.put(
            "/api/v1/jobs/job-123/status",
            json={"status": "RUNNING"},
            headers=INTERNAL_HEADERS,
        )
        assert response.status_code == 200


class TestJobModels:
    def test_job_create_request_valid(self):
        from app.models.job import JobCreateRequest

        request = JobCreateRequest(
            job_name="test_job",
            job_type="spark_etl",
            entrypoint="s3://scripts/test.py",
            submitted_by="tester",
        )
        assert request.job_name == "test_job"
        assert request.max_retries == 3

    def test_job_create_request_invalid_type(self):
        from app.models.job import JobCreateRequest

        with pytest.raises(Exception):
            JobCreateRequest(
                job_name="test_job",
                job_type="invalid_type",
                entrypoint="s3://scripts/test.py",
                submitted_by="tester",
            )

    def test_job_status_enum(self):
        from app.models.enums import JobStatus

        assert JobStatus.PENDING.value == "PENDING"
        assert JobStatus.RUNNING.value == "RUNNING"
        assert JobStatus.DEAD.value == "DEAD"
