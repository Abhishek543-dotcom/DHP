# Lakehouse Platform — Runbook

## Local Development

### Prerequisites
- Docker Desktop with Docker Compose
- Python 3.11+
- kubectl with a reachable local Kubernetes cluster (`kubectl cluster-info`)
- `~/.kube/config` present (mounted into the orchestrator container)

### Start Infrastructure
```bash
cd infra
docker-compose -f docker-compose.dev.yaml up -d
```

### Verify Services
```bash
# Health checks
curl http://localhost:8001/health   # Job Service
curl http://localhost:8002/health   # Metadata Service
curl http://localhost:8003/health   # Log Service
curl http://localhost:8004/health   # Storage Service

# Service docs
open http://localhost:8001/docs     # Job Service Swagger
open http://localhost:8002/docs     # Metadata Service Swagger
open http://localhost:8003/docs     # Log Service Swagger
open http://localhost:8004/docs     # Storage Service Swagger

# Infrastructure UIs
open http://localhost:9001          # MinIO Console (see S3_ACCESS_KEY/S3_SECRET_KEY in .env)
open http://localhost:3000          # Grafana (admin/admin)
```

## Common Operations

Set API key once for all requests:
```bash
export API_KEY="${API_KEY:-dev-api-key-change-me}"
```

### Submit a Spark Job
```bash
curl -X POST http://localhost:8001/api/v1/jobs \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "job_name": "daily_sales_etl",
    "job_type": "spark_etl",
    "entrypoint": "s3://lakehouse-scripts/etl/sales_transform.py",
    "arguments": ["--date", "2026-03-24", "--mode", "incremental"],
    "spark_config": {
      "spark.executor.memory": "4g",
      "spark.executor.cores": 2
    },
    "database_name": "sales_db",
    "table_name": "transactions",
    "submitted_by": "data_engineering"
  }'
```

### Check Job Status
```bash
curl -H "X-API-Key: ${API_KEY}" http://localhost:8001/api/v1/jobs/{job_id}
```

### Get Job Logs
```bash
curl -H "X-API-Key: ${API_KEY}" http://localhost:8001/api/v1/jobs/{job_id}/logs?source=driver\&tail=500
```

### Cancel a Job
```bash
curl -X DELETE -H "X-API-Key: ${API_KEY}" http://localhost:8001/api/v1/jobs/{job_id}
```

### Create a Database
```bash
curl -X POST http://localhost:8002/api/v1/databases \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "sales_db",
    "owner": "data_engineering",
    "description": "Sales data warehouse"
  }'
```

### Create a Table
```bash
curl -X POST http://localhost:8002/api/v1/databases/sales_db/tables \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "transactions",
    "table_type": "ICEBERG",
    "schema_fields": [
      {"name": "id", "type": "long", "nullable": false},
      {"name": "amount", "type": "decimal", "nullable": false},
      {"name": "currency", "type": "string", "nullable": true},
      {"name": "transaction_date", "type": "timestamp", "nullable": false}
    ],
    "partition_spec": [{"field": "transaction_date", "transform": "day"}],
    "description": "Sales transactions"
  }'
```

### Schema Evolution (Add Column)
```bash
curl -X PUT http://localhost:8002/api/v1/databases/sales_db/tables/transactions \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "add_columns": [
      {"name": "region", "type": "string", "nullable": true}
    ],
    "changed_by": "data_engineering"
  }'
```

### List Storage Buckets
```bash
curl -H "X-API-Key: ${API_KEY}" http://localhost:8004/api/v1/storage/buckets
```

### Get Presigned Upload URL
```bash
curl -X POST http://localhost:8004/api/v1/storage/buckets/lakehouse-raw/presigned-url \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "object_key": "sales/2026-03-24/data.parquet",
    "operation": "upload",
    "expiry": 3600
  }'
```

## Troubleshooting

### Service won't start
1. Check Docker logs: `docker logs lakehouse-job-service`
2. Verify PostgreSQL is ready: `docker exec lakehouse-postgres pg_isready`
3. Verify Kafka is ready: `docker exec lakehouse-kafka kafka-topics --bootstrap-server localhost:9092 --list`

### Job stuck in PENDING
1. Check Kafka consumer is running: look at orchestrator logs
2. Verify Kafka topic exists: `docker exec lakehouse-kafka kafka-topics --bootstrap-server localhost:9092 --list`
3. Check Job Service can reach Kafka

### Job fails with `localhost:80` / namespace API errors
1. Verify local K8s is running: `kubectl cluster-info`
2. Confirm kubeconfig exists: `ls ~/.kube/config`
3. Restart orchestrator after kubeconfig changes: `docker compose -f infra/docker-compose.dev.yaml up -d --build orchestrator`
4. If you see TLS hostname mismatch errors, keep `K8S_SKIP_TLS_VERIFY=true` for local Docker mode

### Spark pods stay Pending (`Insufficient memory`)
1. Lower local default resources in `infra/docker-compose.dev.yaml` (`DEFAULT_MEMORY_REQUEST`, `DEFAULT_MEMORY_LIMIT`, `DEFAULT_CPU_REQUEST`)
2. Recreate orchestrator: `docker compose -f infra/docker-compose.dev.yaml up -d --force-recreate orchestrator`
3. Submit a new job and inspect pod events: `kubectl describe pod <pod-name> -n lakehouse-jobs`

### No logs for a job
1. Check Fluent Bit sidecar is running in the Spark pod
2. Verify Loki is receiving logs: `curl http://localhost:3100/ready`
3. Check Kafka topic `spark-job-logs` has messages

## Metrics & Monitoring

- **Prometheus metrics**: `http://localhost:{port}/metrics` on each service
- **Grafana dashboards**: `http://localhost:3000`
- Key metrics to watch:
  - `http_requests_total` — API request rates
  - `http_request_duration_seconds` — API latency
  - Job success/failure rates (custom metric)
  - Kafka consumer lag

