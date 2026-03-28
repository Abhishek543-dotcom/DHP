from enum import Enum


class JobStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD = "DEAD"


class JobType(str, Enum):
    SPARK_SQL = "spark_sql"
    SPARK_ETL = "spark_etl"
    SPARK_ML = "spark_ml"
    SPARK_STREAMING = "spark_streaming"


class LogSource(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    DRIVER = "driver"
    EXECUTOR = "executor"
    ALL = "all"

