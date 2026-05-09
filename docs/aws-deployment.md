# DHP on AWS ECS — Deployment Guide

This document covers deploying DHP onto AWS using the Terraform stack
in `infra/terraform/`. Two CI/CD systems are supported:

- **GitHub Actions** (`.github/workflows/deploy.yml`) — OIDC-based, automatic on push to `main`.
- **Jenkins** (`Jenkinsfile` at repo root) — Credential-based, parameterized pipeline with manual triggers.

## Architecture

```
                Internet
                   │
              ┌────▼─────┐
              │   ALB    │  (HTTPS via ACM, path-routed)
              └────┬─────┘
        /jobs  /metadata  /logs  /storage  /lineage  /spark-history
              │
   ┌──────────┴──────────────────────────────────────┐
   │   ECS Fargate (private subnets)                 │
   │  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐        │
   │  │ job   │ │ meta  │ │ log   │ │ stor. │        │
   │  └───────┘ └───────┘ └───────┘ └───────┘        │
   │  ┌───────────┐ ┌───────────────┐ ┌────────────┐ │
   │  │ lineage   │ │ orchestrator  │ │  spark     │ │
   │  │ service   │ │ +scheduler    │ │  history   │ │
   │  └───────────┘ └──────┬────────┘ └────────────┘ │
   │                       │ ecs:RunTask              │
   │                ┌──────▼────────┐                 │
   │                │  Spark task   │                 │
   │                │   (Fargate)   │                 │
   │                └───────────────┘                 │
   └──────┬─────────────────┬──────────────┬──────────┘
          │                 │              │
     ┌────▼────┐       ┌────▼────────┐ ┌───▼───────────┐
     │   RDS   │       │    MSK      │ │ Glue Data     │
     │ Postgres│       │ Serverless  │ │ Catalog       │
     └─────────┘       └─────────────┘ └───────────────┘
                         (IAM auth)

     ┌──────────┐  ┌──────────┐  ┌──────────────┐
     │   S3 x4  │  │ElastiCache│ │ CloudWatch   │
     │ buckets  │  │   Redis   │ │ Logs+Metrics │
     └──────────┘  └──────────┘  └──────────────┘
       (incl.
        spark-events/
        prefix on logs)
```

## Prerequisites

- AWS account with admin (or fine-grained equivalent)
- `terraform` >= 1.6
- `aws` CLI v2
- `docker` (for the bootstrap image push)
- An ACM certificate in the deployment region (recommended for HTTPS)

## One-time bootstrap

### 1. Configure GitHub OIDC

Create an IAM role that GitHub Actions can assume via OIDC. Trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::<ACCOUNT>:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike":   {"token.actions.githubusercontent.com:sub": "repo:<ORG>/<REPO>:ref:refs/heads/main"}
    }
  }]
}
```

Attach permissions for: `ecr:*`, `ecs:*` (scoped to the cluster),
`iam:PassRole` for the task roles, `ec2:Describe*`, `logs:*`.

### 2. Set GitHub repo variables/secrets

Variables (Settings → Variables):
- `AWS_REGION` — e.g. `us-east-1`
- `AWS_ACCOUNT_ID`
- `ECR_REGISTRY` — `<account>.dkr.ecr.<region>.amazonaws.com`
- `ECS_CLUSTER` — `dhp-dev-cluster` (matches Terraform)
- `ENVIRONMENT` — `dev` (or `staging`/`prod`)

Secrets:
- `AWS_ROLE_ARN` — ARN of the OIDC role above

### 3. Apply Terraform

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit values: aws_region, environment, acm_certificate_arn, alb_allowed_cidrs

terraform init
terraform plan
terraform apply
```

This creates the VPC, ECS cluster, ALB, RDS, MSK, S3, ECR repos, etc.
Service tasks will fail to start until images exist (next step).

### 4. Push the first images

You can either:

**Option A — let GitHub Actions do it** by pushing to `main`:
the `deploy.yml` workflow builds + pushes all images, runs the
migrations task, and rolls the services.

**Option B — bootstrap manually** (one-off):

```bash
ENV=dev
REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com

aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $REGISTRY

for svc in job-service metadata-service log-service storage-service lineage-service orchestrator; do
  docker build --platform linux/amd64 -t $REGISTRY/dhp-$ENV/$svc:latest services/$svc
  docker push $REGISTRY/dhp-$ENV/$svc:latest
done

docker build --platform linux/amd64 -t $REGISTRY/dhp-$ENV/spark-base:latest spark-images/base
docker push $REGISTRY/dhp-$ENV/spark-base:latest

docker build --platform linux/amd64 -t $REGISTRY/dhp-$ENV/spark-history:latest spark-images/spark-history
docker push $REGISTRY/dhp-$ENV/spark-history:latest

docker build --platform linux/amd64 -t $REGISTRY/dhp-$ENV/db-migrations:latest db
docker push $REGISTRY/dhp-$ENV/db-migrations:latest
```

