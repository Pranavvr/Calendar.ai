# Security groups for the three layers.

# CloudFront's published origin-facing IP ranges, as an AWS-managed prefix list.
# Managed rather than hardcoded because these ranges change; AWS keeps the list
# current.
data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# ALB SG — reachable only from CloudFront.
#
# Previously this allowed 0.0.0.0/0 on port 80. CloudFront redirects viewers to
# HTTPS, but nothing forced traffic through CloudFront: the ALB's own DNS name
# was directly reachable over plain HTTP, so the session cookie could be sent in
# cleartext and the TLS termination bypassed entirely.
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Allow inbound HTTP to the ALB from CloudFront edge locations only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "HTTP from CloudFront edges only"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id]
  }

  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ECS task SG — allow inbound 8000 ONLY from the ALB SG.
resource "aws_security_group" "ecs_task" {
  name        = "${var.project_name}-ecs-task-sg"
  description = "Allow inbound app port from ALB, all egress for API calls"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "App port from ALB only"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All egress (for Google, OpenAI, RDS, Secrets Manager, ECR)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# RDS SG — allow inbound Postgres from:
#   - the ECS task SG (production access)
#   - my laptop's IP (initial migration + occasional psql from local)
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Allow Postgres from ECS tasks and from my laptop for admin"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from ECS tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_task.id]
  }

  ingress {
    description = "Postgres from my laptop (initial migration, local admin)"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [local.my_cidr]
  }

  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
