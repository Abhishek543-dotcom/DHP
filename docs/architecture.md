# DataHarbour Project (DHP) Architecture

## 1. Architecture Goals

The platform is designed around five goals:

1. API-first job operations for data teams
2. Isolated Spark runtime per job
3. Durable asynchronous orchestration
4. Clear metadata governance for lakehouse objects
5. Production-style observability in local development

## 2. Logical Architecture

```text
Clients (Postman/SDK/UI)
        |
        v
+-----------------------------+
| FastAPI Service Layer       |
| - Job Service (8001)        |
| - Metadata Service (8002)   |
| - Log Service (8003)        |
| - Storage Service (8004)    |
+-----------------------------+
        |
        | events (Kafka)
        v
+-----------------------------+
| Orchestration Layer         |
| - Orchestrator consumer     |
| - Kubernetes Job manager    |
+-----------------------------+
        |
        v
+-----------------------------+
| Execution Layer             |
| - Spark container per job   |
| - Optional Fluent Bit sidecar|
+-----------------------------+
        |
        +--> MinIO/S3 (data)
        +--> Job Service callback (status)
        +--> Loki (logs)

Cross-cutting: Prometheus + Blackbox + Grafana
```

## 3. Service Responsibilities

| Service | Responsibility | Persistence |
|---|---|---|
| Job Service | Job intake, status lifecycle, retries, cancellation, log passthrough | PostgreSQL (`jobs`, `job_log_refs`) |
| Metadata Service | Database and table CRUD, schema history, snapshot lookup | PostgreSQL (`catalog_*`, `schema_history`, `table_snapshots`) |
| Log Service | Query/stream job logs from Loki | Loki |
| Storage Service | Bucket/object listing and presigned URL generation | MinIO/S3 |
| Orchestrator | Kafka consume and K8s Job create/delete | Kafka + Kubernetes API |

## 4. Control Plane Design

### 4.1 Job Submission

- Job Service validates request and writes a `PENDING` row.
- It publishes to Kafka topic `spark-job-submissions`.
- On successful publish, state moves to `QUEUED`.
- If publish fails, job remains `PENDING` with an error message.

### 4.2 Orchestration

- Orchestrator consumes submission events.
- It marks job `PROVISIONING` through internal callback.
- It creates a Kubernetes Job named `spark-job-<jobid8>-r<retry_count>` in namespace `lakehouse-jobs`.
- Runtime env includes callback URL, internal token, S3 credentials, and Spark config.

### 4.3 Runtime Callback

Spark container entrypoint:

1. Reports `RUNNING`
2. Executes `spark-submit`
3. Reports terminal status with exit code

### 4.4 Retry Model

Job Service retry logic:

- On `FAILED` and `retry_count < max_retries`: increment retry and requeue
- On `FAILED` and `retry_count >= max_retries`: mark `DEAD`

Terminal states: `SUCCESS`, `CANCELLED`, `DEAD`

## 5. Data Plane Design

### 5.1 Metadata Catalog

Metadata Service stores:

- Namespaces: `catalog_databases`
- Tables: `catalog_tables`
- Schema evolution: `schema_history`
- Snapshots: `table_snapshots`

Table schema is stored as JSON (`schema_json`) and updated via schema evolution API.

### 5.2 Object Storage

- MinIO is used in local dev as S3-compatible backend.
- Startup bootstrap creates:
  - `lakehouse-warehouse`
  - `lakehouse-raw`
  - `lakehouse-scripts`
  - `lakehouse-logs`
- Spark jobs read/write using `s3a://`.

## 6. Log and Metrics Architecture

### 6.1 Logs

- Spark writes runtime logs to `/var/log/spark/<job_id>.log`.
- Fluent Bit sidecar can tail and forward logs with labels (`job_id`, `source`, `container_id`).
- Log Service queries Loki via LogQL, scoped by `job_id`.

### 6.2 Metrics

All API services expose `/metrics` via `prometheus_fastapi_instrumentator`.

Prometheus scrapes:

- API services
- Loki
- Prometheus self metrics
- Blackbox exporter targets (HTTP and TCP probes)

### 6.3 Dashboarding

Grafana is provisioned with:

- Prometheus datasource (`uid: prometheus`, default)
- Loki datasource (`uid: loki`)
- Dashboard: `lakehouse-admin-ops` (13 panels)

Dashboard focus:

- Availability and connectivity
- API throughput/error/latency
- Service resource health
- Job and log activity

## 7. Security Model

Current implementation:

- `X-API-Key` for business endpoints
- `X-Internal-Token` for internal status callback
- Constant-time token compare (`hmac.compare_digest`)

Planned hardening direction:

- Identity provider-backed authn/authz
- Role-based access controls
- Secret manager integration
- mTLS between services

## 8. Deployment Topologies

### 8.1 Local Development (Docker Compose + Local K8s)

- API services and infra run in Docker Compose.
- Orchestrator runs in Docker but talks to local Kubernetes via mounted kubeconfig.
- For Docker-to-host access:
  - `K8S_HOST_ALIAS=host.docker.internal`
  - `K8S_SKIP_TLS_VERIFY=true` (local-only convenience)

### 8.2 Kubernetes Manifests

`infra/k8s/` provides:

- Namespaces (`lakehouse-platform`, `lakehouse-jobs`)
- ConfigMap and Secret templates
- Deployments/Services for core APIs
- Orchestrator RBAC for managing Spark jobs
- Optional network policy for Spark pod egress control

## 9. Known Architectural Constraints

- Local mode depends on a running local Kubernetes cluster for Spark execution.
- Kafka topic management is auto-create in local dev.
- Retry logic is app-level (`backoff_limit=0` on K8s Job spec).
- Job status is callback-driven from runtime container.

## 10. Suggested Next Architecture Steps

1. Add dead-letter strategy for irrecoverable orchestration errors.
2. Add distributed tracing (OpenTelemetry) across services.
3. Add SLO-based alerts in Grafana/Alertmanager.
4. Introduce API gateway and role-based authorization.
