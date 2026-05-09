output "alb_dns_name" {
  description = "Public DNS for the ALB"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_urls" {
  description = "ECR repo URLs by service"
  value       = { for k, r in aws_ecr_repository.service : k => r.repository_url }
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_names" {
  value = concat(
    [for s in aws_ecs_service.service : s.name],
    [aws_ecs_service.orchestrator.name],
  )
}

output "rds_endpoint" {
  value     = aws_db_instance.main.address
  sensitive = true
}

output "msk_bootstrap_brokers" {
  value     = aws_msk_serverless_cluster.main.bootstrap_brokers_sasl_iam
  sensitive = true
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "s3_buckets" {
  value = { for k, b in aws_s3_bucket.lakehouse : k => b.bucket }
}

output "secrets_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "spark_task_definition_arn" {
  value = aws_ecs_task_definition.spark.arn
}

output "migrations_task_definition_arn" {
  value = aws_ecs_task_definition.db_migrations.arn
}
