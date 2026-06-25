# terraform/outputs.tf

# WHY OUTPUTS:
# After terraform apply, these values print in terminal
# Useful for copying Lambda ARN, S3 bucket name etc
# Also used by GitHub Actions to know where to deploy

output "lambda_function_name" {
  description = "Name of the deployed Lambda function"
  value       = aws_lambda_function.incident_handler.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.incident_handler.arn
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for incidents"
  value       = aws_sns_topic.incidents.arn
}

output "s3_bucket_name" {
  description = "S3 bucket storing incident reports"
  value       = aws_s3_bucket.incident_reports.bucket
}

output "cloudwatch_alarm_name" {
  description = "Name of the CloudWatch alarm"
  value       = aws_cloudwatch_metric_alarm.lambda_errors.alarm_name
}

output "deployment_summary" {
  description = "Quick summary of what was deployed"
  value = <<-EOT
    ✅ DEPLOYMENT COMPLETE
    Lambda Function : ${aws_lambda_function.incident_handler.function_name}
    SNS Topic       : ${aws_sns_topic.incidents.name}
    S3 Bucket       : ${aws_s3_bucket.incident_reports.bucket}
    CloudWatch Alarm: ${aws_cloudwatch_metric_alarm.lambda_errors.alarm_name}
    Region          : ${var.aws_region}
  EOT
}

output "ec2_public_ip" {
  description = "Public IP of EC2 instance"
  value       = aws_instance.flask_app.public_ip
}

output "ec2_instance_id" {
  description = "EC2 Instance ID"
  value       = aws_instance.flask_app.id
}

output "flask_app_url" {
  description = "Flask app URL"
  value       = "http://${aws_instance.flask_app.public_ip}:5000"
}