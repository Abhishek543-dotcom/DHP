#!/bin/bash
# Run Spark History Server in the foreground so ECS treats this container's
# liveness as the JVM process itself.
set -euo pipefail

: "${S3_LOGS_BUCKET:?S3_LOGS_BUCKET env var must be set}"

# Re-resolve SPARK_HISTORY_OPTS at runtime so the bucket env var is expanded
# now (Dockerfile ENV captures literal text).
export SPARK_HISTORY_OPTS="\
-Dspark.history.fs.logDirectory=s3a://${S3_LOGS_BUCKET}/spark-events/ \
-Dspark.history.fs.cleaner.enabled=true \
-Dspark.history.fs.cleaner.maxAge=14d \
-Dspark.history.ui.port=18080 \
-Dspark.history.ui.proxyBase=/spark-history \
-Dspark.hadoop.fs.s3a.aws.credentials.provider=com.amazonaws.auth.DefaultAWSCredentialsProviderChain \
-Dspark.hadoop.fs.s3a.path.style.access=false"

exec /opt/spark/bin/spark-class org.apache.spark.deploy.history.HistoryServer
