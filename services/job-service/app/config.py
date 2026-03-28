from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Job Service configuration."""

    # Application
    app_name: str = "Lakehouse Job Service"
    app_version: str = "1.0.0"
    debug: bool = False
    cors_allowed_origins: str = (
        "http://localhost:3000,http://localhost:8000,http://localhost:8001,"
        "http://localhost:8002,http://localhost:8003,http://localhost:8004"
    )
    api_key: str = "dev-api-key-change-me"
    internal_api_token: str = "dev-internal-token-change-me"

    # Database
    database_url: str = "postgresql+asyncpg://lakehouse:dev-db-password-change-me@localhost:5432/lakehouse"
    auto_create_tables: bool = False

    # Kafka
    kafka_brokers: str = "localhost:9092"
    kafka_job_topic: str = "spark-job-submissions"
    kafka_job_status_topic: str = "spark-job-status"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Log Service
    log_service_url: str = "http://localhost:8003"
    log_service_api_key: str = "dev-api-key-change-me"

    # Orchestrator callback
    callback_url: str = "http://localhost:8001"

    # Job defaults
    default_max_retries: int = 3
    default_executor_memory: str = "4g"
    default_executor_cores: int = 2
    default_executor_instances: int = 2

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

