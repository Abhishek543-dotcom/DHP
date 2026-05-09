# DHP — Disaster Recovery & Backup

This document describes recovery objectives, backup mechanisms, and step-by-step
restore procedures for the DHP stack on AWS.

## Recovery objectives

| Tier        | RPO  | RTO  | Notes                                          |
|-------------|------|------|------------------------------------------------|
| dev         | 24h  | 4h   | Single AZ, single-node Redis, no Multi-AZ RDS  |
| staging     | 4h   | 2h   | Single AZ, snapshot-driven recovery            |
| prod        | 5min | 1h   | Multi-AZ RDS, PITR, cross-region S3 replication recommended |

RPO = max acceptable data loss. RTO = max acceptable time to restore service.

## What is backed up

| Asset                       | Mechanism                                      |
|-----------------------------|------------------------------------------------|
| Postgres (jobs, catalog)    | RDS automated backups + PITR (`backup_retention_period`) |
| S3 buckets (warehouse, raw) | S3 versioning + 30-day lifecycle on logs       |
| Spark scripts bucket        | S3 versioning                                  |
| Secrets (API keys, DB password) | Secrets Manager built-in versioning        |
| MSK topics (job events)     | MSK retains messages per topic config (default 7 days). DLQ topic retained per same policy |
| ECR images                  | Lifecycle keeps last 20 tags per repo          |
| CloudWatch logs             | 7d (dev) / 30d (prod) retention                |

## What is NOT backed up

- ElastiCache Redis (rate-limit counters only — re-populated organically).
- Running ECS tasks (Spark in-flight jobs are killed on cluster loss; the
  orchestrator will replay un-acked Kafka messages from the consumer group
  offset on restart, *unless* the broker also lost data).

## Restore procedures

### 1. Restore Postgres from PITR

```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier dhp-prod-postgres \
  --target-db-instance-identifier dhp-prod-postgres-restore \
  --restore-time 2026-05-07T08:00:00Z \
  --use-latest-restorable-time   # OR --restore-time <ISO>
```

After verifying the restore, update the Secrets Manager `DATABASE_URL` value
to point at the new endpoint and force a service redeploy:

```bash
aws ecs update-service --cluster dhp-prod --service dhp-prod-job-service --force-new-deployment
# repeat per service
```

### 2. S3 object recovery

Versioning is enabled on all four buckets. To roll back a single object:

```bash
aws s3api list-object-versions --bucket dhp-prod-warehouse --prefix path/to/key
aws s3api copy-object --copy-source 'dhp-prod-warehouse/path/to/key?versionId=<ID>' \
  --bucket dhp-prod-warehouse --key path/to/key
```

For a bucket-wide restore, use [S3 Batch Operations] with the version inventory.

### 3. Secrets recovery

Secrets Manager retains all previous versions. To roll back:

```bash
aws secretsmanager list-secret-version-ids --secret-id dhp-prod/app
aws secretsmanager update-secret-version-stage \
  --secret-id dhp-prod/app \
  --version-stage AWSCURRENT \
  --move-to-version-id <previous-version-id>
```

Then force-redeploy services so containers pick up the rotated secret:

```bash
aws ecs update-service --cluster dhp-prod --service dhp-prod-<svc> --force-new-deployment
```

### 4. Replaying DLQ messages

The orchestrator publishes permanently-failed jobs to
`spark-job-submissions-dlq`. After fixing the root cause:

```bash
# 1. Read the DLQ
kafka-console-consumer --bootstrap-server <msk-bootstrap> \
  --topic spark-job-submissions-dlq --from-beginning --max-messages 100

# 2. Inspect each payload (original_event + error + attempts + timestamp).
# 3. Re-publish ONLY the original_event back to the live topic:
echo '<original_event_json>' | kafka-console-producer \
  --bootstrap-server <msk-bootstrap> \
  --topic spark-job-submissions
```

For MSK Serverless, use the `aws kafka` CLI helpers or a small Python script
that pulls IAM credentials from the local profile.

### 5. Full region failover (prod)

DHP is single-region by default. For multi-region DR:

1. Enable cross-region read replica on RDS.
2. Enable Cross-Region Replication on S3 buckets (warehouse + scripts).
3. Replicate Secrets Manager via the `replica` block.
4. Stand up a parallel Terraform workspace in the failover region (point at
   the same Git tag).
5. Promote the read replica, repoint Route53 to the failover ALB.

This procedure is **not automated** — exercise quarterly and document the
runbook with stopwatch results to validate the prod RTO.

## Routine drills

Perform monthly:

- **Snapshot restore drill**: restore last night's RDS snapshot to a throwaway
  instance and run `psql -c "SELECT count(*) FROM jobs;"` to verify integrity.
- **DLQ replay drill**: publish a deliberately broken job event, verify
  alarm fires, drain DLQ, re-publish, confirm successful run.
- **Secret rotation**: rotate `API_KEY` via Secrets Manager + force-redeploy;
  verify all four services come back healthy without manual intervention.

[S3 Batch Operations]: https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops.html
