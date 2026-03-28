#!/bin/bash
# seed-data.sh - Seed initial data for development
set -euo pipefail

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-dev-access-key-change-me}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-dev-secret-key-change-me}"

echo "=== Seeding MinIO buckets ==="

# Install mc (MinIO Client) if not available
if ! command -v mc &> /dev/null; then
    echo "Installing MinIO Client..."
    curl -sL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
    chmod +x /usr/local/bin/mc
fi

# Configure MinIO alias
mc alias set lakehouse "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"

# Create default buckets
mc mb --ignore-existing lakehouse/lakehouse-warehouse
mc mb --ignore-existing lakehouse/lakehouse-raw
mc mb --ignore-existing lakehouse/lakehouse-scripts
mc mb --ignore-existing lakehouse/lakehouse-logs

echo "=== MinIO buckets created ==="

# Upload sample Spark job
mc cp ../spark-images/jobs/sample_etl.py lakehouse/lakehouse-scripts/etl/

echo "=== Seed data complete ==="
