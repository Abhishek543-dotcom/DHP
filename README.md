# DataHarbour Project (DHP)

DataHarbour Project (DHP) is an API-first data platform for running Spark jobs with strong operational controls:

- Job submission, cancellation, status tracking, and retries
- Metadata catalog for databases and tables (schema evolution included)
- Object storage management for S3/MinIO
- Centralized logs and metrics with Grafana dashboards
- Kubernetes-backed isolated Spark runtime per job

This repository is optimized for local development while preserving production-like patterns (event-driven orchestration, health probes, observability, and service separation).

## Core Components

| Component | Port | Purpose |
|---|---:|---|
| Job Service | 8001 | Submit/list/get/cancel jobs and read logs |
| Metadata Service | 8002 | Manage databases, tables, schema, snapshots |
| Log Service | 8003 | Retrieve/stream job logs from Loki |
| Storage Service | 8004 | Manage buckets, objects, presigned URLs |
| Orchestrator | N/A | Consumes Kafka events and creates K8s Spark Jobs |
| Grafana | 3000 | Dashboards and platform observability |
| Prometheus | 9090 | Metrics scraping and probing |
| Loki | 3100 | Log storage and query backend |
| MinIO API | 9000 | S3-compatible object storage endpoint |
| MinIO Console | 9001 | MinIO admin UI |
| Kafka | 9092/29092 | Job queue and async event backbone |
| PostgreSQL | 5432 | Job and catalog metadata persistence |
| Redis | 6379 | Service cache / future coordination |

## High-Level Flow

1. Client submits a job to `POST /api/v1/jobs`.
2. Job Service stores it in PostgreSQL and publishes to Kafka topic `spark-job-submissions`.
3. Orchestrator consumes the event and creates a Kubernetes Job running the Spark image.
4. Spark container reports `RUNNING` and final status (`SUCCESS` or `FAILED`) to Job Service via internal callback.
5. Failed jobs are retried until `max_retries`; terminal failures become `DEAD`.
6. Logs are shipped to Loki and retrieved via Job Service or Log Service APIs.

## Prerequisites

- Docker Desktop (with Compose)
- Python 3.11+
- `kubectl` configured to a reachable local cluster
- `~/.kube/config` present (mounted into orchestrator container)

## Quick Start

```bash
cp .env.example .env

# Required for Spark runtime jobs created by orchestrator
kubectl cluster-info

# Build Spark runtime image used by orchestrator (required once, or after changes)
make build-spark

# Start full local stack
make up
```

After startup:

- Job Service docs: `http://localhost:8001/docs`
- Metadata Service docs: `http://localhost:8002/docs`
- Log Service docs: `http://localhost:8003/docs`
- Storage Service docs: `http://localhost:8004/docs`
- Grafana: `http://localhost:3000` (`admin` / `admin`)
- Prometheus: `http://localhost:9090`
- MinIO Console: `http://localhost:9001`

## Authentication Model

- Business APIs use `X-API-Key`.
- Internal callback endpoint `PUT /api/v1/jobs/{job_id}/status` uses `X-Internal-Token`.
- Health endpoints are intentionally unauthenticated.

Defaults come from `.env`:

- `API_KEY=dev-api-key-change-me`
- `INTERNAL_API_TOKEN=dev-internal-token-change-me`

## API Surface

### Job Service (`http://localhost:8001`)

- `GET /health`
- `GET /health/ready`
- `POST /api/v1/jobs/`
- `GET /api/v1/jobs/`
- `GET /api/v1/jobs/{job_id}`
- `DELETE /api/v1/jobs/{job_id}`
- `PUT /api/v1/jobs/{job_id}/status` (internal)
- `GET /api/v1/jobs/{job_id}/logs`

### Metadata Service (`http://localhost:8002`)

- `GET /health`
- `POST /api/v1/databases/`
- `GET /api/v1/databases/`
- `GET /api/v1/databases/{db_name}`
- `DELETE /api/v1/databases/{db_name}`
- `POST /api/v1/databases/{db_name}/tables/`
- `GET /api/v1/databases/{db_name}/tables/`
- `GET /api/v1/databases/{db_name}/tables/{table_name}`
- `PUT /api/v1/databases/{db_name}/tables/{table_name}`
- `DELETE /api/v1/databases/{db_name}/tables/{table_name}`
- `GET /api/v1/databases/{db_name}/tables/{table_name}/snapshots`

### Log Service (`http://localhost:8003`)

- `GET /health`
- `GET /api/v1/logs/{job_id}`
- `GET /api/v1/logs/{job_id}/stream` (SSE)

### Storage Service (`http://localhost:8004`)

- `GET /health`
- `POST /api/v1/storage/buckets`
- `GET /api/v1/storage/buckets`
- `GET /api/v1/storage/buckets/{bucket_name}/objects`
- `POST /api/v1/storage/buckets/{bucket_name}/presigned-url`
- `DELETE /api/v1/storage/buckets/{bucket_name}/objects/{object_key}`

## Spark Jobs in This Repo

- Sample ETL: `spark-images/jobs/sample_etl.py`
- Batch test suite: `spark-images/jobs/batch10/job_1.py` ... `job_10.py`

Use `entrypoint` values like:

- `s3://lakehouse-scripts/etl/sales_transform.py` (sample style)
- `s3://lakehouse-scripts/batch10/job_1.py` (batch suite style)

The runtime entrypoint script converts `s3://` to `s3a://` automatically and injects Spark/Iceberg/S3 settings.
Make sure these scripts are uploaded to the `lakehouse-scripts` bucket before submitting jobs.

## Observability

Grafana ships with a provisioned admin dashboard:

- URL: `http://localhost:3000/d/lakehouse-admin-ops/lakehouse-platform-admin-operations-overview`
- UID: `lakehouse-admin-ops`
- Folder: `DataHarbour Admin`

The dashboard includes:

- HTTP and TCP blackbox probes
- Service scrape status (`up`)
- API throughput, error rate, and P95 latency
- CPU, memory, and open file descriptors per service
- Job API activity and log volume panels
- Recent error logs from Loki

## Postman Assets

Importable artifacts are under `docs/postman/`:

- `lakehouse-platform.postman_collection.json`
- `lakehouse-platform.local.postman_environment.json`

See `docs/postman/README.md` for run order and environment variable details.

## Useful Make Targets

```bash
make help
make up
make down
make logs
make build
make build-spark
make test
make db-init
make db-reset
```

## Repository Layout

```text
.
├── docs/
│   ├── architecture.md
│   ├── runbook.md
│   └── postman/
├── infra/
│   ├── docker-compose.dev.yaml
│   ├── prometheus/
│   ├── grafana/
│   └── k8s/
├── services/
│   ├── job-service/
│   ├── metadata-service/
│   ├── log-service/
│   ├── storage-service/
│   └── orchestrator/
├── spark-images/
│   ├── base/
│   └── jobs/
└── scripts/
```

## Additional Documentation

- Architecture details: `docs/architecture.md`
- Operations runbook: `docs/runbook.md`
- Contributing guide: `CONTRIBUTING.md`
- Security policy: `SECURITY.md`
