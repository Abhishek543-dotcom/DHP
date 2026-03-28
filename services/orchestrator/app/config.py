from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Orchestrator configuration."""

    # Kafka
    kafka_brokers: str = "localhost:9092"
    kafka_job_topic: str = "spark-job-submissions"
    kafka_consumer_group: str = "job-orchestrator"

    # Kubernetes
    k8s_namespace: str = "lakehouse-jobs"
    k8s_in_cluster: bool = False  # True when running inside K8s
    k8s_host_alias: Optional[str] = None
    k8s_skip_tls_verify: bool = False
    spark_image: str = "lakehouse-spark:3.5.0"
    spark_service_account: str = "spark-runner"
    enable_fluent_bit_sidecar: bool = True

    # Resource defaults
    default_cpu_request: str = "2"
    default_cpu_limit: str = "4"
    default_memory_request: str = "8Gi"
    default_memory_limit: str = "16Gi"

    # Job Service callback
    job_service_url: str = "http://localhost:8001"
    runtime_job_service_url: Optional[str] = None
    internal_api_token: str = "dev-internal-token-change-me"

    # Object storage credentials for Spark jobs
    s3_endpoint: str = "http://minio:9000"
    runtime_s3_endpoint: Optional[str] = None
    s3_access_key: str = "dev-access-key-change-me"
    s3_secret_key: str = "dev-secret-key-change-me"
    runtime_kafka_brokers: Optional[str] = None

    # Job cleanup
    ttl_seconds_after_finished: int = 3600  # 1 hour

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

