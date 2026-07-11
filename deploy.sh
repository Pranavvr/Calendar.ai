#!/usr/bin/env bash
# Deploy cal-ai to AWS (ECR + RDS + ECS Fargate + ALB via Terraform).
#
# Prerequisites:
#   - AWS CLI authenticated with profile set in TF_VAR_aws_profile (default: cal-ai)
#   - Docker running
#   - .env at project root with GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY
#   - .venv with alembic installed (for the migration step)
#
# Usage: ./deploy.sh
#
# Cost: ~$28-43/mo while running. Use ./destroy.sh to tear down.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
AWS_PROFILE="${TF_VAR_aws_profile:-cal-ai}"
AWS_REGION="${TF_VAR_region:-us-east-1}"

# --- Load secrets from .env ---
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "ERROR: .env not found at $PROJECT_ROOT/.env"
    exit 1
fi

export TF_VAR_google_client_id=$(grep '^GOOGLE_CLIENT_ID=' "$PROJECT_ROOT/.env" | cut -d= -f2-)
export TF_VAR_google_client_secret=$(grep '^GOOGLE_CLIENT_SECRET=' "$PROJECT_ROOT/.env" | cut -d= -f2-)
export TF_VAR_openai_api_key=$(grep '^OPENAI_API_KEY=' "$PROJECT_ROOT/.env" | cut -d= -f2-)

for var in TF_VAR_google_client_id TF_VAR_google_client_secret TF_VAR_openai_api_key; do
    if [ -z "${!var:-}" ]; then
        echo "ERROR: $var is empty. Check .env for GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY."
        exit 1
    fi
done

# --- Step 1: Create ECR repository so we can push before ECS pulls ---
echo ""
echo "=== [1/5] Creating ECR repository ==="
cd "$TERRAFORM_DIR"
terraform apply -auto-approve \
    -target=aws_ecr_repository.cal_ai \
    -target=aws_ecr_lifecycle_policy.cal_ai

# --- Step 2: Build image, tag with ECR URI, push ---
echo ""
echo "=== [2/5] Building and pushing Docker image to ECR ==="
ECR_URL=$(terraform output -raw ecr_repository_url)

# Login to ECR with a short-lived token
aws --profile "$AWS_PROFILE" ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$ECR_URL"

# --platform linux/amd64: Fargate runs x86 by default. Without this flag on
# Apple Silicon, docker builds an ARM image that Fargate can't run.
cd "$PROJECT_ROOT"
docker build --platform linux/amd64 -t cal-ai:latest .
docker tag cal-ai:latest "$ECR_URL:latest"
docker push "$ECR_URL:latest"

# --- Step 3: Full terraform apply ---
echo ""
echo "=== [3/5] Full terraform apply (RDS creation takes ~5-10 min) ==="
cd "$TERRAFORM_DIR"
terraform apply -auto-approve

# --- Step 4: Run alembic migration against the freshly-created RDS ---
echo ""
echo "=== [4/5] Running alembic migration against RDS ==="
DB_URL_SECRET_ARN=$(terraform output -raw database_url_secret_arn)
DATABASE_URL=$(aws --profile "$AWS_PROFILE" secretsmanager get-secret-value \
    --secret-id "$DB_URL_SECRET_ARN" \
    --query SecretString --output text)

cd "$PROJECT_ROOT"
DATABASE_URL="$DATABASE_URL" .venv/bin/alembic upgrade head

# --- Step 5: Print URLs + reminder ---
cd "$TERRAFORM_DIR"
ALB_DNS=$(terraform output -raw alb_dns_name)
REDIRECT_URI=$(terraform output -raw google_redirect_uri)

echo ""
echo "==========================================================="
echo " Deploy complete"
echo "==========================================================="
echo ""
echo "ALB URL:  http://$ALB_DNS"
echo ""
echo "MANUAL STEP:"
echo "  Add this redirect URI to your Google OAuth client:"
echo "  https://console.cloud.google.com  ->  APIs & Services  ->  Credentials  ->  cal-ai-web"
echo ""
echo "  Redirect URI to add:"
echo "    $REDIRECT_URI"
echo ""
echo "Then test:"
echo "  1. Browser  ->  http://$ALB_DNS/health         (should return {\"status\":\"ok\"})"
echo "  2. Browser  ->  http://$ALB_DNS/auth/google/login   (OAuth flow)"
echo "  3. Browser  ->  http://$ALB_DNS/me              (returns your profile as JSON)"
echo "  4. /docs    ->  http://$ALB_DNS/docs           (Swagger UI — try POST /schedule)"
echo ""
