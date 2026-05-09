#!/bin/bash
# =============================================================
# DHP Spark task entrypoint (AWS-aware)
# =============================================================
# Behaviour:
#   * If S3_ENDPOINT is set (local MinIO), uses path-style + static creds.
#   * Otherwise (AWS): no endpoint override, IAM task role provides creds
#     via the EC2/ECS metadata service.
#   * Reports RUNNING and final status to the Job Service callback.
# =============================================================
set -euo pipefail

echo "============================================"
echo "  DHP Spark Job Container"
echo "  JOB_ID:     ${JOB_ID:-not-set}"
echo "  ENTRYPOINT: ${ENTRYPOINT_SCRIPT:-not-set}"
echo "  STARTED:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================"

: "${JOB_ID:?JOB_ID is required}"
: "${ENTRYPOINT_SCRIPT:?ENTRYPOINT_SCRIPT is required}"

ENTRYPOINT_SCRIPT_RESOLVED="${ENTRYPOINT_SCRIPT}"
if [[ "${ENTRYPOINT_SCRIPT_RESOLVED}" == s3://* ]]; then
    ENTRYPOINT_SCRIPT_RESOLVED="s3a://${ENTRYPOINT_SCRIPT_RESOLVED#s3://}"
fi

S3_ENDPOINT="${S3_ENDPOINT:-}"
WAREHOUSE_BUCKET="${S3_WAREHOUSE_BUCKET:-lakehouse-warehouse}"

SPARK_CONF=""
SPARK_CONF="${SPARK_CONF} --conf spark.app.id=${JOB_ID}"
SPARK_CONF="${SPARK_CONF} --conf spark.driver.extraJavaOptions=-Djob.id=${JOB_ID}"
SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem"

# Iceberg SQL extensions (CALL, MERGE, UPDATE/DELETE syntax).
SPARK_CONF="${SPARK_CONF} --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"

# Default Iceberg catalog backed by Hadoop (filesystem) — kept for offline /
# docker-compose runs where Glue isn't available. Iceberg metadata lives at
# s3a://<warehouse>/<db>/<table>/metadata/.
SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.lakehouse=org.apache.iceberg.spark.SparkCatalog"
SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.lakehouse.type=hadoop"
SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.lakehouse.warehouse=s3a://${WAREHOUSE_BUCKET}/"

# Optional Glue Iceberg catalog. Enabled when the orchestrator passes
# GLUE_CATALOG_DATABASE; jobs reference tables as `glue.<db>.<table>`.
GLUE_DB="${GLUE_CATALOG_DATABASE:-}"
if [ -n "${GLUE_DB}" ]; then
    SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.glue=org.apache.iceberg.spark.SparkCatalog"
    SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.glue.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog"
    SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.glue.io-impl=org.apache.iceberg.aws.s3.S3FileIO"
    SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.glue.warehouse=s3://${WAREHOUSE_BUCKET}/iceberg/"
    SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.glue.glue.skip-archive=true"
fi

# Spark event logging — required by the dedicated Spark History Server
# service to inspect completed jobs. Logs are partitioned per job_id so the
# history server can list runs without scanning unrelated streams.
LOGS_BUCKET="${S3_LOGS_BUCKET:-}"
if [ -n "${LOGS_BUCKET}" ]; then
    SPARK_CONF="${SPARK_CONF} --conf spark.eventLog.enabled=true"
    SPARK_CONF="${SPARK_CONF} --conf spark.eventLog.dir=s3a://${LOGS_BUCKET}/spark-events/"
    SPARK_CONF="${SPARK_CONF} --conf spark.eventLog.compress=true"
    SPARK_CONF="${SPARK_CONF} --conf spark.history.fs.logDirectory=s3a://${LOGS_BUCKET}/spark-events/"
fi

# OpenLineage transport — Spark publishes RunEvents to the lineage-service
# HTTP endpoint when LINEAGE_URL is set. Falls back to no-op listener when
# unset (tests / docker-compose without lineage-service).
LINEAGE_URL="${LINEAGE_URL:-}"
if [ -n "${LINEAGE_URL}" ]; then
    SPARK_CONF="${SPARK_CONF} --conf spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener"
    SPARK_CONF="${SPARK_CONF} --conf spark.openlineage.transport.type=http"
    SPARK_CONF="${SPARK_CONF} --conf spark.openlineage.transport.url=${LINEAGE_URL}"
    SPARK_CONF="${SPARK_CONF} --conf spark.openlineage.transport.endpoint=/api/v1/lineage"
    SPARK_CONF="${SPARK_CONF} --conf spark.openlineage.namespace=dhp"
    # Stamp the DHP job_id into emitted facets so lineage-service can map
    # OpenLineage runs back to the orchestrator's Job entity.
    SPARK_CONF="${SPARK_CONF} --conf spark.openlineage.facets.custom_environment_variables=[JOB_ID]"
    if [ -n "${LINEAGE_API_KEY:-}" ]; then
        SPARK_CONF="${SPARK_CONF} --conf spark.openlineage.transport.auth.type=api_key"
        SPARK_CONF="${SPARK_CONF} --conf spark.openlineage.transport.auth.apiKey=${LINEAGE_API_KEY}"
    fi
fi

if [ -n "${S3_ENDPOINT}" ]; then
    # Local / MinIO mode: static creds, path-style.
    export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-dev-access-key-change-me}"
    export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-dev-secret-key-change-me}"
    SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.endpoint=${S3_ENDPOINT}"
    SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.access.key=${AWS_ACCESS_KEY_ID}"
    SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.secret.key=${AWS_SECRET_ACCESS_KEY}"
    SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.path.style.access=true"
