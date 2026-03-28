"""
Sample ETL Job for the Lakehouse Platform.

This job demonstrates:
- Reading from object storage (S3/MinIO)
- Data transformation with PySpark
- Writing to an Iceberg table in the lakehouse
- Proper logging with job_id context
"""
import argparse
import logging
import sys
import os
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType,
    StructField,
    LongType,
    StringType,
    DoubleType,
    TimestampType,
)

# Setup logging
job_id = os.getenv("JOB_ID", "local-dev")
logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [%(levelname)s] [job_id={job_id}] %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Sales ETL Job")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--mode", type=str, default="append", choices=["append", "overwrite"])
    parser.add_argument("--source", type=str, default="s3a://lakehouse-raw/sales/")
    parser.add_argument("--target-db", type=str, default="sales_db")
    parser.add_argument("--target-table", type=str, default="transactions")
    return parser.parse_args()


def create_spark_session() -> SparkSession:
    """Create a Spark session with Iceberg and S3 support."""
    return (
        SparkSession.builder
        .appName(f"lakehouse-etl-{job_id}")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .getOrCreate()
    )


def generate_sample_data(spark: SparkSession, date_str: str):
    """Generate sample data if source doesn't exist (for testing)."""
    schema = StructType([
        StructField("transaction_id", LongType(), False),
        StructField("customer_id", LongType(), False),
        StructField("amount", DoubleType(), False),
        StructField("currency", StringType(), True),
        StructField("product_category", StringType(), True),
        StructField("transaction_date", StringType(), False),
    ])

    import random
    data = []
    categories = ["electronics", "clothing", "food", "books", "sports"]
    currencies = ["USD", "EUR", "GBP", "JPY"]

    for i in range(1000):
        data.append((
            i + 1,
            random.randint(1, 100),
            round(random.uniform(10.0, 500.0), 2),
            random.choice(currencies),
            random.choice(categories),
            date_str,
        ))

    return spark.createDataFrame(data, schema)


def run_etl(spark: SparkSession, args):
    """Main ETL logic."""
    logger.info(f"Starting ETL for date={args.date}, mode={args.mode}")

    # Read source data
    logger.info(f"Reading source data from: {args.source}")
    try:
        source_path = f"{args.source}{args.date}/"
        raw_df = spark.read.parquet(source_path)
        logger.info(f"Read {raw_df.count()} records from source")
    except Exception:
        logger.warning("Source data not found, generating sample data")
        raw_df = generate_sample_data(spark, args.date)
        logger.info(f"Generated {raw_df.count()} sample records")

    # ============================================
    # Transform
    # ============================================
    logger.info("Applying transformations...")

    transformed_df = (
        raw_df
        # Filter out invalid records
        .filter(F.col("amount") > 0)
        # Add processing metadata
        .withColumn("processed_at", F.current_timestamp())
        .withColumn("etl_job_id", F.lit(job_id))
        .withColumn("processing_date", F.lit(args.date))
        # Parse transaction date
        .withColumn("transaction_ts", F.to_timestamp("transaction_date", "yyyy-MM-dd"))
        # Add derived columns
        .withColumn(
            "amount_usd",
            F.when(F.col("currency") == "EUR", F.col("amount") * 1.08)
            .when(F.col("currency") == "GBP", F.col("amount") * 1.27)
            .when(F.col("currency") == "JPY", F.col("amount") * 0.0067)
            .otherwise(F.col("amount")),
        )
    )

    record_count = transformed_df.count()
    logger.info(f"Transformation complete: {record_count} records")

    # ============================================
    # Write to Iceberg table
    # ============================================
    target = f"lakehouse.{args.target_db}.{args.target_table}"
    logger.info(f"Writing to {target} (mode={args.mode})")

    try:
        if args.mode == "overwrite":
            transformed_df.writeTo(target).overwritePartitions()
        else:
            transformed_df.writeTo(target).append()
        logger.info(f"Successfully wrote {record_count} records to {target}")
    except Exception as e:
        # If table doesn't exist, create it
        logger.warning(f"Write failed ({e}), attempting to create table and retry...")
        transformed_df.writeTo(target).using("iceberg").createOrReplace()
        logger.info(f"Created table and wrote {record_count} records to {target}")

    # ============================================
    # Verify
    # ============================================
    logger.info("Verifying written data...")
    verify_df = spark.sql(f"SELECT count(*) as cnt FROM {target}")
    total_count = verify_df.collect()[0]["cnt"]
    logger.info(f"Verification: {total_count} total records in {target}")

    return record_count


def main():
    args = parse_args()

    logger.info("=" * 60)
    logger.info(f"  Lakehouse ETL Job")
    logger.info(f"  Job ID:    {job_id}")
    logger.info(f"  Date:      {args.date}")
    logger.info(f"  Mode:      {args.mode}")
    logger.info(f"  Source:    {args.source}")
    logger.info(f"  Target:    {args.target_db}.{args.target_table}")
    logger.info("=" * 60)

    spark = create_spark_session()

    try:
        record_count = run_etl(spark, args)
        logger.info(f"ETL completed successfully: {record_count} records processed")
    except Exception as e:
        logger.error(f"ETL failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        spark.stop()
        logger.info("Spark session stopped")


if __name__ == "__main__":
    main()

