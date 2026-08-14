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

# Shared secret proving a request came from *our* CloudFront distribution.
#
# The security group restricts the ALB to CloudFront's IP ranges, but those
# ranges belong to every CloudFront distribution in the world — anyone could
# point their own distribution at this ALB's DNS name and be inside the allowed
# CIDRs. This header closes that gap.
resource "random_password" "origin_verify" {
  length  = 48
  special = false
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.cal_ai.arn
  port              = 80
  protocol          = "HTTP"

  # Deny by default. Only the rule below, which requires the shared secret,
  # forwards to the application.
  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Direct origin access is not permitted. Use the CloudFront URL."
      status_code  = "403"
    }
  }
}

resource "aws_lb_listener_rule" "from_cloudfront" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.cal_ai.arn
  }

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [random_password.origin_verify.result]
    }
  }
}
