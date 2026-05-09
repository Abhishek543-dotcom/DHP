locals {
  name = "${var.name_prefix}-${var.environment}"

  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # Service catalog: drives ECR repos, log groups, target groups, services, and ALB routing.
  services = {
    job-service = {
      port     = 8000
      path     = "/jobs"
      health   = "/health/ready"
      priority = 100
    }
    metadata-service = {
      port     = 8000
      path     = "/metadata"
      health   = "/health/ready"
      priority = 110
    }
    log-service = {
      port     = 8000
      path     = "/logs"
      health   = "/health/ready"
      priority = 120
    }
    storage-service = {
      port     = 8000
      path     = "/storage"
      health   = "/health/ready"
      priority = 130
    }
    lineage-service = {
      port     = 8000
      path     = "/lineage"
      health   = "/health/ready"
      priority = 150
    }
  }

  # Orchestrator and spark are launched but not behind the ALB
  background_services = ["orchestrator"]

  s3_buckets = [
    "warehouse",
    "raw",
    "scripts",
    "logs",
  ]

  ecr_repos = concat(
    keys(local.services),
    local.background_services,
    ["spark-base", "spark-history", "db-migrations"],
  )
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}
