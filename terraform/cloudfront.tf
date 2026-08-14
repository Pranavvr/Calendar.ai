# CloudFront distribution fronting the ALB.
# Purpose: give us HTTPS for free via a *.cloudfront.net domain, so Google's
# OAuth (which requires HTTPS for sensitive scopes like Calendar) accepts us.
#
# Traffic flow:
#   Browser --HTTPS--> CloudFront edge --HTTP--> ALB --HTTP--> ECS task
#
# CloudFront terminates TLS at the edge; the backend leg stays HTTP inside AWS.

resource "aws_cloudfront_distribution" "cal_ai" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "cal-ai — HTTPS fronting ALB"
  price_class     = "PriceClass_100" # US + Canada + Europe only; cheaper than global

  origin {
    domain_name = aws_lb.cal_ai.dns_name
    origin_id   = "cal-ai-alb"

    # Proves to the ALB that a request came from this distribution rather than
    # from any CloudFront distribution inside the allowed IP ranges. The ALB
    # listener returns 403 without it.
    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.origin_verify.result
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # ALB is HTTP; CloudFront speaks HTTPS to browsers
      origin_ssl_protocols   = ["TLSv1.2"]
      # Bump the origin timeout above the default 30s. Agent runs (multiple LLM
      # calls + Google Calendar API round-trips) can take 40-60s. 60s is the
      # max without a service quota increase.
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "cal-ai-alb"

    viewer_protocol_policy = "redirect-to-https"

    # AWS-managed policies:
    #   CachingDisabled — nothing gets cached at the edge (dynamic API)
    #   AllViewer       — forward all headers, cookies, query strings to origin
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    # Default *.cloudfront.net cert — free, no domain purchase needed.
    cloudfront_default_certificate = true
  }
}
