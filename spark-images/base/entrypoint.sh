#!/bin/bash
# =============================================================
# Lakehouse Spark Container Entrypoint
# =============================================================
# This script:
# 1. Tags all output with JOB_ID for log isolation
# 2. Configures S3/Iceberg settings
# 3. Launches the Spark job
# 4. Reports completion status back to the Job Service
# =============================================================
set -euo pipefail

echo "============================================"
echo "  Lakehouse Spark Job Container"
echo "  JOB_ID:     ${JOB_ID:-not-set}"
echo "  ENTRYPOINT: ${ENTRYPOINT_SCRIPT:-not-set}"
echo "  STARTED:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================"

# Validate required env vars
: "${JOB_ID:?JOB_ID is required}"
: "${ENTRYPOINT_SCRIPT:?ENTRYPOINT_SCRIPT is required}"

ENTRYPOINT_SCRIPT_RESOLVED="${ENTRYPOINT_SCRIPT}"
if [[ "${ENTRYPOINT_SCRIPT_RESOLVED}" == s3://* ]]; then
    ENTRYPOINT_SCRIPT_RESOLVED="s3a://${ENTRYPOINT_SCRIPT_RESOLVED#s3://}"
fi

# S3 configuration
S3_ENDPOINT="${S3_ENDPOINT:-http://minio:9000}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-dev-access-key-change-me}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-dev-secret-key-change-me}"

# Build Spark configuration
SPARK_CONF=""
SPARK_CONF="${SPARK_CONF} --conf spark.app.id=${JOB_ID}"
SPARK_CONF="${SPARK_CONF} --conf spark.driver.extraJavaOptions=-Djob.id=${JOB_ID}"
SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.endpoint=${S3_ENDPOINT}"
SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.access.key=${AWS_ACCESS_KEY_ID}"
SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.secret.key=${AWS_SECRET_ACCESS_KEY}"
SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.path.style.access=true"
SPARK_CONF="${SPARK_CONF} --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem"
SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.lakehouse=org.apache.iceberg.spark.SparkCatalog"
SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.lakehouse.type=hadoop"
SPARK_CONF="${SPARK_CONF} --conf spark.sql.catalog.lakehouse.warehouse=s3a://lakehouse-warehouse/"

# Append any extra Spark config from env
if [ -n "${SPARK_EXTRA_CONF:-}" ]; then
    SPARK_CONF="${SPARK_CONF} ${SPARK_EXTRA_CONF}"
fi

# Log file path
LOG_FILE="/var/log/spark/${JOB_ID}.log"
CALLBACK_URL="${CALLBACK_URL:-}"
INTERNAL_API_TOKEN="${INTERNAL_API_TOKEN:-}"

report_status() {
    local status="$1"
    local exit_code="$2"

    if [ -z "${CALLBACK_URL}" ]; then
        return 0
    fi

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
        --retry 3 \
        --retry-delay 5 \
        --max-time 30 || echo "[WARN] Failed to report job status (${status})"
}

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [INFO] Starting Spark submit..." | tee -a "${LOG_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [INFO] Reporting RUNNING status to callback endpoint" | tee -a "${LOG_FILE}"
report_status "RUNNING" "null"

# Launch Spark
set +e
/opt/spark/bin/spark-submit \
    --master local[*] \
    ${SPARK_CONF} \
    ${ENTRYPOINT_SCRIPT_RESOLVED} \
    ${ARGUMENTS:-} 2>&1 | tee -a "${LOG_FILE}"
EXIT_CODE=${PIPESTATUS[0]}
set -e

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [INFO] Spark job finished with exit code: ${EXIT_CODE}" | tee -a "${LOG_FILE}"

# Determine status
if [ ${EXIT_CODE} -eq 0 ]; then
    STATUS="SUCCESS"
else
    STATUS="FAILED"
fi

# Report back to Job Service
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [INFO] Reporting final status '${STATUS}' to callback endpoint" | tee -a "${LOG_FILE}"
report_status "${STATUS}" "${EXIT_CODE}"

# Wait briefly for logs to flush
sleep 5

exit ${EXIT_CODE}
