# Spark History Server — reads event logs from S3 and serves the UI on :18080.
#
# We reuse the same Spark base distribution as the job container so jar
# versions match exactly (Hadoop AWS, S3A, IAM credentials chain). The
# entrypoint just runs Spark's bundled start-history-server.sh in the
# foreground and tails the log so ECS sees the process.
FROM apache/spark:3.5.1

USER root

# AWS region + logs bucket are injected by the ECS task definition.
ENV SPARK_HISTORY_OPTS="\
  -Dspark.history.fs.logDirectory=s3a://${S3_LOGS_BUCKET:-changeme}/spark-events/ \
  -Dspark.history.fs.cleaner.enabled=true \
  -Dspark.history.fs.cleaner.maxAge=14d \
  -Dspark.history.ui.port=18080 \
  -Dspark.hadoop.fs.s3a.aws.credentials.provider=com.amazonaws.auth.DefaultAWSCredentialsProviderChain \
  -Dspark.hadoop.fs.s3a.path.style.access=false"

EXPOSE 18080

# start-history-server.sh forks into the background; we wrap it so the
# foreground process is the actual Java history server, otherwise ECS would
# kill the task immediately.
COPY entrypoint.sh /opt/dhp-entrypoint.sh
RUN chmod +x /opt/dhp-entrypoint.sh

USER spark

ENTRYPOINT ["/opt/dhp-entrypoint.sh"]
