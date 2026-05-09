# =============================================================================
# Spark History Server
# =============================================================================
# Reads Spark event logs from s3://<logs-bucket>/spark-events/ and serves the
# UI on port 18080 behind the ALB at /spark-history*. One task is sufficient
# (history server is read-only and stateless beyond an in-memory cache).
# =============================================================================

resource "aws_iam_role" "spark_history" {
  name               = "${local.name}-spark-history-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Read-only access to the logs bucket; no MSK / Secrets Manager attachment.
data "aws_iam_policy_document" "spark_history_logs" {
  statement {
    actions = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [
      aws_s3_bucket.lakehouse["logs"].arn,
    ]
  }
  statement {
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.lakehouse["logs"].arn}/spark-events/*",
    ]
  }
}

resource "aws_iam_role_policy" "spark_history_logs" {
  name   = "logs-read"
  role   = aws_iam_role.spark_history.id
  policy = data.aws_iam_policy_document.spark_history_logs.json
}

resource "aws_lb_target_group" "spark_history" {
  name        = "${local.name}-spark-history"
  port        = 18080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    # The history server returns 200 for the API endpoint as soon as it
    # finishes its first scan of the event log directory (which is fast even
    # when empty). Plain "/" returns the HTML which is also fine.
    path                = "/spark-history/api/v1/applications"
    port                = "traffic-port"
    matcher             = "200-299"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 15
}

resource "aws_lb_listener_rule" "spark_history" {
  listener_arn = var.acm_certificate_arn != "" ? aws_lb_listener.https[0].arn : aws_lb_listener.http.arn
  priority     = 140

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.spark_history.arn
  }

  condition {
    path_pattern {
      values = ["/spark-history", "/spark-history/*"]
    }
  }
}

resource "aws_ecs_task_definition" "spark_history" {
  family                   = "${local.name}-spark-history"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.spark_history.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "spark-history"
      image     = "${local.ecr_base}/${local.name}/spark-history:${lookup(var.service_image_tags, "spark-history", var.image_tag)}"
      essential = true
      portMappings = [{
        containerPort = 18080
        protocol      = "tcp"
      }]
      environment = [
        { name = "AWS_REGION", value = var.aws_region },
        { name = "S3_LOGS_BUCKET", value = aws_s3_bucket.lakehouse["logs"].bucket },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["spark-history"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "spark-history"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:18080/spark-history/api/v1/applications || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 60
      }
    }
  ])
}

resource "aws_ecs_service" "spark_history" {
  name            = "${local.name}-spark-history"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.spark_history.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.spark_history.arn
    container_name   = "spark-history"
    container_port   = 18080
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 200

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}
