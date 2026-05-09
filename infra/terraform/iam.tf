# ----- ECS task execution role (pulls images, writes logs, reads secrets) -----
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "secrets-read"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.app.arn]
    }]
  })
}

# ----- Per-service task role -----
resource "aws_iam_role" "task" {
  for_each           = toset(concat(keys(local.services), local.background_services))
  name               = "${local.name}-${each.value}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# All services need to read S3 + secrets at minimum.
data "aws_iam_policy_document" "s3_access" {
  statement {
    sid    = "BucketOps"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [for b in aws_s3_bucket.lakehouse : b.arn]
  }
  statement {
    sid    = "ObjectOps"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [for b in aws_s3_bucket.lakehouse : "${b.arn}/*"]
  }
}

resource "aws_iam_role_policy" "task_s3" {
  for_each = aws_iam_role.task
  name     = "s3-access"
  role     = each.value.id
  policy   = data.aws_iam_policy_document.s3_access.json
}

# MSK IAM access (kafka:Connect/Read/Write/Describe + glue catalog if needed)
data "aws_iam_policy_document" "msk_access" {
  statement {
    actions = [
      "kafka-cluster:Connect",
      "kafka-cluster:DescribeCluster",
      "kafka-cluster:DescribeClusterDynamicConfiguration",
      "kafka-cluster:DescribeTopic",
      "kafka-cluster:CreateTopic",
      "kafka-cluster:WriteData",
      "kafka-cluster:ReadData",
      "kafka-cluster:DescribeGroup",
      "kafka-cluster:AlterGroup",
    ]
    resources = ["${aws_msk_serverless_cluster.main.arn}/*", aws_msk_serverless_cluster.main.arn]
  }
}

resource "aws_iam_role_policy" "task_msk" {
  for_each = aws_iam_role.task
  name     = "msk-access"
  role     = each.value.id
  policy   = data.aws_iam_policy_document.msk_access.json
}

# Orchestrator additionally needs ecs:RunTask + iam:PassRole for the Spark task.
data "aws_iam_policy_document" "orchestrator_ecs" {
  statement {
    sid       = "RunSparkTasks"
    actions   = ["ecs:RunTask", "ecs:StopTask", "ecs:DescribeTasks", "ecs:ListTasks"]
    resources = ["*"]
  }
  statement {
    sid       = "PassRoleToSpark"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.spark_task.arn, aws_iam_role.ecs_task_execution.arn]
  }
}

resource "aws_iam_role_policy" "orchestrator_ecs" {
  name   = "ecs-runtask"
  role   = aws_iam_role.task["orchestrator"].id
  policy = data.aws_iam_policy_document.orchestrator_ecs.json
}

# ----- Spark task role (job pods) -----
resource "aws_iam_role" "spark_task" {
  name               = "${local.name}-spark-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "spark_task_s3" {
  name   = "s3-access"
  role   = aws_iam_role.spark_task.id
  policy = data.aws_iam_policy_document.s3_access.json
}
