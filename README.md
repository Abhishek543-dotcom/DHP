# Lakehouse Platform

An end-to-end managed lakehouse framework with API-driven Spark job execution, 
metadata management, and full observability.

## Architecture

- **Job Service** — Submit, manage, and monitor Spark jobs via REST API
- **Log Service** — Per-job log retrieval by Job ID
- **Metadata Service** — Database, table, schema CRUD with Iceberg catalog
- **Storage Service** — Object storage management (S3/MinIO)
- **Orchestrator** — Container lifecycle management on Kubernetes
- **Spark Containers** — Isolated Spark execution per job

## Tech Stack

| Component | Technology |
|---|---|
| API Framework | FastAPI (Python 3.11+) |
| Message Queue | Apache Kafka |
| Container Runtime | Kubernetes / Docker |
| Spark | Apache Spark 3.5+ |
| Table Format | Apache Iceberg |
| Object Storage | S3 / MinIO |
| Metastore DB | PostgreSQL 16 |
| Log Pipeline | Fluent Bit → Kafka → Loki |
| Caching | Redis |
| Monitoring | Prometheus + Grafana |

## Quick Start (Local Dev)

```bash
# Create env from template (includes dev API keys)
cp .env.example .env

# Ensure local Kubernetes is running (required for Spark job execution)
kubectl cluster-info

# Start all infrastructure services
cd infra
docker-compose -f docker-compose.dev.yaml up -d

# Start individual services (for development)
cd services/job-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

cd services/log-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003

cd services/metadata-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002

cd services/storage-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8004
```

`orchestrator` uses your local kubeconfig from `~/.kube/config`, rewrites loopback API hosts to `host.docker.internal`, and disables K8s TLS hostname verification in local Docker mode (`K8S_SKIP_TLS_VERIFY=true`).

## Authentication

- All business endpoints require `X-API-Key` (configured via `API_KEY`).
- Internal status callback endpoint requires `X-Internal-Token`.
- Health endpoints (`/health`, `/health/ready`) are intentionally unauthenticated.

## API Endpoints

### Job Service (port 8001)
- `POST /api/v1/jobs` — Submit a new Spark job
- `GET /api/v1/jobs` — List all jobs
- `GET /api/v1/jobs/{job_id}` — Get job details
- `DELETE /api/v1/jobs/{job_id}` — Cancel a job
- `GET /api/v1/jobs/{job_id}/logs` — Get job logs

### Metadata Service (port 8002)
- `POST /api/v1/databases` — Create database
- `GET /api/v1/databases` — List databases
- `DELETE /api/v1/databases/{db_name}` — Drop database
- `POST /api/v1/databases/{db_name}/tables` — Create table
- `GET /api/v1/databases/{db_name}/tables` — List tables
- `GET /api/v1/databases/{db_name}/tables/{table_name}` — Get table details
- `PUT /api/v1/databases/{db_name}/tables/{table_name}` — Alter table
- `DELETE /api/v1/databases/{db_name}/tables/{table_name}` — Drop table
- `GET /api/v1/databases/{db_name}/tables/{table_name}/snapshots` — Table snapshots

### Log Service (port 8003)
- `GET /api/v1/logs/{job_id}` — Get logs by job ID
- `GET /api/v1/logs/{job_id}/stream` — Stream logs (SSE)

### Storage Service (port 8004)
- `POST /api/v1/storage/buckets` — Create bucket
- `GET /api/v1/storage/buckets` — List buckets
- `GET /api/v1/storage/buckets/{name}/objects` — List objects
- `POST /api/v1/storage/buckets/{name}/presigned-url` — Get presigned URL
- `DELETE /api/v1/storage/buckets/{name}/objects/{key}` — Delete object

## Project Structure

```
lakehouse-platform/
├── services/
│   ├── job-service/          # Job management API
│   ├── log-service/          # Log retrieval API
│   ├── metadata-service/     # Catalog/metadata API
│   ├── storage-service/      # Object storage API
│   └── orchestrator/         # Job orchestration engine
├── spark-images/
│   ├── base/                 # Base Spark Docker image
│   └── jobs/                 # Sample Spark jobs
├── infra/
│   ├── k8s/                  # Kubernetes manifests
│   └── docker-compose.dev.yaml
├── scripts/                  # DB init, seed scripts
└── docs/                     # Architecture docs
```

