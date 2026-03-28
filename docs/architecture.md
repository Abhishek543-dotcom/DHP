# Lakehouse Platform — Architecture

## Overview

The Lakehouse Platform is an API-driven managed framework for running Spark jobs in isolated 
Docker containers with full lifecycle management, metadata governance, and log observability.

## Architecture Layers

### 1. Client Layer
- REST API (OpenAPI 3.0)
- CLI (future)
- Web UI (future)

### 2. Service Layer (Microservices)

| Service | Port | Responsibility |
|---|---|---|
| Job Service | 8001 | Job CRUD, submit, cancel, status |
| Metadata Service | 8002 | Database, table, schema CRUD |
| Log Service | 8003 | Per-job log retrieval by Job ID |
| Storage Service | 8004 | Bucket/prefix management, presigned URLs |

### 3. Orchestration Layer
- **Kafka** — Durable job queue with ordered delivery
- **Job Orchestrator** — Kafka consumer → Kubernetes Job creator
- **Kubernetes** — Container lifecycle, autoscaling, pod isolation

### 4. Execution Layer
- **Spark Container** — Each job runs in an isolated container
- **Fluent Bit Sidecar** — Ships logs to Kafka tagged with `job_id`
- **Callback** — Container reports completion status to Job Service

### 5. Data Layer

| Component | Technology |
|---|---|
| Object Storage | S3 / MinIO |
| Metastore DB | PostgreSQL 16 |
| Table Format | Apache Iceberg |
| Log Storage | Grafana Loki |
| Cache | Redis |

## Job Lifecycle

```
PENDING → QUEUED → PROVISIONING → RUNNING → SUCCESS
                                           → FAILED → QUEUED (retry)
                                           → FAILED → DEAD (max retries)
                                  → CANCELLED
```

## Key Design Decisions

1. **Container-per-Job** — Strict resource isolation, independent log streams, clean env
2. **Kafka as Job Queue** — Durability, ordering, replay capability, backpressure
3. **Iceberg** — Vendor-neutral, REST catalog, hidden partitioning, schema evolution, time travel
4. **Log Isolation** — Fluent Bit tags all logs with `job_id` label for per-job querying

## Security (Planned)

- JWT/OAuth2 at API Gateway
- RBAC (Admin, DataEngineer, Analyst, Viewer)
- IAM-based S3 access
- mTLS between services (Istio)
- K8s NetworkPolicies for job container isolation

