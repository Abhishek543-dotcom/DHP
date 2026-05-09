# =============================================================================
# AWS Glue Data Catalog — Iceberg integration
# =============================================================================
# Spark jobs and the metadata-service write Iceberg tables through Glue using
# `org.apache.iceberg.aws.glue.GlueCatalog`. This makes DHP datasets readable
# from Athena, EMR, and Snowflake without bespoke metadata bridges.
# =============================================================================

resource "aws_glue_catalog_database" "dhp" {
  name        = replace(local.name, "-", "_")
  description = "DHP lakehouse catalog (Iceberg tables) for ${var.environment}"

  # Glue locations are advisory; actual data lives under the warehouse bucket
  # at s3://<warehouse>/iceberg/<database>/<table>/.
  location_uri = "s3://${aws_s3_bucket.lakehouse["warehouse"].bucket}/iceberg/"
}

# Glue access policy granted to spark-task and metadata-service roles.
data "aws_iam_policy_document" "glue_iceberg_access" {
  statement {
    sid = "GlueDatabaseRead"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${local.account_id}:catalog",
      aws_glue_catalog_database.dhp.arn,
    ]
  }
  statement {
    sid = "GlueTableReadWrite"
    actions = [
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:CreatePartition",
      "glue:UpdatePartition",
      "glue:DeletePartition",
      "glue:BatchCreatePartition",
      "glue:BatchDeletePartition",
      "glue:BatchUpdatePartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${local.account_id}:catalog",
      aws_glue_catalog_database.dhp.arn,
      "arn:aws:glue:${var.aws_region}:${local.account_id}:table/${aws_glue_catalog_database.dhp.name}/*",
    ]
  }
}

resource "aws_iam_role_policy" "spark_task_glue" {
  name   = "glue-iceberg-access"
  role   = aws_iam_role.spark_task.id
  policy = data.aws_iam_policy_document.glue_iceberg_access.json
}

resource "aws_iam_role_policy" "metadata_service_glue" {
  name   = "glue-iceberg-access"
  role   = aws_iam_role.task["metadata-service"].id
  policy = data.aws_iam_policy_document.glue_iceberg_access.json
}
