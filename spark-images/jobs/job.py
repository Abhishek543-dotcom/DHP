from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, IntegerType, DoubleType
import random

def main():
    # Initialize SparkSession
    spark = SparkSession.builder \
        .appName("RandomDataGenerator") \
        .getOrCreate()

    # Generate random data
    num_rows = 100
    data = [(i, random.randint(1, 100), random.random() * 100.0) for i in range(num_rows)]

    # Define schema
    schema = StructType([
        StructField("id", IntegerType(), True),
        StructField("random_int", IntegerType(), True),
        StructField("random_double", DoubleType(), True)
    ])

    # Create DataFrame
    df = spark.createDataFrame(data, schema)

    # Show the DataFrame
    print("Showing generated random data:")
    df.show(truncate=False)

    # Stop the SparkSession
    spark.stop()

if __name__ == "__main__":
    main()
