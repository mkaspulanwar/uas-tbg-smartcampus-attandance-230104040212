from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import LinearRegression
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, StringType, StructField, StructType, TimestampType


BASE_PATH = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_PATH / "output"

ATTENDANCE_TOTAL_PATH = OUTPUT_PATH / "attendance_total"
ATTENDANCE_TIME_PATH = OUTPUT_PATH / "attendance_time"
ML_ATTENDANCE_PATH = OUTPUT_PATH / "ml_attendance"

BUILDINGS = [
    "Fakultas Sains dan Teknologi",
    "Perpustakaan",
    "Auditorium",
]

OBSERVATION_MINUTES = 12 * 60
OBSERVATION_START_TIME = datetime(2026, 6, 11, 6, 0, 0)
CLASS_START_HOUR = 9


def clamp_attendance(value: float) -> int:
    return int(min(20, max(0, round(value))))


def peak(minute: int, center: int, width: int, amplitude: int) -> float:
    distance = abs(minute - center)
    return max(0, amplitude * (1 - distance / width))


def create_spark_session() -> SparkSession:
    return (
        SparkSession.builder.appName("Smart Campus Attendance Analytics")
        .master("local[*]")
        .config("spark.sql.session.timeZone", "Asia/Makassar")
        .getOrCreate()
    )


def generate_attendance_rows() -> list[tuple[datetime, str, int]]:
    random.seed(42)
    rows: list[tuple[datetime, str, int]] = []

    for minute in range(OBSERVATION_MINUTES):
        current_time = OBSERVATION_START_TIME + timedelta(minutes=minute)

        for building in BUILDINGS:
            noise = random.uniform(-0.5, 1.1)

            if building == "Fakultas Sains dan Teknologi":
                value = (
                    0.15
                    + (0.45 if 150 <= minute < 330 else 0)
                    + (0.40 if 450 <= minute < 540 else 0)
                    + peak(minute, center=150, width=55, amplitude=2.60)
                    + peak(minute, center=240, width=35, amplitude=1.25)
                    + peak(minute, center=450, width=45, amplitude=2.15)
                    + peak(minute, center=330, width=25, amplitude=0.80)
                    + peak(minute, center=540, width=25, amplitude=0.70)
                    + noise
                )
            elif building == "Perpustakaan":
                value = (
                    0.10
                    + (0.45 if 150 <= minute < 330 else 0)
                    + (0.55 if 480 <= minute < 570 else 0)
                    + peak(minute, center=270, width=85, amplitude=1.45)
                    + peak(minute, center=510, width=65, amplitude=2.05)
                    + noise
                )
            else:
                value = (
                    0.05
                    + (0.60 if 150 <= minute < 420 else 0)
                    + peak(minute, center=150, width=55, amplitude=2.00)
                    + peak(minute, center=285, width=75, amplitude=1.20)
                    + noise
                )

            attendance_count = clamp_attendance(value * 0.92)
            rows.append((current_time, building, attendance_count))

    return rows


