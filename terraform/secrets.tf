# App-level secrets stored in Secrets Manager.
# The ECS task's execution role pulls these at container start and injects as env vars.

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "random_password" "session_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name = "${var.project_name}/jwt-secret"
  # Portfolio project: no auto-rotation; short recovery window so terraform destroy is fast.
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}

resource "aws_secretsmanager_secret" "session_secret" {
  name                    = "${var.project_name}/session-secret"
  recovery_window_in_days = 0
}

# Key for encrypting stored Google refresh tokens.
#
# Deliberately separate from jwt_secret: rotating session signing should not
# invalidate every user's stored calendar authorization, and vice versa.
#
# Fernet requires exactly 32 bytes, url-safe base64 encoded. random_password
# with special=false yields 32 ASCII bytes; base64encode produces standard
# base64, so + and / are translated to the url-safe alphabet.
resource "random_password" "token_encryption_key" {
  length  = 32
  special = false
}

locals {
  token_encryption_key = replace(
    replace(base64encode(random_password.token_encryption_key.result), "+", "-"),
    "/", "_"
  )
}

resource "aws_secretsmanager_secret" "token_encryption_key" {
  name                    = "${var.project_name}/token-encryption-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "token_encryption_key" {
  secret_id     = aws_secretsmanager_secret.token_encryption_key.id
  secret_string = local.token_encryption_key
}

resource "aws_secretsmanager_secret_version" "session_secret" {
  secret_id     = aws_secretsmanager_secret.session_secret.id
  secret_string = random_password.session_secret.result
}

resource "aws_secretsmanager_secret" "google_client_id" {
  name                    = "${var.project_name}/google-client-id"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "google_client_id" {
  secret_id     = aws_secretsmanager_secret.google_client_id.id
  secret_string = var.google_client_id
}

resource "aws_secretsmanager_secret" "google_client_secret" {
  name                    = "${var.project_name}/google-client-secret"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "google_client_secret" {
  secret_id     = aws_secretsmanager_secret.google_client_secret.id
  secret_string = var.google_client_secret
}

resource "aws_secretsmanager_secret" "openai_api_key" {
  name                    = "${var.project_name}/openai-api-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}

# DATABASE_URL is built from RDS's Secrets Manager master password + endpoint.
# We store the assembled URL as its own secret so the ECS task can pull it as one env var.
data "aws_secretsmanager_secret_version" "rds_master" {
  secret_id = aws_db_instance.cal_ai.master_user_secret[0].secret_arn
}

locals {
  rds_password = jsondecode(data.aws_secretsmanager_secret_version.rds_master.secret_string)["password"]
  database_url = "postgresql+asyncpg://${aws_db_instance.cal_ai.username}:${local.rds_password}@${aws_db_instance.cal_ai.address}:${aws_db_instance.cal_ai.port}/${aws_db_instance.cal_ai.db_name}"
}

resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${var.project_name}/database-url"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = local.database_url
}

# GOOGLE_REDIRECT_URI uses the CloudFront domain (HTTPS), because Google requires
# HTTPS on redirect URIs when sensitive scopes (Calendar) are involved.
resource "aws_secretsmanager_secret" "google_redirect_uri" {
  name                    = "${var.project_name}/google-redirect-uri"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "google_redirect_uri" {
  secret_id     = aws_secretsmanager_secret.google_redirect_uri.id
  secret_string = "https://${aws_cloudfront_distribution.cal_ai.domain_name}/auth/google/callback"
}