### 5. Run initial migrations

```bash
TD_ARN=$(aws ecs describe-task-definition \
  --task-definition dhp-$ENV-db-migrations \
  --query 'taskDefinition.taskDefinitionArn' --output text)

aws ecs run-task \
  --cluster dhp-$ENV-cluster \
  --task-definition $TD_ARN \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-ids>],securityGroups=[<sg-id>],assignPublicIp=DISABLED}"
```

After this, the API services should reach a steady RUNNING state.

## Smoke test

```bash
ALB_DNS=$(terraform -chdir=infra/terraform output -raw alb_dns_name)

# Health check (no auth required)
curl https://$ALB_DNS/jobs/health
curl https://$ALB_DNS/metadata/health
curl https://$ALB_DNS/logs/health
curl https://$ALB_DNS/storage/health
curl https://$ALB_DNS/lineage/health
# Spark History Server UI
open https://$ALB_DNS/spark-history/

# Submit a sample job (API_KEY from Secrets Manager)
API_KEY=$(aws secretsmanager get-secret-value --secret-id dhp-$ENV/app \
  --query 'SecretString' --output text | jq -r .API_KEY)

curl -X POST https://$ALB_DNS/jobs/api/v1/jobs \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_name": "smoke-test",
    "job_type": "spark_etl",
    "entrypoint": "s3://<scripts-bucket>/job.py",
    "submitted_by": "ops@example.com"
  }'
```

The orchestrator picks the message off MSK and launches an ECS Spark task.
You can follow it via:

```bash
aws ecs list-tasks --cluster dhp-$ENV-cluster --family dhp-$ENV-spark
aws logs tail /dhp/$ENV/spark --follow
```

## Deploying via Jenkins

The `Jenkinsfile` at the repository root provides a parameterized pipeline that
handles both application deployment and infrastructure management.

### Jenkins prerequisites

- Jenkins credential `aws-jenkins-creds` (type: Amazon Web Services Credentials)
- Docker daemon available on the Jenkins agent
- Terraform installed (path configured via `TERRAFORM_BIN` env in Jenkinsfile)
- AWS CLI v2 installed (path configured via `AWS_BIN` env in Jenkinsfile)
- Python 3, `ruff`, `pytest` on the agent (or the pipeline installs them)

### Pipeline parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEPLOY_ACTION` | `build-only` | `build-only`, `deploy`, `infra-plan`, `infra-apply`, `infra-destroy` |
| `ENVIRONMENT` | `dev` | Target environment: `dev`, `staging`, `prod` |
| `AWS_REGION` | `us-east-1` | AWS region |
| `IMAGE_TAG` | *(empty)* | Docker image tag; defaults to 12-char Git SHA |
| `AUTO_APPROVE` | `false` | Skip manual approval gate |
| `RUN_TESTS` | `true` | Run unit tests before build |

### Pipeline actions explained

| Action | Stages executed |
|--------|----------------|
| `build-only` | Checkout → Preflight → Lint → Test → Build & Push Images |
| `deploy` | All of `build-only` + Run DB Migrations → Approval → Deploy ECS Services → Smoke Test |
| `infra-plan` | Checkout → Preflight → Terraform Init → Validate → Plan |
| `infra-apply` | All of `infra-plan` + Approval → Apply |
| `infra-destroy` | Checkout → Preflight → Terraform Init → Validate → Destroy Plan → Approval → Destroy |

### Running a deploy via Jenkins

1. Open the Jenkins job and click **Build with Parameters**.
2. Set `DEPLOY_ACTION` = `deploy`, choose `ENVIRONMENT`, confirm `AWS_REGION`.
3. Optionally set a specific `IMAGE_TAG` or leave blank for Git SHA.
4. The pipeline builds all 8 images in parallel, pushes to ECR, runs Alembic migrations via `ecs run-task`, then waits for approval.
5. After approval, it updates all ECS task definitions and forces new deployments in parallel.
6. The smoke test stage hits each service's `/health/ready` endpoint via the ALB.

### Running infrastructure changes via Jenkins

