"""
Tests for Metadata Service API endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoints:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestDatabaseModels:
    def test_database_create_valid(self):
        from app.models import DatabaseCreateRequest

        req = DatabaseCreateRequest(
            db_name="test_db",
            owner="tester",
            description="Test database",
        )
        assert req.db_name == "test_db"

    def test_database_create_invalid_name(self):
        from app.models import DatabaseCreateRequest

        with pytest.raises(Exception):
            DatabaseCreateRequest(
                db_name="123-invalid",  # doesn't match pattern
                owner="tester",
            )

    def test_database_create_empty_name(self):
        from app.models import DatabaseCreateRequest

        with pytest.raises(Exception):
            DatabaseCreateRequest(db_name="", owner="tester")


class TestTableModels:
    def test_table_create_valid(self):
        from app.models import TableCreateRequest, ColumnSchema

        req = TableCreateRequest(
            table_name="transactions",
            schema_fields=[
                ColumnSchema(name="id", type="long", nullable=False),
                ColumnSchema(name="amount", type="decimal"),
            ],
        )
        assert req.table_name == "transactions"
        assert len(req.schema_fields) == 2

    def test_table_create_empty_schema(self):
        from app.models import TableCreateRequest

        with pytest.raises(Exception):
            TableCreateRequest(
                table_name="empty_table",
                schema_fields=[],  # min_length=1
            )

    def test_table_update_model(self):
        from app.models import TableUpdateRequest, ColumnSchema

        req = TableUpdateRequest(
            add_columns=[
                ColumnSchema(name="region", type="string"),
            ],
            drop_columns=["old_column"],
            rename_columns={"old_name": "new_name"},
            changed_by="tester",
        )
        assert len(req.add_columns) == 1
        assert "old_column" in req.drop_columns

