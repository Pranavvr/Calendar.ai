#!/usr/bin/env bash
# Tear down the entire cal-ai AWS deployment.
# Removes: ECS, RDS, ALB, Secrets Manager entries, ECR (images + repo), IAM roles, SGs, log group.
#
# Usage: ./destroy.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

# Terraform still needs the TF_VAR values defined during destroy (for variable validation).
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "ERROR: .env not found; can't populate TF_VARs for destroy validation."
    exit 1
fi

export TF_VAR_google_client_id=$(grep '^GOOGLE_CLIENT_ID=' "$PROJECT_ROOT/.env" | cut -d= -f2-)
export TF_VAR_google_client_secret=$(grep '^GOOGLE_CLIENT_SECRET=' "$PROJECT_ROOT/.env" | cut -d= -f2-)
export TF_VAR_openai_api_key=$(grep '^OPENAI_API_KEY=' "$PROJECT_ROOT/.env" | cut -d= -f2-)

echo ""
echo "==========================================================="
echo " Destroying cal-ai AWS deployment"
echo "==========================================================="
echo ""
echo "This removes:"
echo "  - ECS cluster + task + service"
echo "  - RDS instance (all user data lost)"
echo "  - ALB + target group + listener"
echo "  - All Secrets Manager entries (immediate delete, no recovery)"
echo "  - ECR repository (all pushed images gone)"
echo "  - IAM roles for the task"
echo "  - Security groups"
echo "  - CloudWatch log group"
echo ""

cd "$TERRAFORM_DIR"
terraform destroy -auto-approve

echo ""
echo "==========================================================="
echo " ✅ Destroyed"
echo "==========================================================="
echo ""
echo "Fresh deploy tomorrow:  ./deploy.sh"
echo ""
