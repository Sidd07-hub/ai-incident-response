# terraform/variables.tf

# WHY VARIABLES:
# Never hardcode values in main.tf
# Variables make the code reusable across environments
# Same Terraform code deploys to dev, staging, production
# Just change the variable values

variable "aws_region" {
  description = "AWS region where all resources will be created"
  type        = string
  default     = "us-east-1"
  
  # WHY us-east-1:
  # Most AWS services launch here first
  # Lowest latency to most AWS APIs
  # Groq API servers also in US — lower round trip time
}

variable "project_name" {
  description = "Name prefix for all resources — keeps things organized"
  type        = string
  default     = "ai-incident-response"
  
  # WHY PREFIX:
  # When you have 100 AWS resources, you need to identify
  # which ones belong to this project
  # All our resources will be named: ai-incident-response-*
}

variable "groq_api_key" {
  description = "Groq API key for LLM access"
  type        = string
  sensitive   = true
  # sensitive = true means Terraform will never print
  # this value in logs or terminal output
  # CRITICAL for security
}

variable "slack_webhook_url" {
  description = "Slack incoming webhook URL for notifications"
  type        = string
  sensitive   = true
  # Same as above — never printed in logs
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
  
  # WHY 300 (5 minutes):
  # Groq AI call takes 10-30 seconds
  # CloudWatch log fetching takes 5-10 seconds
  # Total pipeline needs ~60 seconds
  # We set 300 as safety buffer
  # Lambda max is 900 seconds (15 minutes)
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
  
  # WHY 512MB:
  # Our code is not memory intensive
  # 128MB default is too low for Python + boto3 + groq libraries
  # 512MB gives comfortable headroom
  # More memory also = more CPU for Lambda
}

variable "cloudwatch_alarm_threshold" {
  description = "Number of Lambda errors before alarm fires"
  type        = number
  default     = 5
  
  # WHY 5:
  # 1-2 errors could be normal transient failures
  # 5 errors in 5 minutes = real problem worth investigating
  # Adjust based on your application's normal error rate
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
  
  # Values: dev, staging, production
  # Used in resource names and tags
  # Helps identify which environment has an incident
}