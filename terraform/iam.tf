# Two IAM roles for the ECS task:
# 1) execution role — used by ECS itself to pull image from ECR, write logs, fetch secrets
# 2) task role       — used by the container at runtime (currently no runtime AWS calls, so minimal)

# ----- Execution role -----

resource "aws_iam_role" "ecs_execution" {
  name = "${var.project_name}-ecs-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# AWS-managed policy that covers ECR pulling + CloudWatch Logs.
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Extra: grant execution role permission to read the Secrets Manager entries we've created,
# so ECS can inject them as env vars into the task container at start time.
resource "aws_iam_policy" "ecs_read_secrets" {
  name        = "${var.project_name}-ecs-read-secrets"
  description = "Allow reading the cal-ai secrets from Secrets Manager"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.jwt_secret.arn,
        aws_secretsmanager_secret.session_secret.arn,
        aws_secretsmanager_secret.google_client_id.arn,
        aws_secretsmanager_secret.google_client_secret.arn,
        aws_secretsmanager_secret.google_redirect_uri.arn,
        aws_secretsmanager_secret.openai_api_key.arn,
        aws_secretsmanager_secret.database_url.arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_read_secrets" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = aws_iam_policy.ecs_read_secrets.arn
}

# ----- Task role -----
# Empty for now; container makes no AWS SDK calls at runtime.
# When we later add S3/SES/etc., grant here.

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
