from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Storage Service configuration."""

    app_name: str = "Lakehouse Storage Service"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "local"
    cors_allowed_origins: str = (
        "http://localhost:3000,http://localhost:8000,http://localhost:8001,"
        "http://localhost:8002,http://localhost:8003,http://localhost:8004"
    )
    api_key: str = "dev-api-key-change-me"

    # S3 / MinIO
    # When running on AWS, leave s3_endpoint empty and omit access/secret keys —
    # boto3 will use the IAM task role from IMDS automatically.
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_region: str = "us-east-1"
    # MinIO requires path-style addressing; real AWS S3 supports virtual-host style.
    s3_force_path_style: bool = False

    # Presigned URL defaults
    presigned_url_expiry: int = 3600  # seconds

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
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
