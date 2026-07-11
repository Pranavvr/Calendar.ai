resource "aws_ecr_repository" "cal_ai" {
  name                 = var.project_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Retention: keep only the 10 most recent images to avoid ECR storage costs
# growing unbounded.
resource "aws_ecr_lifecycle_policy" "cal_ai" {
  repository = aws_ecr_repository.cal_ai.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}
