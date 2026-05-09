"""Unit tests for log-service. All external dependencies (Loki, Redis) are mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.loki_client import LokiClient, get_loki_client
from app.main import app

API_HEADERS = {"X-API-Key": "dev-api-key-change-me"}


@pytest.fixture
def fake_loki():
    loki = AsyncMock(spec=LokiClient)
    loki.query_logs = AsyncMock(
        return_value=[
            {
                "timestamp": "2026-05-07T10:00:00",
                "message": "hello",
                "source": "stdout",
                "level": "INFO",
                "job_id": "job-1",
            }
        ]
    )
    return loki


@pytest.fixture
def client(fake_loki):
    app.dependency_overrides[get_loki_client] = lambda: fake_loki
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestLiveness:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "log-service"

    def test_readiness_when_loki_up(self, client):
        with patch("app.routers.health._check_loki", new=AsyncMock(return_value=(True, None))):
            r = client.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_readiness_when_loki_down(self, client):
        with patch("app.routers.health._check_loki", new=AsyncMock(return_value=(False, "boom"))):
            r = client.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "not_ready"


class TestLogQuery:
    def test_query_requires_api_key(self, client):
        r = client.get("/api/v1/logs/job-1")
        assert r.status_code == 401

    def test_query_returns_log_entries(self, client, fake_loki):
        r = client.get("/api/v1/logs/job-1?source=stdout&tail=100", headers=API_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["job_id"] == "job-1"
        assert body["source"] == "stdout"
        assert body["log_count"] == 1
        assert body["entries"][0]["message"] == "hello"
        fake_loki.query_logs.assert_awaited_once_with(job_id="job-1", source="stdout", tail=100)

    def test_query_empty_when_loki_returns_nothing(self, client, fake_loki):
        fake_loki.query_logs.return_value = []
        r = client.get("/api/v1/logs/no-such-job", headers=API_HEADERS)
        assert r.status_code == 200
        assert r.json()["log_count"] == 0
