output "public_url" {
  description = "The HTTPS URL to use — CloudFront in front of the ALB. This is what goes in Google OAuth."
  value       = "https://${aws_cloudfront_distribution.cal_ai.domain_name}"
}

output "cloudfront_domain" {
  description = "CloudFront's *.cloudfront.net domain (HTTPS)."
  value       = aws_cloudfront_distribution.cal_ai.domain_name
}

output "alb_dns_name" {
  description = "Direct ALB DNS (HTTP only). Internal reference; use public_url instead."
  value       = aws_lb.cal_ai.dns_name
}

output "ecr_repository_url" {
  description = "Docker image push target."
  value       = aws_ecr_repository.cal_ai.repository_url
}

output "rds_endpoint" {
  description = "RDS endpoint (host:port). Use for local alembic migrations."
  value       = "${aws_db_instance.cal_ai.address}:${aws_db_instance.cal_ai.port}"
}

output "database_url_secret_arn" {
  description = "Fetch with: aws secretsmanager get-secret-value --secret-id <arn>"
  value       = aws_secretsmanager_secret.database_url.arn
}

output "google_redirect_uri" {
  description = "Add THIS to your Google OAuth client's authorized redirect URIs."
  value       = "https://${aws_cloudfront_distribution.cal_ai.domain_name}/auth/google/callback"
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.cal_ai.name
}

output "ecs_service_name" {
  value = aws_ecs_service.cal_ai.name
}
