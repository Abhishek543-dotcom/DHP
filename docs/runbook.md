# DataHarbour Project (DHP) Runbook

This runbook is for operators and developers running the platform in local dev or validating production-like behavior.

## 1. Prerequisites

- Docker Desktop running
- Python 3.11+
- `kubectl` configured and healthy
- `~/.kube/config` available

Validation:

```bash
docker --version
kubectl cluster-info
```

## 2. Start and Stop Procedures

### 2.1 Start Stack

```bash
cp .env.example .env
make build-spark
make up
```

### 2.2 Stop Stack

```bash
make down
```

### 2.3 Full Cleanup

```bash
make clean
```

## 3. Health Verification

### 3.1 API Health

```bash
curl -s http://localhost:8001/health
curl -s http://localhost:8001/health/ready
curl -s http://localhost:8002/health
curl -s http://localhost:8003/health
curl -s http://localhost:8004/health
```

### 3.2 Infra Health

```bash
curl -s http://localhost:3100/ready
curl -s http://localhost:9090/-/healthy
curl -s http://localhost:3000/api/health
curl -s http://localhost:9000/minio/health/live
```

### 3.3 Metrics Endpoints

```bash
curl -s http://localhost:8001/metrics | head
curl -s http://localhost:8002/metrics | head
curl -s http://localhost:8003/metrics | head
curl -s http://localhost:8004/metrics | head
```

## 4. Authentication Setup

```bash
export API_KEY="${API_KEY:-dev-api-key-change-me}"
export INTERNAL_TOKEN="${INTERNAL_API_TOKEN:-dev-internal-token-change-me}"
```

## 5. Functional Smoke Test

### 5.1 Metadata Setup

Create database:

```bash
curl -s -X POST http://localhost:8002/api/v1/databases/ \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "sales_db",
    "owner": "platform_ops",
    "description": "Sales domain"
  }'
```

Create table:

```bash
curl -s -X POST http://localhost:8002/api/v1/databases/sales_db/tables/ \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "transactions",
    "table_type": "ICEBERG",
    "schema_fields": [
      {"name": "id", "type": "long", "nullable": false},
      {"name": "amount", "type": "double", "nullable": false},
      {"name": "txn_date", "type": "string", "nullable": false}
    ],
    "partition_spec": [{"field": "txn_date", "transform": "day"}]
  }'
```

### 5.2 Storage Setup

```bash
curl -s -X POST http://localhost:8004/api/v1/storage/buckets \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"name":"ops-smoke-bucket"}'
```

### 5.3 Submit Spark Job

```bash
curl -s -X POST http://localhost:8001/api/v1/jobs/ \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "job_name": "sample_etl_smoke",
    "job_type": "spark_etl",
    "entrypoint": "s3://lakehouse-scripts/etl/sales_transform.py",
    "arguments": ["--date", "2026-03-28", "--mode", "append"],
    "spark_config": {
      "spark.executor.memory": "1g",
      "spark.executor.cores": 1,
      "spark.executor.instances": 1
    },
    "database_name": "sales_db",
    "table_name": "transactions",
    "submitted_by": "runbook",
    "max_retries": 1
  }'
```

Store returned `job_id` and poll status:

```bash
JOB_ID="<paste_job_id_here>"
watch -n 2 "curl -s -H 'X-API-Key: ${API_KEY}' http://localhost:8001/api/v1/jobs/${JOB_ID} | jq '{job_id,status,retry_count,error_message}'"
```

Fetch logs:

```bash
curl -s -H "X-API-Key: ${API_KEY}" \
  "http://localhost:8001/api/v1/jobs/${JOB_ID}/logs?source=all&tail=200" | jq .
```

## 6. Batch Execution: 10 Spark Jobs

You can submit all `batch10` jobs via API and track lifecycle.
Before submission, ensure `job_1.py` ... `job_10.py` are available under `s3://lakehouse-scripts/batch10/`.

```bash
for i in $(seq 1 10); do
  curl -s -X POST http://localhost:8001/api/v1/jobs/ \
    -H "X-API-Key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
      \"job_name\": \"batch10_job_${i}\",
      \"job_type\": \"spark_etl\",
      \"entrypoint\": \"s3://lakehouse-scripts/batch10/job_${i}.py\",
      \"arguments\": [\"--records\", \"1200\", \"--tag\", \"batch10\"],
      \"spark_config\": {
        \"spark.executor.memory\": \"1g\",
        \"spark.executor.cores\": 1,
        \"spark.executor.instances\": 1
      },
      \"submitted_by\": \"runbook_batch\",
      \"max_retries\": 1
    }" | jq -r '.job_id'
done
```

