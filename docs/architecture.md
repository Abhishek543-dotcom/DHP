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
| - Lineage Service (8005)    |
+-----------------------------+
        |
        | events (Kafka)               schedules (Postgres)
        v                                       |
+-----------------------------+         +-------v---------+
| Orchestration Layer         |<--------| Scheduler tick  |
| - Orchestrator consumer     |         | (advisory lock) |
| - Cancellation consumer     |         +-----------------+
| - K8s / ECS Job manager     |
| - Metrics endpoint :9000    |
+-----------------------------+
        |
        v
+------------------------------+
| Execution Layer              |
| - Spark container per job    |
| - OpenLineage HTTP transport |
| - Spark eventLog -> S3       |
| - Optional Fluent Bit sidecar|
+------------------------------+
        |
        +--> MinIO/S3 (data + spark-events)
        +--> Job Service callback (status)
        +--> Loki (logs)
        +--> Lineage Service (OpenLineage events)
        +--> Glue Data Catalog (Iceberg, optional)

Cross-cutting: Prometheus + Blackbox + Grafana + Spark History Server (:18080)
```

## 3. Service Responsibilities

| Service | Responsibility | Persistence |
|---|---|---|
| Job Service | Job intake, status lifecycle, retries, cancellation, log passthrough, scheduled jobs CRUD | PostgreSQL (`jobs`, `job_log_refs`, `scheduled_jobs`) |
| Metadata Service | Database and table CRUD, schema history, snapshot lookup, optional Glue write-through | PostgreSQL (`catalog_*`, `schema_history`, `table_snapshots`) + AWS Glue |
| Log Service | Query/stream job logs from Loki | Loki |
| Storage Service | Bucket/object listing and presigned URL generation | MinIO/S3 |
| Lineage Service | Ingest OpenLineage events, traverse run/dataset graph | PostgreSQL (`lineage_runs`, `lineage_datasets`, `lineage_run_inputs`, `lineage_run_outputs`) |
| Orchestrator | Kafka consume + scheduler tick + Spark Job create/delete | Kafka + Postgres advisory lock + K8s/ECS API |
| Spark History Server | Serve UI for completed Spark applications via `/spark-history` | S3 (`spark-events/`) |

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

### 4.5 Scheduled Jobs

- `POST /api/v1/schedules` validates the cron expression with `croniter` and stores `(cron_expression, timezone, job_template, next_run_at)` in `scheduled_jobs`.
- The orchestrator runs a scheduler loop every `SCHEDULER_TICK_SECONDS` (default 30s).
- Each tick acquires a Postgres advisory lock (`pg_try_advisory_lock`) so only one orchestrator replica fires schedules.
- Due rows are materialized into Kafka job submission events with a fresh `job_id`, then `next_run_at` is recomputed in the schedule's timezone and stored in UTC.
- `POST /api/v1/schedules/{id}/trigger` enqueues a one-off run via the existing job submission path.

## 5. Data Plane Design

### 5.1 Metadata Catalog

Metadata Service stores:

- Namespaces: `catalog_databases`
- Tables: `catalog_tables`
- Schema evolution: `schema_history`
- Snapshots: `table_snapshots`

Table schema is stored as JSON (`schema_json`) and updated via schema evolution API.

When `GLUE_CATALOG_DATABASE` is set, table create/drop operations are mirrored to the AWS Glue Data Catalog as Iceberg tables (`table_type=ICEBERG`). Glue calls are best-effort: failures are logged and metered via `dhp_catalog_glue_sync_total{op,outcome}` but never block the DHP write. `POST /api/v1/databases/{db_name}/sync-glue` backfills existing rows.

### 5.2 Object Storage

- MinIO is used in local dev as S3-compatible backend.
- Startup bootstrap creates:
  - `lakehouse-warehouse`
  - `lakehouse-raw`
  - `lakehouse-scripts`
  - `lakehouse-logs`
- Spark jobs read/write using `s3a://`.

