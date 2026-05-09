"""Configuration for the lineage-service."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DHP Lineage Service"
    app_version: str = "1.0.0"
    debug: bool = False
    cors_allowed_origins: str = (
        "http://localhost:3000,http://localhost:8000,http://localhost:8001,"
        "http://localhost:8002,http://localhost:8003,http://localhost:8004"
    )
    api_key: str = "dev-api-key-change-me"

    database_url: str = (
        "postgresql+asyncpg://lakehouse:dev-db-password-change-me"
        "@localhost:5432/lakehouse"
    )

    redis_url: str = "redis://localhost:6379"

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, str) and value.strip().lower() in {
            "release", "prod", "production",
        }:
            return False
        return value

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