Track all recent jobs:

```bash
curl -s -H "X-API-Key: ${API_KEY}" "http://localhost:8001/api/v1/jobs/?page=1&page_size=50" \
  | jq '.jobs[] | {job_id,job_name,status,retry_count,submitted_at}'
```

## 7. Kubernetes Runtime Checks

### 7.1 Inspect Spark Jobs and Pods

```bash
kubectl get jobs -n lakehouse-jobs
kubectl get pods -n lakehouse-jobs
```

### 7.2 Pod Logs

```bash
kubectl logs -n lakehouse-jobs <pod-name> -c spark-<jobid8>
kubectl logs -n lakehouse-jobs <pod-name> -c fluent-bit
```

### 7.3 Pod Events

```bash
kubectl describe pod -n lakehouse-jobs <pod-name>
```

## 8. Grafana and Prometheus Operations

### 8.1 Grafana Dashboard

- URL: `http://localhost:3000/d/lakehouse-admin-ops/lakehouse-platform-admin-operations-overview`
- Login: `admin/admin`

### 8.2 Prometheus Target Health

```bash
curl -s http://localhost:9090/api/v1/targets \
  | jq '{active:(.data.activeTargets|length), healthy:(.data.activeTargets|map(select(.health=="up"))|length), unhealthy:(.data.activeTargets|map(select(.health!="up"))|length)}'
```

### 8.3 Key Queries

Request rate by service:

```promql
sum by (job) (rate(http_requests_total{job=~"job-service|metadata-service|log-service|storage-service"}[5m]))
```

P95 latency by service:

```promql
histogram_quantile(0.95, sum by (job, le) (rate(http_request_duration_highr_seconds_bucket{job=~"job-service|metadata-service|log-service|storage-service"}[5m])))
```

## 9. Troubleshooting Playbooks

### 9.1 Jobs Stay `PENDING` or `QUEUED`

Checks:

```bash
docker logs lakehouse-kafka --tail 100
docker logs lakehouse-orchestrator --tail 200
```

Fixes:

- Confirm Kafka health and topic auto-creation.
- Confirm orchestrator is running and can consume.

### 9.2 Orchestrator Cannot Reach Kubernetes

Symptoms:

- errors around kube config, API host, or TLS verification

Checks:

```bash
kubectl cluster-info
docker logs lakehouse-orchestrator --tail 200 | rg -n "kube|tls|host|namespace"
```

Fixes:

- Ensure `~/.kube/config` exists.
- Keep `K8S_HOST_ALIAS=host.docker.internal` in local docker mode.
- Keep `K8S_SKIP_TLS_VERIFY=true` for local-only setup.

### 9.3 Spark Pods Pending (Resources)

Checks:

```bash
kubectl get pods -n lakehouse-jobs
kubectl describe pod -n lakehouse-jobs <pod-name> | rg -n "Insufficient|FailedScheduling"
```

Fixes:

- Reduce orchestrator defaults in compose env:
  - `DEFAULT_CPU_REQUEST`
  - `DEFAULT_CPU_LIMIT`
  - `DEFAULT_MEMORY_REQUEST`
  - `DEFAULT_MEMORY_LIMIT`

### 9.4 Missing Logs in Job API

Checks:

```bash
curl -s http://localhost:3100/ready
docker logs lakehouse-log-service --tail 200
docker logs lakehouse-loki --tail 200
```

Fixes:

- Confirm Loki is healthy.
- Confirm Spark runtime produced log file.
- Confirm Fluent Bit sidecar enabled if relying on sidecar shipping.

### 9.5 Metadata or Job DB Errors

Checks:

```bash
docker exec lakehouse-postgres pg_isready -U lakehouse -d lakehouse
docker logs lakehouse-job-service --tail 200
docker logs lakehouse-metadata-service --tail 200
```

Fixes:

- Re-init schema: `make db-init`
- Reset schema (destructive): `make db-reset`

## 10. Postman Validation

Use the collection in `docs/postman` and run folders in order:

1. Metadata Service
2. Storage Service
3. Job Service
4. Log Service

Run `Log Streaming (Manual)` separately because it uses SSE.

## 11. Kubernetes Manifests

Deploy manifests:

```bash
make k8s-deploy
```

Remove manifests:

```bash
make k8s-delete
```

## 12. Operational Notes

- Local compose includes Prometheus and blackbox exporter.
- Grafana provisions datasources and dashboard on startup.
- The Spark image tag is expected to match `SPARK_IMAGE` in orchestrator config.