### 5.3 Iceberg + Glue Catalog

The Spark base image bundles `iceberg-spark-runtime-3.5_2.12-1.5.0.jar` and `iceberg-aws-bundle-1.5.0.jar`, and always registers the Iceberg SQL extensions. By default a `lakehouse` Hadoop catalog is configured for offline use. When `GLUE_CATALOG_DATABASE` is provided to the Spark task, an additional `glue` catalog is wired with `org.apache.iceberg.aws.glue.GlueCatalog` against the warehouse bucket. This lets Athena, EMR, and Snowflake read DHP tables through Glue without bespoke metadata bridges.

### 5.4 Lineage

The Spark base image ships with `openlineage-spark_2.12-1.20.4.jar`. When `LINEAGE_URL` is set on the Spark task, the runtime registers `OpenLineageSparkListener` with HTTP transport pointing at the Lineage Service `/api/v1/lineage` endpoint and namespace `dhp`. The custom_environment_variables facet captures `JOB_ID` so DHP-side joins between `lineage_runs.dhp_job_id` and `jobs.job_id` work out of the box.

Lineage Service:

- Upserts runs by `runId` (later events for the same run UPDATE state/ended_at/facets).
- Upserts datasets by `(namespace, name)`.
- Inserts run input/output edges idempotently (`ON CONFLICT DO NOTHING`).
- Exposes upstream/downstream traversal via a recursive CTE bounded to `:max_depth` hops (default 10).

## 6. Log and Metrics Architecture

### 6.1 Logs

- Spark writes runtime logs to `/var/log/spark/<job_id>.log`.
- Fluent Bit sidecar can tail and forward logs with labels (`job_id`, `source`, `container_id`).
- Log Service queries Loki via LogQL, scoped by `job_id`.

### 6.2 Metrics

All API services expose `/metrics` via `prometheus_fastapi_instrumentator`. The orchestrator (which has no FastAPI app) runs an `aiohttp` server on `:9000/metrics` exposing the default Prometheus registry alongside `/health`.

Each service additionally publishes domain-specific counters/gauges/histograms (see README §Observability for the full catalog). Highlights:

- Job Service: submission/queue/active/retry/completed/failed counters and submission latency histogram
- Metadata Service: catalog write counters, database/table gauges (seeded from row counts on lifespan startup so they survive restarts), and Glue sync outcome counter
- Lineage Service: per-event-type ingestion counter and graph query counter
- Orchestrator: `RunTask` latency histogram, launch outcome counter, retry/DLQ counters, cancellation counter

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

### 6.4 Spark History Server

A dedicated ECS service (`apache/spark:3.5.1` based image at `spark-images/spark-history`) reads `s3a://<logs-bucket>/spark-events/` and serves the Spark UI for completed applications behind ALB path `/spark-history` (with `spark.history.ui.proxyBase` set so static assets resolve). Spark task definitions enable `spark.eventLog.*` to write events into the same prefix when `S3_LOGS_BUCKET` is provided. The history server runs with a read-only IAM role scoped to the logs bucket.

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

### 8.3 Jenkins Pipeline

The `Jenkinsfile` at the repository root provides a single parameterized pipeline
covering both application deployment and infrastructure management:

- **App deployment** (`deploy`): Lint → Test → Build & Push (8 images in parallel) → DB Migrations → Approval → Deploy ECS Services (parallel) → Smoke Test.
- **Infrastructure** (`infra-plan` / `infra-apply` / `infra-destroy`): Terraform init → validate → plan → approval → apply/destroy.

Jenkins uses static AWS credentials (`AmazonWebServicesCredentialsBinding`) and
includes a manual approval gate before apply/deploy actions. This contrasts with
the GitHub Actions workflow which uses OIDC and auto-deploys on push to `main`.

Both CI systems produce the same result: updated ECR images, migrated database,
and rolling ECS service deployments.

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
