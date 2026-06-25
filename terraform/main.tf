# terraform/main.tf

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ─────────────────────────────────────────────────────
# RESOURCE 1: IAM ROLE FOR LAMBDA
# ─────────────────────────────────────────────────────
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

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
# RESOURCE 2: IAM POLICY FOR LAMBDA
# ─────────────────────────────────────────────────────
resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [

      # Permission 1: Write Lambda logs to CloudWatch
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
      },

      # Permission 5: SSM — read EC2 instance ID + run commands
      # WHY: Lambda reads EC2 ID from SSM Parameter Store
      # Lambda also sends SSM commands to restart Flask service
      # This is how auto-remediation works without SSH
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:PutParameter",
          "ssm:SendCommand",
          "ssm:GetCommandInvocation",
          "ssm:ListCommands",
          "ssm:ListCommandInvocations"
        ]
        Resource = "*"
      },

      # Permission 6: EC2 — describe and reboot instances
      # WHY: Auto-remediation needs to restart EC2
      # or describe instance status during investigation
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:RebootInstances"
        ]
        Resource = "*"
      }
    ]
  })
}

# ─────────────────────────────────────────────────────
# RESOURCE 3: S3 BUCKET
# ─────────────────────────────────────────────────────
resource "aws_s3_bucket" "incident_reports" {
  bucket = "${var.project_name}-reports-${var.environment}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    Purpose     = "incident-report-storage"
  }
}

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
resource "aws_lambda_function" "incident_handler" {
  filename      = "../lambda.zip"
  function_name = "${var.project_name}-handler"
  role          = aws_iam_role.lambda_role.arn
  handler       = "src.handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  source_code_hash = filebase64sha256("../lambda.zip")

  environment {
    variables = {
      OPENROUTER_API_KEY = var.openrouter_api_key
      SLACK_WEBHOOK_URL  = var.slack_webhook_url
      S3_BUCKET_NAME     = aws_s3_bucket.incident_reports.bucket
      ENVIRONMENT        = var.environment
      AWS_REGION_NAME    = var.aws_region
      PROJECT_NAME       = var.project_name
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
resource "aws_sns_topic_subscription" "lambda" {
  topic_arn = aws_sns_topic.incidents.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.incident_handler.arn
}

# ─────────────────────────────────────────────────────
# RESOURCE 8: CLOUDWATCH ALARM FOR LAMBDA
# ─────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.project_name}-high-errors"
  alarm_description   = "Triggers AI incident response when Lambda errors exceed threshold"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  evaluation_periods  = 2
  period              = 300
  statistic           = "Sum"
  threshold           = var.cloudwatch_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.incidents.arn]
  ok_actions          = [aws_sns_topic.incidents.arn]

  dimensions = {
    FunctionName = aws_lambda_function.incident_handler.function_name
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}