1. Set `DEPLOY_ACTION` = `infra-plan` first to review the Terraform plan (archived as `tfplan.txt`).
2. If satisfied, re-run with `DEPLOY_ACTION` = `infra-apply`.
3. The pipeline passes `-var="environment=..."`, `-var="aws_region=..."`, and `-var="image_tag=..."` to Terraform.

### Comparison: GitHub Actions vs Jenkins

| Aspect | GitHub Actions | Jenkins |
|--------|---------------|---------|
| Auth | OIDC (no static creds) | Static IAM credentials |
| Trigger | Push to `main` / manual dispatch | Manual (Build with Parameters) |
| Infra management | Not included (Terraform run separately) | Built-in `infra-plan`/`infra-apply`/`infra-destroy` |
| Approval gate | N/A (auto-deploys) | Manual `input` step (skip with `AUTO_APPROVE`) |
| Build parallelism | GitHub matrix (separate runners) | Jenkins parallel stages (single agent) |

---

## Configuration reference

All sensitive runtime config lives in **Secrets Manager** under
`dhp-<env>/app`. Task definitions inject these into containers as env vars
via the `secrets` block:

| Env var              | Source                                       |
|----------------------|----------------------------------------------|
| `DATABASE_URL`       | Secrets Manager (`dhp-<env>/app:DATABASE_URL`) |
| `API_KEY`            | Secrets Manager                              |
| `INTERNAL_API_TOKEN` | Secrets Manager                              |
| `KAFKA_BROKERS`      | Plain env (MSK bootstrap brokers)            |
| `S3_*_BUCKET`        | Plain env (Terraform-resolved bucket names)  |
| `AWS_REGION`         | Plain env                                    |
| `ECS_CLUSTER`, `SPARK_TASK_DEFINITION`, `SPARK_SUBNETS`, `SPARK_SECURITY_GROUP` | Orchestrator-only |
| `GLUE_CATALOG_DATABASE` | Plain env (Terraform-resolved Glue DB name) — set on metadata-service and Spark task |
| `LINEAGE_URL`           | Plain env (`http://<alb_dns>/lineage`) — set on Spark task to enable OpenLineage |
| `S3_LOGS_BUCKET`        | Plain env — Spark task writes eventLogs to `spark-events/`; history server reads from it |
| `SCHEDULER_TICK_SECONDS`| Plain env on orchestrator (default 30) |

## Cost estimate (dev profile, idle)

~$195/mo. See `infra/terraform/README.md` for breakdown. Multi-AZ +
larger instances roughly triple this for prod.

## Operational notes

- **Local dev path is preserved**: docker-compose still works via MinIO + Kafka. Do NOT set `MSK_USE_IAM=true` locally.
- **Spark on Fargate caveat**: 200 GiB ephemeral disk cap, no native shuffle service. For >100 GiB intermediate data, switch the orchestrator to launch EMR Serverless jobs (one-method change in `app/ecs_manager.py`).
- **Static API-key auth is intentional for Phase 1**. Phase 2 will swap to Cognito JWT.
- **Migrations are idempotent** — `alembic upgrade head` is safe to re-run on every deploy.

## Production hardening (Phase 2)

### Health checks
- ALB target groups probe `GET /health/ready` (deep readiness, hits DB/Kafka/Loki/S3 as appropriate).
- ECS container `HEALTHCHECK` continues to hit the cheap `GET /health` (liveness only).
- A failing readiness probe causes ALB to drain the task while ECS leaves it running — the orchestrator can repair stuck dependencies without a forced restart loop.

### Rate limiting
- All four FastAPI services run `slowapi` with the limiter backed by ElastiCache Redis.
- Default: `120/minute` per API key (X-API-Key header) or per source IP. Override per service via `RATE_LIMIT_DEFAULT` env var.
- `X-Internal-Token` traffic is exempted (service-to-service callbacks).
- 429 responses include `Retry-After: 60`.

### Alerting (SNS + email)
Set `alarm_emails = ["sre@yourcompany.com", ...]` in your tfvars. After `terraform apply`, each subscriber receives an AWS confirmation email — must be clicked once before alerts deliver.

Active alarms (all publish to the same SNS topic):

| Alarm                              | Trigger                                  |
|------------------------------------|------------------------------------------|
| `dhp-<env>-alb-5xx`                | >10 ALB 5xx in 1 min, two periods        |
| `dhp-<env>-<svc>-unhealthy-hosts`  | Any unhealthy target in TG               |
| `dhp-<env>-rds-cpu`                | RDS CPU >80% for 15 min                  |
| `dhp-<env>-rds-free-storage`       | RDS storage <20% of allocation           |
| `dhp-<env>-<svc>-cpu-high`         | ECS service CPU >85% for 3 min           |
| `dhp-<env>-<svc>-memory-high`      | ECS service memory >85% for 3 min        |
| `dhp-<env>-<svc>-running-count-low`| Tasks <`service_min_count` for 2 min     |
| `dhp-<env>-orchestrator-dlq`       | Any DLQ publish in last 5 min            |

