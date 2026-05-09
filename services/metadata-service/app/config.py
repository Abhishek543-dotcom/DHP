from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Metadata Service configuration."""

    app_name: str = "Lakehouse Metadata Service"
    app_version: str = "1.0.0"
    debug: bool = False
    cors_allowed_origins: str = (
        "http://localhost:3000,http://localhost:8000,http://localhost:8001,"
        "http://localhost:8002,http://localhost:8003,http://localhost:8004"
    )
    api_key: str = "dev-api-key-change-me"

    # Database
    database_url: str = "postgresql+asyncpg://lakehouse:dev-db-password-change-me@localhost:5432/lakehouse"
    auto_create_tables: bool = False

    # Object Storage
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "dev-access-key-change-me"
    s3_secret_key: str = "dev-secret-key-change-me"
    s3_warehouse_bucket: str = "lakehouse-warehouse"

    # AWS Glue Data Catalog (Iceberg integration). When empty (local /
    # docker-compose), Glue write-through is skipped and DHP-internal Postgres
    # remains the sole source of truth.
    glue_catalog_database: str = ""
    aws_region: str = "us-east-1"

    # Redis (rate limiting)
    redis_url: str = "redis://localhost:6379"

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, str) and value.strip().lower() in {
            "release",
            "prod",
            "production",
        }:
            return False
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()

