# Remote state in S3, with DynamoDB for locking.
#
# State was previously a local file. Three problems with that:
#
#   1. Losing the file orphans every resource. Terraform no longer knows they
#      exist, so it cannot destroy or modify them — they have to be imported
#      one at a time or deleted by hand in the console.
#   2. There is no locking, so two concurrent applies can interleave writes and
#      corrupt state.
#   3. State contains secret values in plaintext — the RDS password, the token
#      encryption key, the origin verify header. On a laptop that is an
#      unencrypted file outside any access control.
#
# BOOTSTRAP — the bucket must exist before Terraform can use it as a backend,
# which is a chicken-and-egg. Create it once, out of band:
#
#   AWS_PROFILE=cal-ai
#   REGION=us-east-1
#   BUCKET=cal-ai-tfstate-$(aws --profile $AWS_PROFILE sts get-caller-identity \
#            --query Account --output text)
#
#   aws --profile $AWS_PROFILE s3api create-bucket \
#       --bucket "$BUCKET" --region "$REGION"
#   aws --profile $AWS_PROFILE s3api put-bucket-versioning \
#       --bucket "$BUCKET" --versioning-configuration Status=Enabled
#   aws --profile $AWS_PROFILE s3api put-bucket-encryption \
#       --bucket "$BUCKET" --server-side-encryption-configuration \
#       '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
#   aws --profile $AWS_PROFILE s3api put-public-access-block \
#       --bucket "$BUCKET" --public-access-block-configuration \
#       'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
#
#   aws --profile $AWS_PROFILE dynamodb create-table \
#       --table-name cal-ai-tflock \
#       --attribute-definitions AttributeName=LockID,AttributeType=S \
#       --key-schema AttributeName=LockID,KeyType=HASH \
#       --billing-mode PAY_PER_REQUEST --region "$REGION"
#
# Then fill in the bucket name below, uncomment, and run:
#
#   terraform init -migrate-state
#
# Versioning matters: it is the difference between a corrupted state file being
# an inconvenience and being unrecoverable.
#
# Left commented because the bucket name must be globally unique and this
# account does not exist yet. Uncommenting without the bootstrap above will fail
# `terraform init`.

# terraform {
#   backend "s3" {
#     bucket         = "cal-ai-tfstate-REPLACE_WITH_ACCOUNT_ID"
#     key            = "prod/terraform.tfstate"
#     region         = "us-east-1"
#     profile        = "cal-ai"
#     dynamodb_table = "cal-ai-tflock"
#     encrypt        = true
#   }
# }
