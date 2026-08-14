terraform {
  required_version = ">= 1.5"
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
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = var.project_name
      ManagedBy   = "Terraform"
      Environment = "prod"
    }
  }
}

# Use the AWS account's DEFAULT VPC. Cheaper + simpler than provisioning a new VPC.
data "aws_vpc" "default" {
  default = true
}

# Get all subnets in the default VPC (they're all public by default).
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# The my_ip data source and my_cidr local were removed with the RDS laptop
# ingress rule. They were the only consumer, and every plan made an outbound HTTP
# call to discover an address that is no longer used for anything.
