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

# tr strip trailing whitespace: .env values sometimes have trailing newlines/spaces
# and Google's OAuth rejects the client_id if it has trailing space in the URL.
export TF_VAR_google_client_id=$(grep '^GOOGLE_CLIENT_ID=' "$PROJECT_ROOT/.env" | cut -d= -f2- | tr -d '[:space:]')
export TF_VAR_google_client_secret=$(grep '^GOOGLE_CLIENT_SECRET=' "$PROJECT_ROOT/.env" | cut -d= -f2- | tr -d '[:space:]')
export TF_VAR_openai_api_key=$(grep '^OPENAI_API_KEY=' "$PROJECT_ROOT/.env" | cut -d= -f2- | tr -d '[:space:]')

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
docker tag cal-ai:latest "${ECR_URL}:latest"
docker push "${ECR_URL}:latest"

# --- Step 3: Full terraform apply ---
echo ""
echo "=== [3/5] Full terraform apply (RDS creation takes ~5-10 min) ==="
cd "$TERRAFORM_DIR"
terraform apply -auto-approve

# --- Step 4: Run alembic migration as a one-off ECS task ---
#
# Previously this ran alembic from the laptop, which required
# publicly_accessible = true on RDS — a database exposed to the internet with
# only a security group in front, permanently, despite being commented
# "temporary". The database is now private, so migrations run inside the VPC in
# the same image and task definition as the app. This is why alembic is kept in
# the runtime image.
echo ""
echo "=== [4/5] Running alembic migration as an ECS task ==="

CLUSTER=$(terraform output -raw ecs_cluster_name)
TASK_DEF=$(terraform output -raw ecs_task_definition_arn)
SUBNETS=$(terraform output -json ecs_subnet_ids | tr -d '[]" ' )
TASK_SG=$(terraform output -raw ecs_task_security_group_id)

MIGRATION_TASK_ARN=$(aws --profile "$AWS_PROFILE" ecs run-task \
    --cluster "$CLUSTER" \
    --task-definition "$TASK_DEF" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${TASK_SG}],assignPublicIp=ENABLED}" \
    --overrides '{"containerOverrides":[{"name":"'"${TF_VAR_project_name:-cal-ai}"'","command":["python","-m","alembic","upgrade","head"]}]}' \
    --query 'tasks[0].taskArn' --output text)

if [ -z "$MIGRATION_TASK_ARN" ] || [ "$MIGRATION_TASK_ARN" = "None" ]; then
    echo "ERROR: failed to start the migration task."
    exit 1
fi

echo "Migration task: $MIGRATION_TASK_ARN"
echo "Waiting for it to finish..."
aws --profile "$AWS_PROFILE" ecs wait tasks-stopped \
    --cluster "$CLUSTER" --tasks "$MIGRATION_TASK_ARN"

# A stopped task is not a successful one — check the container's exit code, or a
# failed migration would pass silently and the app would start against an
# out-of-date schema.
MIGRATION_EXIT=$(aws --profile "$AWS_PROFILE" ecs describe-tasks \
    --cluster "$CLUSTER" --tasks "$MIGRATION_TASK_ARN" \
    --query 'tasks[0].containers[0].exitCode' --output text)

if [ "$MIGRATION_EXIT" != "0" ]; then
    echo "ERROR: migration task exited with code $MIGRATION_EXIT."
    echo "Logs: aws --profile $AWS_PROFILE logs tail /ecs/${TF_VAR_project_name:-cal-ai} --since 10m"
    exit 1
fi
echo "Migration applied."

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
