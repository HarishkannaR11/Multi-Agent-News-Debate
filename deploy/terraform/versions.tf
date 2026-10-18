# Terraform and provider versions this configuration was written for.
terraform {
  # Any 1.x release from 1.5 on.
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Version 5 of the AWS provider (6.x renamed some attributes used here).
      version = "~> 5.0"
    }
  }
}

# The main provider: everything is created in this region, and every resource gets these tags.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "counterpoint"
      ManagedBy = "terraform"
    }
  }
}

# A second provider pinned to us-east-1: an AWS WAF web ACL for CloudFront must be created there,
# whichever region the server itself runs in. It is only used when enable_waf = true.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = "counterpoint"
      ManagedBy = "terraform"
    }
  }
}
