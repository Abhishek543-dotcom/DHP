resource "aws_ecs_cluster" "main" {
  name = "${local.name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# ---- API service task definitions ----
locals {
  account_id = data.aws_caller_identity.current.account_id
  ecr_base   = "${local.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"

  # Common environment shared by all services. Sensitive values come via `secrets`.
  common_env = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "KAFKA_BROKERS", value = aws_msk_serverless_cluster.main.bootstrap_brokers_sasl_iam },
    { name = "REDIS_URL", value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:6379" },
    { name = "S3_REGION", value = var.aws_region },
    { name = "S3_WAREHOUSE_BUCKET", value = aws_s3_bucket.lakehouse["warehouse"].bucket },
    { name = "S3_RAW_BUCKET", value = aws_s3_bucket.lakehouse["raw"].bucket },
    { name = "S3_SCRIPTS_BUCKET", value = aws_s3_bucket.lakehouse["scripts"].bucket },
    { name = "S3_LOGS_BUCKET", value = aws_s3_bucket.lakehouse["logs"].bucket },
    { name = "GLUE_CATALOG_DATABASE", value = aws_glue_catalog_database.dhp.name },
    # Service discovery via internal ALB hostnames (use service-discovery DNS in a follow-up).
    { name = "JOB_SERVICE_URL", value = "http://${aws_lb.main.dns_name}/jobs" },
    { name = "LOG_SERVICE_URL", value = "http://${aws_lb.main.dns_name}/logs" },
  ]

  common_secrets = [
    { name = "API_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:API_KEY::" },
    { name = "INTERNAL_API_TOKEN", valueFrom = "${aws_secretsmanager_secret.app.arn}:INTERNAL_API_TOKEN::" },
    { name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_URL::" },
  ]
}

resource "aws_ecs_task_definition" "service" {
  for_each                 = local.services
  family                   = "${local.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.service_cpu
  memory                   = var.service_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.task[each.key].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = each.key
      image     = "${local.ecr_base}/${local.name}/${each.key}:${lookup(var.service_image_tags, each.key, var.image_tag)}"
      essential = true
      portMappings = [{
        containerPort = each.value.port
        protocol      = "tcp"
      }]
      environment = local.common_env
      secrets     = local.common_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service[each.key].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = each.key
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${each.value.port}${each.value.health} || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  ])
}

resource "aws_ecs_service" "service" {
  for_each        = local.services
  name            = "${local.name}-${each.key}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = var.service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.service[each.key].arn
    container_name   = each.key
    container_port   = each.value.port
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  # Allow CI to push new image tags and Application Auto Scaling to manage
  # desired_count without Terraform reverting either on subsequent applies.
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.http]
}

# ---- Orchestrator (no ALB target group) ----
resource "aws_ecs_task_definition" "orchestrator" {
  family                   = "${local.name}-orchestrator"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.task["orchestrator"].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "orchestrator"
      image     = "${local.ecr_base}/${local.name}/orchestrator:${lookup(var.service_image_tags, "orchestrator", var.image_tag)}"
      essential = true
      portMappings = [
        # /metrics + /health endpoint served by app.metrics_server.MetricsServer.
        # Reachable on the task's awsvpc ENI from a Prometheus scraper or the ALB
        # internal target group; not exposed publicly.
        { containerPort = 9000, protocol = "tcp" }
      ]
      environment = concat(local.common_env, [
        { name = "ECS_CLUSTER", value = aws_ecs_cluster.main.name },
        { name = "SPARK_TASK_DEFINITION", value = aws_ecs_task_definition.spark.arn },
        { name = "SPARK_SUBNETS", value = join(",", aws_subnet.private[*].id) },
        { name = "SPARK_SECURITY_GROUP", value = aws_security_group.ecs_tasks.id },
        { name = "SPARK_LOG_GROUP", value = aws_cloudwatch_log_group.service["spark"].name },
      ])
      secrets = local.common_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["orchestrator"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "orchestrator"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "orchestrator" {
  name            = "${local.name}-orchestrator"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.orchestrator.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}

# ---- DB migrations one-shot task definition (run via ecs run-task on deploy) ----
resource "aws_ecs_task_definition" "db_migrations" {
  family                   = "${local.name}-db-migrations"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "migrations"
      image     = "${local.ecr_base}/${local.name}/db-migrations:${lookup(var.service_image_tags, "db-migrations", var.image_tag)}"
      essential = true
      secrets = [
        { name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_URL::" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["orchestrator"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "migrations"
        }
      }
    }
  ])
}

# ---- Spark task definition (template - launched via ecs:RunTask by orchestrator) ----
resource "aws_ecs_task_definition" "spark" {
  family                   = "${local.name}-spark"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.spark_task_cpu
  memory                   = var.spark_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.spark_task.arn

  ephemeral_storage {
    size_in_gib = 50
  }

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "spark"
      image     = "${local.ecr_base}/${local.name}/spark-base:${lookup(var.service_image_tags, "spark-base", var.image_tag)}"
      essential = true
      # Orchestrator overrides command/env per RunTask call.
      environment = [
        { name = "AWS_REGION", value = var.aws_region },
        { name = "S3_WAREHOUSE_BUCKET", value = aws_s3_bucket.lakehouse["warehouse"].bucket },
        { name = "S3_SCRIPTS_BUCKET", value = aws_s3_bucket.lakehouse["scripts"].bucket },
        { name = "S3_LOGS_BUCKET", value = aws_s3_bucket.lakehouse["logs"].bucket },
        { name = "GLUE_CATALOG_DATABASE", value = aws_glue_catalog_database.dhp.name },
        { name = "LINEAGE_URL", value = "http://${aws_lb.main.dns_name}/lineage" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["spark"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "spark"
        }
      }
    }
  ])
}
