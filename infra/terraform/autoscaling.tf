# ECS service auto-scaling (Application Auto Scaling).
#
# Each API service registers a scalable target on its ECS service `desiredCount`
# and is driven by two target-tracking policies:
#   1. Average task CPU utilization
#   2. ALB request count per target (load-shed before saturation)
#
# Orchestrator is intentionally excluded — its concurrency is bounded by the
# Kafka consumer group and adding more replicas just rebalances partitions.

resource "aws_appautoscaling_target" "service" {
  for_each           = local.services
  max_capacity       = var.service_max_count
  min_capacity       = var.service_min_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.service[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "service_cpu" {
  for_each           = local.services
  name               = "${local.name}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.service[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.service[each.key].scalable_dimension
  service_namespace  = aws_appautoscaling_target.service[each.key].service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = var.autoscale_target_cpu
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_policy" "service_alb_rcpt" {
  for_each           = local.services
  name               = "${local.name}-${each.key}-alb-rcpt"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.service[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.service[each.key].scalable_dimension
  service_namespace  = aws_appautoscaling_target.service[each.key].service_namespace

  target_tracking_scaling_policy_configuration {
    # Target 200 requests/min per task; tune via terraform var if traffic changes shape.
    target_value       = 200
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      # Format: app/<lb-name>/<lb-id>/targetgroup/<tg-name>/<tg-id>
      resource_label = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.service[each.key].arn_suffix}"
    }
  }
}
