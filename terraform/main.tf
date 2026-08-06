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

# The IP of the machine running Terraform — used to allow this laptop into
# the RDS security group for the initial alembic migration.
data "http" "my_ip" {
  url = "https://checkip.amazonaws.com/"
}

locals {
  my_cidr = "${chomp(data.http.my_ip.response_body)}/32"
}