### ECS auto-scaling
- Per-service target tracking on `ECSServiceAverageCPUUtilization` (default target 60%) and `ALBRequestCountPerTarget` (target 200/min/task).
- Bounds: `service_min_count` (default 2) ↔ `service_max_count` (default 10).
- Cooldowns: 60s scale-out, 300s scale-in.
- Orchestrator is intentionally NOT auto-scaled (Kafka consumer group concurrency is the limit).

### Dead-letter queue
- Topic: `spark-job-submissions-dlq` (override via `KAFKA_DLQ_TOPIC` env).
- Orchestrator retries `RunTask` failures up to `max_retries` (per job event, default 3) with exponential backoff (capped at 30s). On exhaustion the original event + `{error, attempts, host, timestamp}` is published to the DLQ.
- Replay path: drain the DLQ topic with `kafka-console-consumer` (or any tool), inspect, and re-publish to `spark-job-submissions` after fixing the root cause.

See [`disaster-recovery.md`](./disaster-recovery.md) for RTO/RPO targets and restore procedures.

## Phase 3 features

### Custom Prometheus business metrics
All FastAPI services expose domain counters/gauges/histograms in addition to standard HTTP metrics. The orchestrator (no FastAPI app) runs `aiohttp` on port `9000` exposing `/metrics` and `/health`; the ECS task SG allows `9000` self-ingress so Prometheus (or any side-car scraper in the same SG) can pull them. See README §Observability for the full metric catalog.

### Spark History Server
- Image: `spark-images/spark-history` (`apache/spark:3.5.1` + entrypoint setting `spark.history.fs.logDirectory=s3a://<logs-bucket>/spark-events/` and `spark.history.ui.proxyBase=/spark-history`).
- Service: `aws_ecs_service.spark_history`, 1 vCPU / 2 GiB, 1 task. ALB rule priority 140 routes `/spark-history*` to target group port 18080. Health check `/spark-history/api/v1/applications`.
- IAM: dedicated read-only role on the logs bucket.
- Spark tasks emit event logs automatically when `S3_LOGS_BUCKET` is set (compressed gzipped events).

### Job scheduling (cron)
- Migration `0002_scheduled_jobs` creates the `scheduled_jobs` table with a partial index on `(next_run_at) WHERE enabled`.
- Routes: `POST/GET/PUT/DELETE /api/v1/schedules` and `POST /api/v1/schedules/{id}/trigger` on Job Service (cron validated with `croniter`).
- Orchestrator runs a scheduler loop every `SCHEDULER_TICK_SECONDS` (default 30s); each tick uses `pg_try_advisory_lock(0x4448505F5343484C)` so only one replica fires schedules at a time. Due rows are materialized as Kafka submissions and `next_run_at` advances in the schedule's timezone, stored UTC.

### Iceberg + Glue catalog
- Terraform creates `aws_glue_catalog_database.dhp` (location `s3://<warehouse-bucket>/iceberg/`).
- IAM: Spark task role and metadata-service task role get `glue:Get/Create/Update/Delete*` on the database, tables, and partitions.
- Spark base image bundles `iceberg-spark-runtime-3.5_2.12-1.5.0.jar` + `iceberg-aws-bundle-1.5.0.jar`. Iceberg SQL extensions are always on; the `glue` catalog is enabled when `GLUE_CATALOG_DATABASE` is set.
- Metadata Service mirrors `create_table` / `drop_table` to Glue best-effort and exposes `POST /api/v1/databases/{db_name}/sync-glue` to backfill.

### Lineage
- New service at `services/lineage-service` (FastAPI, port 8000, ALB path `/lineage`, priority 150).
- Migration `0003_lineage` creates `lineage_runs`, `lineage_datasets`, `lineage_run_inputs`, `lineage_run_outputs`.
- Spark base image bundles `openlineage-spark_2.12-1.20.4.jar`. When `LINEAGE_URL` is provided, the runtime registers `OpenLineageSparkListener` with HTTP transport, namespace `dhp`, and `JOB_ID` captured via the custom_environment_variables facet.
- Endpoints: `POST /api/v1/lineage`, `GET /jobs/{ns}/{name}/runs`, `GET /datasets/{ns}/{name}`, `.../upstream`, `.../downstream` (recursive CTE bounded to 10 hops).
