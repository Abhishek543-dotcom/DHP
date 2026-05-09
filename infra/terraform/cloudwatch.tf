resource "aws_cloudwatch_log_group" "service" {
  for_each          = toset(concat(keys(local.services), local.background_services, ["spark", "spark-history"]))
  name              = "/dhp/${var.environment}/${each.value}"
  retention_in_days = var.environment == "prod" ? 30 : 7
}

locals {
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# ---- ALB / target health ----
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${local.name}-alb-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  treat_missing_data  = "notBreaching"
  alarm_description   = "Sustained 5xx from DHP services"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  for_each            = local.services
  alarm_name          = "${local.name}-${each.key}-unhealthy-hosts"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_description   = "ALB has unhealthy targets in ${each.key} target group"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
    TargetGroup  = aws_lb_target_group.service[each.key].arn_suffix
  }
}

# ---- RDS ----
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${local.name}-rds-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  alarm_name          = "${local.name}-rds-free-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  # 20% of allocated storage, in bytes.
  threshold          = floor(var.db_allocated_storage * 1024 * 1024 * 1024 * 0.2)
  treat_missing_data = "breaching"
  alarm_description  = "RDS free storage below 20% of allocation"
  alarm_actions      = local.alarm_actions
  ok_actions         = local.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }
}

# ---- ECS task health ----
resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  for_each            = local.services
  alarm_name          = "${local.name}-${each.key}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  treat_missing_data  = "notBreaching"
  alarm_description   = "ECS service ${each.key} CPU sustained >85%"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.service[each.key].name
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  for_each            = local.services
  alarm_name          = "${local.name}-${each.key}-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  treat_missing_data  = "notBreaching"
  alarm_description   = "ECS service ${each.key} memory sustained >85%"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.service[each.key].name
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_running_count_low" {
  for_each            = local.services
  alarm_name          = "${local.name}-${each.key}-running-count-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 60
  statistic           = "Minimum"
  threshold           = var.service_min_count
  treat_missing_data  = "breaching"
  alarm_description   = "ECS service ${each.key} has fewer than ${var.service_min_count} running tasks"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.service[each.key].name
  }
}

# ---- DLQ visibility ----
# Filter the orchestrator log group for "dlq publish" events emitted by
# DLQProducer; surface them as a CloudWatch metric and alarm on any presence.
resource "aws_cloudwatch_log_metric_filter" "orchestrator_dlq" {
  name           = "${local.name}-orchestrator-dlq"
  log_group_name = aws_cloudwatch_log_group.service["orchestrator"].name
  pattern        = "\"dlq publish\""

  metric_transformation {
    name          = "OrchestratorDLQPublishes"
    namespace     = "DHP/Orchestrator"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "orchestrator_dlq" {
  alarm_name          = "${local.name}-orchestrator-dlq"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "OrchestratorDLQPublishes"
  namespace           = "DHP/Orchestrator"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Orchestrator published a job to the DLQ topic — manual triage required"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}
