"""Unit tests for storage-service. boto3/S3 calls are mocked via a fake client."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.s3_client import S3Client, get_s3_client

API_HEADERS = {"X-API-Key": "dev-api-key-change-me"}


@pytest.fixture
def fake_s3():
    s3 = MagicMock(spec=S3Client)
    s3.list_buckets.return_value = [
        {"name": "lakehouse-warehouse", "creation_date": datetime.now(timezone.utc).isoformat()},
    ]
    s3.create_bucket.return_value = {"bucket": "new-bucket", "status": "created"}
    s3.list_objects.return_value = {
        "bucket": "lakehouse-warehouse",
        "prefix": "",
        "objects": [
            {"key": "a.parquet", "size": 100, "last_modified": "2026-01-01T00:00:00", "etag": "abc"}
        ],
        "total": 1,
        "is_truncated": False,
        "next_continuation_token": None,
    }
    s3.generate_presigned_url.return_value = "https://example.com/signed"
    s3.delete_object.return_value = True
    return s3


@pytest.fixture
def client(fake_s3):
    app.dependency_overrides[get_s3_client] = lambda: fake_s3
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestLiveness:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_readiness_ok(self, client):
        from unittest.mock import AsyncMock
        with patch("app.routers.health._check_s3", new=AsyncMock(return_value=(True, None))):
            r = client.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_readiness_failure(self, client):
        from unittest.mock import AsyncMock
        with patch("app.routers.health._check_s3", new=AsyncMock(return_value=(False, "denied"))):
            r = client.get("/health/ready")
        assert r.status_code == 503


class TestBuckets:
    def test_list_requires_auth(self, client):
        assert client.get("/api/v1/storage/buckets").status_code == 401

    def test_list_buckets(self, client):
        r = client.get("/api/v1/storage/buckets", headers=API_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["buckets"][0]["name"] == "lakehouse-warehouse"

    def test_create_bucket(self, client, fake_s3):
        r = client.post(
            "/api/v1/storage/buckets",
            json={"name": "new-bucket"},
            headers=API_HEADERS,
        )
        assert r.status_code == 201
        fake_s3.create_bucket.assert_called_once_with("new-bucket")


class TestObjects:
    def test_list_objects(self, client):
        r = client.get(
            "/api/v1/storage/buckets/lakehouse-warehouse/objects",
            headers=API_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_list_objects_404(self, client, fake_s3):
        fake_s3.list_objects.return_value = None
        r = client.get(
            "/api/v1/storage/buckets/missing/objects",
            headers=API_HEADERS,
        )
        assert r.status_code == 404

    def test_presigned_url(self, client, fake_s3):
        r = client.post(
            "/api/v1/storage/buckets/b/presigned-url",
            json={"object_key": "k", "operation": "download"},
            headers=API_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["url"] == "https://example.com/signed"
        fake_s3.generate_presigned_url.assert_called_once()
