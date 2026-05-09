"""Orchestrator configuration."""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Environment
    environment: str = "dev"
    aws_region: str = "us-east-1"

    # Kafka / MSK
    kafka_brokers: str = "localhost:9092"
    kafka_job_topic: str = "spark-job-submissions"
    kafka_consumer_group: str = "job-orchestrator"
    msk_use_iam: bool = False  # set to true for AWS, leave false for local docker-compose
    runtime_kafka_brokers: Optional[str] = None  # what the Spark task should connect to

    # ECS - Spark task launch
    ecs_cluster: str = ""
    spark_task_definition: str = ""
    spark_subnets: str = ""             # comma-separated
    spark_security_group: str = ""      # comma-separated (single id ok)
    spark_container_name: str = "spark"
    spark_log_group: str = ""           # for log queries; not strictly required here

    # Job Service callback
    job_service_url: str = "http://localhost:8001"
    runtime_job_service_url: Optional[str] = None
    internal_api_token: str = "dev-internal-token-change-me"

    # Polling
    task_poll_interval_seconds: int = 30

    # Retry / DLQ
    default_max_retries: int = 3


@lru_cache()
def get_settings() -> Settings:
    return Settings()
