variable "aws_region" {
  description = "AWS region to deploy DHP into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod). Drives sizing and HA defaults."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "name_prefix" {
  description = "Prefix applied to all resource names"
  type        = string
  default     = "dhp"
}

# ---- Networking ----
variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "az_count" {
  description = "Number of AZs (and matching public/private subnets) to spread across"
  type        = number
  default     = 2
}

# ---- RDS Postgres ----
variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_username" {
  type    = string
  default = "lakehouse"
}

variable "db_name" {
  type    = string
  default = "lakehouse"
}

variable "db_multi_az" {
  description = "Enable Multi-AZ for RDS (set true for prod)"
  type        = bool
  default     = false
}

# ---- MSK ----
variable "msk_kafka_version" {
  type    = string
  default = "3.6.0"
}

variable "msk_broker_instance_type" {
  type    = string
  default = "kafka.t3.small"
}

variable "msk_broker_count" {
  type    = number
  default = 2
}

# ---- ElastiCache Redis ----
variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

# ---- ECS / Service sizing ----
variable "service_cpu" {
  description = "Default CPU units per API service task (1 vCPU = 1024)"
  type        = number
  default     = 512
}

variable "service_memory" {
  description = "Default memory (MiB) per API service task"
  type        = number
  default     = 1024
}

variable "service_desired_count" {
  type    = number
  default = 2
}

variable "spark_task_cpu" {
  description = "CPU units for spawned Spark task (default 2 vCPU)"
  type        = number
  default     = 2048
}

variable "spark_task_memory" {
  description = "Memory (MiB) for spawned Spark task"
  type        = number
  default     = 8192
}

# ---- Image tags (set by CI on deploy) ----
variable "image_tag" {
  description = "Docker image tag to deploy across services. Override per-service via service_image_tags."
  type        = string
  default     = "latest"
}

variable "service_image_tags" {
  description = "Optional per-service tag overrides. Falls back to var.image_tag."
  type        = map(string)
  default     = {}
}

# ---- TLS / DNS ----
variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the ALB HTTPS listener. If empty, only HTTP listener is created (NOT recommended for prod)."
  type        = string
  default     = ""
}

variable "alb_allowed_cidrs" {
  description = "CIDR blocks allowed to hit the ALB. Restrict to VPN/office ranges in prod."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ---- Alerting ----
variable "alarm_emails" {
  description = "Email addresses subscribed to the alerts SNS topic. Each address must be confirmed via AWS-sent email after apply."
  type        = list(string)
  default     = []
}

# ---- ECS service auto-scaling ----
variable "service_min_count" {
  description = "Minimum ECS task count per API service when auto-scaling"
  type        = number
  default     = 2
}

variable "service_max_count" {
  description = "Maximum ECS task count per API service when auto-scaling"
  type        = number
  default     = 10
}

variable "autoscale_target_cpu" {
  description = "Target average CPU (%) for ECS service auto-scaling"
  type        = number
  default     = 60
}
