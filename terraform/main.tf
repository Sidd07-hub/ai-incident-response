# terraform/main.tf

# ─────────────────────────────────────────────────────
# PROVIDER CONFIGURATION
# ─────────────────────────────────────────────────────
# WHY PROVIDER BLOCK:
# Tells Terraform WHICH cloud to use and WHERE
# Without this, Terraform does not know if you want
# AWS, Azure, GCP, or something else
# version constraint ensures everyone uses same version

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
      # ~> 5.0 means: use 5.x but not 6.x
      # Prevents breaking changes from major version upgrades
    }
  }
}

provider "aws" {
  region = var.aws_region
  # Credentials come from AWS CLI config we set up earlier
  # Never put access keys here — that is a security risk
}

# ─────────────────────────────────────────────────────
# RESOURCE 1: IAM ROLE
# ─────────────────────────────────────────────────────
# The identity that Lambda assumes when it runs
# Think of it as Lambda's passport

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

  # assume_role_policy = who is allowed to USE this role
  # Only Lambda service can assume this role
  # Not EC2, not a human user — only Lambda
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# ─────────────────────────────────────────────────────
# RESOURCE 2: IAM POLICY
# ─────────────────────────────────────────────────────
# The rulebook — what Lambda is allowed to DO

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      
      # Permission 1: Write logs to CloudWatch
      # WHY: Lambda must log its own execution
      # Without this, you cannot debug Lambda errors
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },

      # Permission 2: Read CloudWatch logs for analysis
      # WHY: Our agent reads logs from monitored services
      {
        Effect = "Allow"
        Action = [
          "logs:FilterLogEvents",
          "logs:GetLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },

      # Permission 3: Read CloudWatch metrics
      # WHY: Agent fetches CPU, error rate, memory metrics
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:ListMetrics"
        ]
        Resource = "*"
      },

      # Permission 4: Write to S3
      # WHY: Store incident reports for audit trail
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.incident_reports.arn,
          "${aws_s3_bucket.incident_reports.arn}/*"
        ]
      }
    ]
  })
}

# ─────────────────────────────────────────────────────
# RESOURCE 3: S3 BUCKET
# ─────────────────────────────────────────────────────
# Stores all incident reports as JSON files

resource "aws_s3_bucket" "incident_reports" {
  # random suffix prevents name conflicts
  # S3 bucket names must be globally unique across ALL AWS accounts
  bucket = "${var.project_name}-reports-${var.environment}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    Purpose     = "incident-report-storage"
  }
}

# Block all public access to bucket
# WHY: Incident reports contain sensitive system information
# Nobody outside your AWS account should ever see these
resource "aws_s3_bucket_public_access_block" "incident_reports" {
  bucket = aws_s3_bucket.incident_reports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ─────────────────────────────────────────────────────
# RESOURCE 4: SNS TOPIC
# ─────────────────────────────────────────────────────
# The messaging channel between CloudWatch and Lambda

resource "aws_sns_topic" "incidents" {
  name = "${var.project_name}-incidents"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# ─────────────────────────────────────────────────────
# RESOURCE 5: LAMBDA FUNCTION
# ─────────────────────────────────────────────────────
# Our Python agent running on AWS serverless

resource "aws_lambda_function" "incident_handler" {
  filename      = "../lambda.zip"
  function_name = "${var.project_name}-handler"
  role          = aws_iam_role.lambda_role.arn
  
  # handler = filename.function_name
  # src/handler.py → lambda_handler function
  handler = "src.handler.lambda_handler"
  runtime = "python3.12"

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory

  # source_code_hash detects when code changes
  # If hash changes, Terraform updates Lambda automatically
  source_code_hash = filebase64sha256("../lambda.zip")

  # Environment variables — accessible via os.getenv() in Python
  # WHY NOT HARDCODE: Security. These are secrets.
  # Lambda encrypts environment variables at rest with KMS
  environment {
    variables = {
      GROQ_API_KEY      = var.groq_api_key
      SLACK_WEBHOOK_URL = var.slack_webhook_url
      S3_BUCKET_NAME    = aws_s3_bucket.incident_reports.bucket
      ENVIRONMENT       = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# ─────────────────────────────────────────────────────
# RESOURCE 6: LAMBDA PERMISSION
# ─────────────────────────────────────────────────────
# Allows SNS to invoke our Lambda function
# Without this SNS gets Access Denied

resource "aws_lambda_permission" "sns_invoke" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.incident_handler.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.incidents.arn
}

# ─────────────────────────────────────────────────────
# RESOURCE 7: SNS SUBSCRIPTION
# ─────────────────────────────────────────────────────
# Links SNS Topic to Lambda
# When message arrives on topic → Lambda is invoked

resource "aws_sns_topic_subscription" "lambda" {
  topic_arn = aws_sns_topic.incidents.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.incident_handler.arn
}

# ─────────────────────────────────────────────────────
# RESOURCE 8: CLOUDWATCH METRIC ALARM
# ─────────────────────────────────────────────────────
# The trigger of the entire system
# Watches Lambda error count and fires when too high

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name        = "${var.project_name}-high-errors"
  alarm_description = "Triggers AI incident response when Lambda errors exceed threshold"

  # What to watch
  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  
  dimensions = {
    FunctionName = aws_lambda_function.incident_handler.function_name
  }

  # When to fire
  # evaluation_periods = 2 means: check 2 consecutive periods
  # Both must breach threshold before alarm fires
  # WHY 2 PERIODS: Prevents false alarms from single spike
  evaluation_periods = 2
  period             = 300    # 5 minutes per period
  statistic          = "Sum"  # Total errors in the period
  threshold          = var.cloudwatch_alarm_threshold
  comparison_operator = "GreaterThanThreshold"

  # What to do when alarm fires
  alarm_actions = [aws_sns_topic.incidents.arn]

  # What to do when alarm recovers to OK
  # We notify Slack that incident is resolved
  ok_actions = [aws_sns_topic.incidents.arn]

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}