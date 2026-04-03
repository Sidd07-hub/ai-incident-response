# src/tools/cloudwatch_reader.py

import boto3
from datetime import datetime, timedelta, timezone

# WHY THIS CLASS:
# We wrap all CloudWatch logic in one class.
# If AWS changes their API tomorrow, we only fix ONE file.
# The agent doesn't care HOW we get logs, just that we do.

class CloudWatchReader:
    
    def __init__(self):
        # boto3.client creates a connection to AWS CloudWatch
        # 'logs' means we are connecting to CloudWatch Logs specifically
        # credentials come automatically from AWS CLI config we set up earlier
        self.logs_client = boto3.client('logs')
        
        # 'cloudwatch' (without 'logs') is for metrics like CPU, memory
        self.metrics_client = boto3.client('cloudwatch')
    
    def get_recent_logs(self, log_group_name: str, minutes: int = 30) -> list:
        """
        Fetches log lines from the last X minutes.
        
        log_group_name: The CloudWatch log group to read from
                        Example: '/aws/lambda/my-function'
        minutes: How far back to look. Default 30 minutes.
        
        WHY 30 MINUTES:
        Most incidents show symptoms 10-20 minutes before the alarm fires.
        30 minutes captures the full picture of what went wrong.
        """
        
        # Calculate time range
        # We need milliseconds for CloudWatch API (multiply by 1000)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)
        
        # Convert to milliseconds timestamp (CloudWatch requirement)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        print(f"Reading logs from: {log_group_name}")
        print(f"Time range: last {minutes} minutes")
        
        try:
            # filter_log_events is the AWS API call to fetch logs
            # filterPattern='' means get ALL logs, no filtering
            response = self.logs_client.filter_log_events(
                logGroupName=log_group_name,
                startTime=start_ms,
                endTime=end_ms,
                limit=100  # Max 100 log lines at once
                           # WHY 100: Sending 10000 lines to AI costs more tokens
                           # 100 recent lines capture the incident clearly
            )
            
            # Extract just the message text from each log event
            # Each event has: timestamp, message, logStreamName, eventId
            # We only need the message for AI analysis
            logs = []
            for event in response.get('events', []):
                logs.append(event['message'])
            
            print(f"Found {len(logs)} log lines")
            return logs
            
        except self.logs_client.exceptions.ResourceNotFoundException:
            # This error means the log group doesn't exist
            # We return empty list instead of crashing
            # WHY: Agent should continue even if logs are missing
            print(f"Log group {log_group_name} not found")
            return []
            
        except Exception as e:
            # Catch any other error (network issue, permissions etc)
            print(f"Error reading logs: {str(e)}")
            return []
    
    def get_metric_data(self, namespace: str, metric_name: str, 
                        dimensions: list = None, period: int = 300) -> dict:
        """
        Fetches metric values for the last 1 hour.
        
        namespace: AWS service namespace
                   Example: 'AWS/EC2', 'AWS/Lambda', 'AWS/RDS'
        metric_name: Which metric to fetch
                     Example: 'CPUUtilization', 'Errors', 'Duration'
        dimensions: Filters to identify specific resource
                    Example: [{'Name': 'FunctionName', 'Value': 'my-function'}]
        period: Time interval in seconds. 300 = 5 minute intervals
        
        WHY METRICS MATTER:
        Logs tell you WHAT happened. Metrics tell you WHEN and HOW SEVERE.
        CPU chart showing spike at 14:32 + error logs at 14:32 = clear picture.
        """
        
        if dimensions is None:
            dimensions = []
        
        # Time range: last 1 hour of metric data
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        try:
            response = self.metrics_client.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=period,        # Data point every 5 minutes
                Statistics=['Average', 'Maximum', 'Minimum']
                # WHY ALL THREE:
                # Average shows overall trend
                # Maximum shows the worst point (what triggered alarm)
                # Minimum shows if there was recovery
            )
            
            # Sort data points by time (AWS returns them unordered)
            datapoints = sorted(
                response.get('Datapoints', []),
                key=lambda x: x['Timestamp']
            )
            
            # Format into clean dictionary for AI to read
            return {
                'metric_name': metric_name,
                'namespace': namespace,
                'datapoints': [
                    {
                        'time': str(dp['Timestamp']),
                        'average': round(dp.get('Average', 0), 2),
                        'maximum': round(dp.get('Maximum', 0), 2),
                        'minimum': round(dp.get('Minimum', 0), 2),
                    }
                    for dp in datapoints
                ]
            }
            
        except Exception as e:
            print(f"Error reading metrics: {str(e)}")
            return {'metric_name': metric_name, 'datapoints': [], 'error': str(e)}


# WHY THIS TEST BLOCK:
# When you run this file directly (python cloudwatch_reader.py)
# it runs this test. When imported by another file, it does not run.
# This lets you test each file independently.
if __name__ == "__main__":
    reader = CloudWatchReader()
    
    # Test with a real Lambda log group
    # Replace with a log group that exists in your AWS account
    logs = reader.get_recent_logs('/aws/lambda/test', minutes=30)
    print(f"Test result: {len(logs)} logs fetched")