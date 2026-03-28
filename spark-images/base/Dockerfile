FROM apache/spark:3.5.0-python3

USER root

# ============================================
# Install Iceberg + S3 dependencies
# ============================================
RUN curl -L -o /opt/spark/jars/iceberg-spark-runtime-3.5_2.12-1.5.0.jar \
    https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.0/iceberg-spark-runtime-3.5_2.12-1.5.0.jar && \
    curl -L -o /opt/spark/jars/aws-java-sdk-bundle-1.12.661.jar \
    https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.661/aws-java-sdk-bundle-1.12.661.jar && \
    curl -L -o /opt/spark/jars/hadoop-aws-3.3.4.jar \
    https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar

# ============================================
# Install system dependencies
# ============================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# ============================================
# Create log directories
# ============================================
RUN mkdir -p /var/log/spark && chmod 777 /var/log/spark

# ============================================
# Copy entrypoint script
# ============================================
COPY entrypoint.sh /opt/spark/entrypoint.sh
RUN chmod +x /opt/spark/entrypoint.sh

# ============================================
# Copy Fluent Bit config
# ============================================
COPY fluent-bit.conf /etc/fluent-bit/fluent-bit.conf

ENTRYPOINT ["/opt/spark/entrypoint.sh"]

