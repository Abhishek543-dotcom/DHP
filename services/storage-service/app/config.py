from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Storage Service configuration."""

    app_name: str = "Lakehouse Storage Service"
    app_version: str = "1.0.0"
    debug: bool = False
    cors_allowed_origins: str = (
        "http://localhost:3000,http://localhost:8000,http://localhost:8001,"
        "http://localhost:8002,http://localhost:8003,http://localhost:8004"
    )
    api_key: str = "dev-api-key-change-me"

    # S3/MinIO
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "dev-access-key-change-me"
    s3_secret_key: str = "dev-secret-key-change-me"
    s3_region: str = "us-east-1"

    # Presigned URL defaults
    presigned_url_expiry: int = 3600  # seconds

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