def write_parquet_outputs(spark: SparkSession) -> None:
    schema = StructType(
        [
            StructField("timestamp", TimestampType(), False),
            StructField("building", StringType(), False),
            StructField("attendance_count", IntegerType(), False),
        ]
    )
    attendance_df = spark.createDataFrame(generate_attendance_rows(), schema=schema)

    enriched_df = (
        attendance_df.withColumn("hour", F.hour("timestamp"))
        .withColumn("minute", F.minute("timestamp"))
        .withColumn("timestamp_unix", F.unix_timestamp("timestamp"))
    )

    min_timestamp = enriched_df.agg(F.min("timestamp_unix").alias("min_timestamp")).first()[
        "min_timestamp"
    ]

    attendance_total_df = (
        enriched_df.groupBy("building")
        .agg(F.sum("attendance_count").alias("total_attendance"))
        .orderBy(F.desc("total_attendance"))
    )

    attendance_time_df = (
        enriched_df.withColumn(
            "bucket_index",
            F.floor((F.col("timestamp_unix") - F.lit(min_timestamp)) / F.lit(20 * 60)),
        )
        .withColumn(
            "time_bucket",
            F.from_unixtime(F.lit(min_timestamp) + (F.col("bucket_index") * F.lit(20 * 60))).cast(
                "timestamp"
            ),
        )
        .groupBy("building", "time_bucket")
        .agg(F.sum("attendance_count").alias("attendance_count"))
        .withColumn("time_bucket", F.date_format("time_bucket", "yyyy-MM-dd HH:mm:ss"))
        .orderBy("time_bucket", "building")
    )

    ml_attendance_df = (
        enriched_df.groupBy("building", "hour")
        .agg(F.sum("attendance_count").alias("attendance_count"))
        .withColumn("hour_squared", F.col("hour") * F.col("hour"))
        .withColumn("hour_cubed", F.col("hour") * F.col("hour") * F.col("hour"))
        .withColumn(
            "is_fst",
            F.when(F.col("building") == "Fakultas Sains dan Teknologi", F.lit(1)).otherwise(
                F.lit(0)
            ),
        )
        .withColumn(
            "is_library",
            F.when(F.col("building") == "Perpustakaan", F.lit(1)).otherwise(F.lit(0)),
        )
        .withColumn(
            "is_auditorium",
            F.when(F.col("building") == "Auditorium", F.lit(1)).otherwise(F.lit(0)),
        )
        .withColumn("fst_hour", F.col("hour") * F.col("is_fst"))
        .withColumn("library_hour", F.col("hour") * F.col("is_library"))
        .withColumn(
            "fst_class_session",
            F.when(
                (F.col("building") == "Fakultas Sains dan Teknologi")
                & (
                    F.col("hour").between(8, 11)
                    | F.col("hour").between(13, 15)
                ),
                F.lit(1),
            ).otherwise(F.lit(0)),
        )
        .withColumn(
            "library_session",
            F.when(
                (F.col("building") == "Perpustakaan")
                & (
                    F.col("hour").between(8, 11)
                    | F.col("hour").between(14, 15)
                ),
                F.lit(1),
            ).otherwise(F.lit(0)),
        )
        .withColumn(
            "auditorium_event",
            F.when(
                (F.col("building") == "Auditorium") & F.col("hour").between(8, 12),
                F.lit(1),
            ).otherwise(F.lit(0)),
        )
        .orderBy("building", "hour")
    )

    feature_columns = [
        "hour",
        "hour_squared",
        "hour_cubed",
        "is_fst",
        "is_library",
        "fst_hour",
        "library_hour",
        "fst_class_session",
        "library_session",
        "auditorium_event",
    ]
    assembler = VectorAssembler(inputCols=feature_columns, outputCol="features")
    ml_ready_df = assembler.transform(ml_attendance_df)

    model = LinearRegression(featuresCol="features", labelCol="attendance_count", regParam=0.01)
    lr_model = model.fit(ml_ready_df)

    prediction_df = (
        lr_model.transform(ml_ready_df)
        .select(
            "building",
            "hour",
            F.round("attendance_count", 2).alias("attendance_count"),
            F.round(F.greatest(F.col("prediction"), F.lit(0)), 2).alias("predicted_attendance"),
        )
        .orderBy("building", "hour")
    )

    attendance_total_df.write.mode("overwrite").parquet(str(ATTENDANCE_TOTAL_PATH))
    attendance_time_df.write.mode("overwrite").parquet(str(ATTENDANCE_TIME_PATH))
    prediction_df.write.mode("overwrite").parquet(str(ML_ATTENDANCE_PATH))

    print("Spark berhasil dijalankan.")
    print(f"Parquet total mahasiswa: {ATTENDANCE_TOTAL_PATH}")
    print(f"Parquet tren 20 menit: {ATTENDANCE_TIME_PATH}")
    print(f"Parquet dataset AI: {ML_ATTENDANCE_PATH}")
    print(f"Linear Regression coefficient: {lr_model.coefficients[0]:.4f}")
    print(f"Linear Regression intercept: {lr_model.intercept:.4f}")


def main() -> None:
    spark = create_spark_session()
    try:
        write_parquet_outputs(spark)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
