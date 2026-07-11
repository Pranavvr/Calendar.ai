variable "region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region"
}

variable "aws_profile" {
  type        = string
  default     = "cal-ai"
  description = "AWS CLI profile to use. Override with TF_VAR_aws_profile when switching accounts."
}

variable "project_name" {
  type        = string
  default     = "cal-ai"
  description = "Prefix for all resource names"
}

variable "google_client_id" {
  type        = string
  sensitive   = true
  description = "Google OAuth client ID (Web application type). Provide via TF_VAR_google_client_id env var."
}

variable "google_client_secret" {
  type        = string
  sensitive   = true
  description = "Google OAuth client secret. Provide via TF_VAR_google_client_secret env var."
}

variable "openai_api_key" {
  type        = string
  sensitive   = true
  description = "OpenAI API key for the LangGraph agent. Provide via TF_VAR_openai_api_key env var."
}

variable "container_image_tag" {
  type        = string
  default     = "latest"
  description = "Tag of the cal-ai image in ECR. Bump per deploy in a real CD pipeline."
}
