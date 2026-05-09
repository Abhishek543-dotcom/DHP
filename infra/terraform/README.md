# DHP Terraform — AWS Infrastructure

Provisions the AWS infrastructure for DHP on ECS Fargate.

## What gets created

| Layer | Resource |
|-------|----------|
| Network | VPC, 2x public/private subnets, IGW, NAT, route tables, 3x security groups |
| Compute | ECS Fargate cluster + capacity providers, services for 4 APIs + orchestrator, Spark task definition |
| Edge | Application Load Balancer with path-based routing (`/jobs`, `/metadata`, `/logs`, `/storage`); HTTPS when `acm_certificate_arn` provided |
| Data | RDS Postgres 16, MSK Serverless (IAM auth), ElastiCache Redis 7 |
| Storage | 4x S3 buckets (warehouse / raw / scripts / logs), versioning + SSE + public-access block |
| Registry | 6x ECR repos (one per service + spark-base) with lifecycle policy |
| Security | IAM task execution role + per-service task roles, Secrets Manager (API key, internal token, DB URL) |
| Observability | CloudWatch log groups per service, ALB 5xx + RDS CPU alarms |

## Prerequisites

- Terraform >= 1.6
- AWS credentials with admin (or fine-grained equivalent)
- (Recommended) S3 bucket + DynamoDB table for remote state — see `backend.tf.example`

## Bootstrap

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your environment values

# Optional: configure remote state
cp backend.tf.example backend.tf  # then edit

terraform init
terraform plan
terraform apply
```

First apply will fail-fast on missing ECR images. After `apply` completes the
infra exists but ECS tasks will keep restarting until you push images:

```bash
# CI does this automatically; manual bootstrap example:
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker build -t <account>.dkr.ecr.us-east-1.amazonaws.com/dhp-dev/job-service:latest \
  ../../services/job-service
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/dhp-dev/job-service:latest
# repeat for each service
```

## Environment profiles

- `environment = "dev"` — single NAT, no Multi-AZ, force-destroy buckets, 1-day backup
- `environment = "prod"` — NAT per AZ, RDS Multi-AZ, deletion protection, 7-day backup, 30-day log retention

## Cost estimate (idle, dev profile, us-east-1)

Approximate monthly:
- NAT Gateway: ~$33
- RDS db.t4g.medium: ~$50
- MSK Serverless idle: ~$25 (charged per partition-hour + traffic)
- ALB: ~$18
- ElastiCache cache.t4g.micro: ~$13
- ECS Fargate (5 tasks @ 0.5vCPU/1GB always-on): ~$45
- CloudWatch + S3 + ECR: ~$10
- **Total ~$195/mo idle**, scales with Spark job runtime + traffic

Use Multi-AZ + larger instances for prod; expect 3-4x for HA setup.

## Outputs

After apply, useful outputs:

```bash
terraform output alb_dns_name
terraform output ecr_repository_urls
terraform output spark_task_definition_arn
```

## Destroy

```bash
terraform destroy
```

Note: in `prod`, RDS deletion protection and Secrets Manager 7-day recovery
window will block destroy until manually disabled.