else
    # AWS mode: IAM task role via container credentials provider.
    # Hadoop 3.3.x supports the IAMInstanceCredentialsProvider, which works
    # for both EC2 and ECS task roles via the metadata endpoint.
    SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.aws.credentials.provider=com.amazonaws.auth.DefaultAWSCredentialsProviderChain"
    SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.path.style.access=false"
    if [ -n "${AWS_REGION:-}" ]; then
        SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.endpoint.region=${AWS_REGION}"
    fi
fi

if [ -n "${SPARK_EXTRA_CONF:-}" ]; then
    SPARK_CONF="${SPARK_CONF} ${SPARK_EXTRA_CONF}"
fi

LOG_FILE="/var/log/spark/${JOB_ID}.log"
mkdir -p /var/log/spark
CALLBACK_URL="${CALLBACK_URL:-}"
INTERNAL_API_TOKEN="${INTERNAL_API_TOKEN:-}"

report_status() {
    local status="$1"
    local exit_code="$2"
    [ -z "${CALLBACK_URL}" ] && return 0

    local payload
    payload=$(jq -n \
        --arg status "${status}" \
        --argjson exit_code "${exit_code}" \
        '{status: $status, exit_code: $exit_code}')

    local auth_header=()
    if [ -n "${INTERNAL_API_TOKEN}" ]; then
        auth_header=(-H "X-Internal-Token: ${INTERNAL_API_TOKEN}")
    fi

    curl -s -X PUT "${CALLBACK_URL}" \
        -H "Content-Type: application/json" \
        "${auth_header[@]}" \
        -d "${payload}" \
        --retry 3 --retry-delay 5 --max-time 30 \
        || echo "[WARN] Failed to report job status (${status})"
}

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [INFO] Reporting RUNNING" | tee -a "${LOG_FILE}"
report_status "RUNNING" "null"

set +e
/opt/spark/bin/spark-submit \
    --master local[*] \
    ${SPARK_CONF} \
    ${ENTRYPOINT_SCRIPT_RESOLVED} \
    ${ARGUMENTS:-} 2>&1 | tee -a "${LOG_FILE}"
EXIT_CODE=${PIPESTATUS[0]}
set -e

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [INFO] spark-submit exit=${EXIT_CODE}" | tee -a "${LOG_FILE}"

if [ ${EXIT_CODE} -eq 0 ]; then
    STATUS="SUCCESS"
else
    STATUS="FAILED"
fi

report_status "${STATUS}" "${EXIT_CODE}"
sleep 2
exit ${EXIT_CODE}
