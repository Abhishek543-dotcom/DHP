"""
Kubernetes client wrapper for creating and managing Spark job pods.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class K8sJobManager:
    """Manages Kubernetes Jobs for Spark execution."""

    def __init__(self):
        if settings.k8s_in_cluster:
            config.load_incluster_config()
        else:
            try:
                config.load_kube_config()
                self._rewrite_loopback_kube_host_if_needed()
            except Exception:
                logger.warning("Could not load kube config — K8s operations will fail")

        self.batch_v1 = client.BatchV1Api()
        self.core_v1 = client.CoreV1Api()
        self.namespace = settings.k8s_namespace

    def _rewrite_loopback_kube_host_if_needed(self):
        """Map localhost kube API host to a Docker-reachable alias when configured."""
        cfg = client.Configuration.get_default_copy()
        if settings.k8s_host_alias:
            parsed = urlparse(cfg.host)
            if parsed.hostname in {"localhost", "127.0.0.1"}:
                scheme = parsed.scheme or "https"
                port = parsed.port
                netloc = (
                    settings.k8s_host_alias
                    if port is None
                    else f"{settings.k8s_host_alias}:{port}"
                )
                cfg.host = f"{scheme}://{netloc}"
                logger.info(
                    "Kubernetes API host rewritten from loopback to %s for container access",
                    cfg.host,
                )

        if settings.k8s_skip_tls_verify:
            cfg.verify_ssl = False
            logger.warning("Kubernetes TLS verification disabled for local development")

        client.Configuration.set_default(cfg)

    def _ensure_namespace(self):
        """Ensure the target namespace exists."""
        try:
            self.core_v1.read_namespace(self.namespace)
        except ApiException as e:
            if e.status == 404:
                ns = client.V1Namespace(
                    metadata=client.V1ObjectMeta(name=self.namespace)
                )
                self.core_v1.create_namespace(ns)
                logger.info(f"Created namespace: {self.namespace}")
            else:
                raise

    def _ensure_service_account(self):
        """Ensure the Spark service account exists in the target namespace."""
        if not settings.spark_service_account:
            return

        try:
            self.core_v1.read_namespaced_service_account(
                name=settings.spark_service_account,
                namespace=self.namespace,
            )
        except ApiException as e:
            if e.status == 404:
                sa = client.V1ServiceAccount(
                    metadata=client.V1ObjectMeta(
                        name=settings.spark_service_account,
                        namespace=self.namespace,
                    )
                )
                self.core_v1.create_namespaced_service_account(
                    namespace=self.namespace,
                    body=sa,
                )
                logger.info(
                    "Created service account '%s' in namespace '%s'",
                    settings.spark_service_account,
                    self.namespace,
                )
            else:
                raise

    def create_spark_job(self, job_event: dict) -> str:
        """
        Create a Kubernetes Job that runs a Spark container.

        The container runs the Spark job with all config injected via env vars.
        Fluent Bit sidecar ships logs tagged with job_id.
        """
        job_id = job_event["job_id"]
        retry_count = int(job_event.get("retry_count", 0))
        job_name_k8s = f"spark-job-{job_id[:8]}-r{retry_count}"

        spark_config = job_event.get("spark_config", {})
        arguments = job_event.get("arguments", [])
        runtime_kafka_brokers = settings.runtime_kafka_brokers or settings.kafka_brokers
        runtime_s3_endpoint = settings.runtime_s3_endpoint or settings.s3_endpoint
        runtime_job_service_url = settings.runtime_job_service_url or settings.job_service_url

        # Build Spark extra config string
        spark_conf_str = " ".join(
            f"--conf {k}={v}" for k, v in spark_config.items()
        )

        # Environment variables for the Spark container
        env_vars = [
            client.V1EnvVar(name="JOB_ID", value=job_id),
            client.V1EnvVar(name="ENTRYPOINT_SCRIPT", value=job_event["entrypoint"]),
            client.V1EnvVar(name="ARGUMENTS", value=" ".join(arguments)),
            client.V1EnvVar(name="SPARK_EXTRA_CONF", value=spark_conf_str),
            client.V1EnvVar(name="KAFKA_BROKERS", value=runtime_kafka_brokers),
            client.V1EnvVar(
                name="CALLBACK_URL",
                value=f"{runtime_job_service_url}/api/v1/jobs/{job_id}/status",
            ),
            client.V1EnvVar(name="INTERNAL_API_TOKEN", value=settings.internal_api_token),
            client.V1EnvVar(name="AWS_ACCESS_KEY_ID", value=settings.s3_access_key),
            client.V1EnvVar(name="AWS_SECRET_ACCESS_KEY", value=settings.s3_secret_key),
            client.V1EnvVar(name="S3_ENDPOINT", value=runtime_s3_endpoint),
        ]

        # Parse resource requirements from spark_config
        cpu_request = settings.default_cpu_request
        cpu_limit = settings.default_cpu_limit
        mem_request = settings.default_memory_request
        mem_limit = settings.default_memory_limit

        # Main Spark container
        spark_container = client.V1Container(
            name=f"spark-{job_id[:8]}",
            image=settings.spark_image,
            env=env_vars,
            resources=client.V1ResourceRequirements(
                requests={"cpu": cpu_request, "memory": mem_request},
                limits={"cpu": cpu_limit, "memory": mem_limit},
            ),
            volume_mounts=[
                client.V1VolumeMount(
                    name="spark-logs",
                    mount_path="/var/log/spark",
                ),
            ],
        )

        containers = [spark_container]
        volumes = [
            client.V1Volume(
                name="spark-logs",
                empty_dir=client.V1EmptyDirVolumeSource(),
            ),
        ]

        if settings.enable_fluent_bit_sidecar:
            fluentbit_container = client.V1Container(
                name="fluent-bit",
                image="fluent/fluent-bit:2.2",
                env=[
                    client.V1EnvVar(name="JOB_ID", value=job_id),
                    client.V1EnvVar(name="KAFKA_BROKERS", value=runtime_kafka_brokers),
                ],
                volume_mounts=[
                    client.V1VolumeMount(
                        name="spark-logs",
                        mount_path="/var/log/spark",
                        read_only=True,
                    ),
                    client.V1VolumeMount(
                        name="fluent-bit-config",
                        mount_path="/fluent-bit/etc",
                    ),
                ],
                resources=client.V1ResourceRequirements(
                    requests={"cpu": "100m", "memory": "128Mi"},
                    limits={"cpu": "200m", "memory": "256Mi"},
                ),
            )
            containers.append(fluentbit_container)
            volumes.append(
                client.V1Volume(
                    name="fluent-bit-config",
                    config_map=client.V1ConfigMapVolumeSource(
                        name="fluent-bit-config",
                        optional=True,
                    ),
                )
            )

        # Pod spec
        pod_spec = client.V1PodSpec(
            containers=containers,
            restart_policy="Never",
            service_account_name=settings.spark_service_account,
            volumes=volumes,
        )

        # Job spec
        job_spec = client.V1JobSpec(
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "lakehouse-spark",
                        "job-id": job_id,
                        "job-type": job_event.get("job_type", "unknown"),
                    },
                ),
                spec=pod_spec,
            ),
            backoff_limit=0,  # We handle retries at the application level
            ttl_seconds_after_finished=settings.ttl_seconds_after_finished,
        )

        k8s_job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name_k8s,
                namespace=self.namespace,
                labels={
                    "app": "lakehouse-spark",
                    "job-id": job_id,
                },
            ),
            spec=job_spec,
        )

        try:
            self._ensure_namespace()
            self._ensure_service_account()
            self.batch_v1.create_namespaced_job(
                namespace=self.namespace, body=k8s_job
            )
            logger.info(f"Created K8s Job: {job_name_k8s} for job_id={job_id}")
            return job_name_k8s
        except ApiException as e:
            if e.status == 409:
                logger.warning(
                    "K8s Job already exists: %s (job_id=%s), reusing existing resource",
                    job_name_k8s,
                    job_id,
                )
                return job_name_k8s
            logger.error(f"Failed to create K8s job for {job_id}: {e}")
            raise

    def delete_spark_job(self, job_id: str) -> bool:
        """Delete all Kubernetes Jobs associated with a job_id (for cancellation)."""
        try:
            result = self.batch_v1.list_namespaced_job(
                namespace=self.namespace,
                label_selector=f"job-id={job_id}",
            )
            jobs = result.items
            if not jobs:
                logger.warning(f"No K8s jobs found for job_id={job_id}")
                return False

            for job in jobs:
                self.batch_v1.delete_namespaced_job(
                    name=job.metadata.name,
                    namespace=self.namespace,
                    body=client.V1DeleteOptions(
                        propagation_policy="Foreground",
                    ),
                )
                logger.info(f"Deleted K8s Job: {job.metadata.name}")

            return True
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"K8s jobs not found for job_id={job_id}")
                return False
            raise

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get status of the latest Kubernetes Job for the provided job_id."""
        try:
            result = self.batch_v1.list_namespaced_job(
                namespace=self.namespace,
                label_selector=f"job-id={job_id}",
            )
            jobs = result.items
            if not jobs:
                return None

            jobs.sort(
                key=lambda j: j.metadata.creation_timestamp
                or datetime.fromtimestamp(0, tz=timezone.utc)
            )
            job = jobs[-1]
            status = job.status
            return {
                "k8s_job_name": job.metadata.name,
                "active": status.active or 0,
                "succeeded": status.succeeded or 0,
                "failed": status.failed or 0,
                "start_time": status.start_time.isoformat() if status.start_time else None,
                "completion_time": (
                    status.completion_time.isoformat()
                    if status.completion_time
                    else None
                ),
            }
        except ApiException as e:
            raise

