resource "aws_lb" "cal_ai" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "cal_ai" {
  name        = "${var.project_name}-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip" # Fargate tasks are addressed by IP
  vpc_id      = data.aws_vpc.default.id

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  # Give the task time to start up (langchain imports are slow ~30s).
  deregistration_delay = 30
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.cal_ai.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.cal_ai.arn
  }
}
