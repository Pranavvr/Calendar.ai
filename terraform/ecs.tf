resource "aws_ecs_cluster" "cal_ai" {
  name = "${var.project_name}-cluster"
}

resource "aws_ecs_cluster_capacity_providers" "cal_ai" {
  cluster_name       = aws_ecs_cluster.cal_ai.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

resource "aws_cloudwatch_log_group" "cal_ai" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 7 # portfolio: keep costs low
}

resource "aws_ecs_task_definition" "cal_ai" {
  family                   = "${var.project_name}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"  # 0.25 vCPU
  memory                   = "512"  # 0.5 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = var.project_name
    image     = "${aws_ecr_repository.cal_ai.repository_url}:${var.container_image_tag}"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    # Env vars pulled from Secrets Manager at container start.
    secrets = [
      { name = "DATABASE_URL",         valueFrom = aws_secretsmanager_secret.database_url.arn },
      { name = "JWT_SECRET",           valueFrom = aws_secretsmanager_secret.jwt_secret.arn },
      { name = "SESSION_SECRET",       valueFrom = aws_secretsmanager_secret.session_secret.arn },
      { name = "GOOGLE_CLIENT_ID",     valueFrom = aws_secretsmanager_secret.google_client_id.arn },
      { name = "GOOGLE_CLIENT_SECRET", valueFrom = aws_secretsmanager_secret.google_client_secret.arn },
      { name = "GOOGLE_REDIRECT_URI",  valueFrom = aws_secretsmanager_secret.google_redirect_uri.arn },
      { name = "OPENAI_API_KEY",       valueFrom = aws_secretsmanager_secret.openai_api_key.arn },
    ]

    # Plain env vars (non-secret).
    environment = [
      { name = "JWT_TTL_HOURS", value = "168" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.cal_ai.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "cal_ai" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.cal_ai.id
  task_definition = aws_ecs_task_definition.cal_ai.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_task.id]
    assign_public_ip = true # public subnets, no NAT — task needs public IP to reach Google/OpenAI
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.cal_ai.arn
    container_name   = var.project_name
    container_port   = 8000
  }

  # ALB needs to be listening before ECS attaches; explicit dep.
  depends_on = [aws_lb_listener.http]

  # Wait for tasks to be steady before considering apply complete.
  wait_for_steady_state = true

  lifecycle {
    ignore_changes = [desired_count] # allow manual scaling without terraform churn
  }
}
