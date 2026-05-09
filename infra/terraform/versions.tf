terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Configure the S3 backend by copying backend.tf.example -> backend.tf and
  # filling in your bucket / table / region. Kept out of source control to
  # avoid baking org-specific values into the repo.
  # backend "s3" { ... }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "DHP"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
