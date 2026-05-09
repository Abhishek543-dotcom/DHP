from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Log Service configuration."""

    app_name: str = "Lakehouse Log Service"
    app_version: str = "1.0.0"
    debug: bool = False
    cors_allowed_origins: str = (
        "http://localhost:3000,http://localhost:8000,http://localhost:8001,"
        "http://localhost:8002,http://localhost:8003,http://localhost:8004"
    )
    api_key: str = "dev-api-key-change-me"

    # Loki
    loki_url: str = "http://localhost:3100"
    loki_query_path: str = "/loki/api/v1/query_range"

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

