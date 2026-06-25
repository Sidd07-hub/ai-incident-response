# terraform/ec2.tf

# ─────────────────────────────────────────────────────
# FETCH DEFAULT VPC AUTOMATICALLY
# WHY: No need to hardcode VPC ID
# Terraform finds it automatically from your AWS account
# ─────────────────────────────────────────────────────
data "aws_vpc" "default" {
  default = true
}

# Fetch default subnets automatically
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ─────────────────────────────────────────────────────
# FETCH LATEST AMAZON LINUX 2 AMI AUTOMATICALLY
# WHY: AMI IDs change by region and over time
# This always gets the latest correct one for us-east-1
# ─────────────────────────────────────────────────────
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# ─────────────────────────────────────────────────────
# SECURITY GROUP
# Controls what traffic can reach our EC2
# WHY THESE RULES:
# Port 22  = SSH access (we connect to manage the server)
# Port 5000 = Flask app runs on this port
# Port 80  = HTTP access
# ─────────────────────────────────────────────────────
resource "aws_security_group" "flask_app" {
  name        = "${var.project_name}-flask-sg"
  description = "Security group for Flask app on EC2"
  vpc_id      = data.aws_vpc.default.id

  # Allow SSH from anywhere
  # WHY: We need to connect to EC2 to manage it
  # In production: restrict to your IP only
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow Flask app traffic
  ingress {
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow HTTP traffic
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow all outbound traffic
  # WHY: EC2 needs to reach internet to install packages
  # and send logs to CloudWatch
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# ─────────────────────────────────────────────────────
# IAM ROLE FOR EC2
# WHY: EC2 needs permission to send logs to CloudWatch
# Without this, CloudWatch agent cannot push metrics
# ─────────────────────────────────────────────────────
resource "aws_iam_role" "ec2_role" {
  name = "${var.project_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Attach CloudWatch agent policy to EC2 role
# WHY: This is AWS managed policy that gives
# exactly the permissions CloudWatch agent needs
resource "aws_iam_role_policy_attachment" "ec2_cloudwatch" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Attach SSM policy — allows us to run commands on EC2
# without needing SSH
resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Instance profile — attaches IAM role to EC2
# WHY: EC2 cannot use IAM role directly
# It needs an instance profile as a wrapper
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# ─────────────────────────────────────────────────────
# EC2 INSTANCE
# t2.micro = FREE TIER (750 hours/month free)
# ─────────────────────────────────────────────────────
resource "aws_instance" "flask_app" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t2.micro"
  key_name               = "ai-incident-key"
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.flask_app.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  # user_data runs automatically when EC2 starts
  # This script installs everything we need
  # WHY USER DATA:
  # We do not want to manually SSH and install things
  # Everything is automated — true DevOps approach
  user_data = base64encode(templatefile("${path.module}/../scripts/setup_ec2.sh", {
    project_name = var.project_name
    aws_region   = var.aws_region
  }))

  tags = {
    Name        = "${var.project_name}-flask-app"
    Project     = var.project_name
    Environment = var.environment
  }
}

# ─────────────────────────────────────────────────────
# CLOUDWATCH ALARMS FOR EC2
# Three real alarms watching real metrics
# ─────────────────────────────────────────────────────

# Alarm 1: High CPU
resource "aws_cloudwatch_metric_alarm" "ec2_high_cpu" {
  alarm_name          = "${var.project_name}-ec2-high-cpu"
  alarm_description   = "EC2 CPU utilization is too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 70
  alarm_actions       = [aws_sns_topic.incidents.arn]
  ok_actions          = [aws_sns_topic.incidents.arn]

  dimensions = {
    InstanceId = aws_instance.flask_app.id
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Alarm 2: High Memory
# WHY CUSTOM METRIC:
# AWS does not collect memory metrics by default
# CloudWatch agent on EC2 sends this custom metric
resource "aws_cloudwatch_metric_alarm" "ec2_high_memory" {
  alarm_name          = "${var.project_name}-ec2-high-memory"
  alarm_description   = "EC2 memory utilization is too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "mem_used_percent"
  namespace           = "CWAgent"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_actions       = [aws_sns_topic.incidents.arn]
  ok_actions          = [aws_sns_topic.incidents.arn]

  dimensions = {
    InstanceId = aws_instance.flask_app.id
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Alarm 3: Application Error Rate
# WHY CUSTOM METRIC:
# Flask app sends error count to CloudWatch
# This alarm fires when too many 500 errors occur
resource "aws_cloudwatch_metric_alarm" "app_error_rate" {
  alarm_name          = "${var.project_name}-app-high-errors"
  alarm_description   = "Flask application error rate is too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ErrorCount"
  namespace           = "FlaskApp"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_actions       = [aws_sns_topic.incidents.arn]
  ok_actions          = [aws_sns_topic.incidents.arn]

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# ─────────────────────────────────────────────────────
# SSM PARAMETER — Store EC2 Instance ID
# WHY: Lambda needs to know EC2 instance ID
# to execute auto-remediation (restart service)
# Storing in SSM Parameter Store is cleaner than
# hardcoding or passing as environment variable
# ─────────────────────────────────────────────────────
resource "aws_ssm_parameter" "ec2_instance_id" {
  name  = "/${var.project_name}/ec2-instance-id"
  type  = "String"
  value = aws_instance.flask_app.id

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}