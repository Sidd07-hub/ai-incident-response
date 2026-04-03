# src/tools/cloudwatch_reader.py

import boto3
from datetime import datetime, timedelta, timezone

class CloudWatchReader:
    
    def __init__(self):
        
        self.logs_client = boto3.client('logs')
        
       
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
        
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)
        
        
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        print(f"Reading logs from: {log_group_name}")
        print(f"Time range: last {minutes} minutes")
        
        try:
            
            response = self.logs_client.filter_log_events(
                logGroupName=log_group_name,
                startTime=start_ms,
                endTime=end_ms,
                limit=100  
            )
            
            
            logs = []
            for event in response.get('events', []):
                logs.append(event['message'])
            
            print(f"Found {len(logs)} log lines")
            return logs
            
        except self.logs_client.exceptions.ResourceNotFoundException:
            
            print(f"Log group {log_group_name} not found")
            return []
            
        except Exception as e:
            
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
        
       
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        try:
            response = self.metrics_client.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=period,        
                Statistics=['Average', 'Maximum', 'Minimum']
                
            )
            
          
            datapoints = sorted(
                response.get('Datapoints', []),
                key=lambda x: x['Timestamp']
            )
            
            
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



if __name__ == "__main__":
    reader = CloudWatchReader()
    
  
    logs = reader.get_recent_logs('/aws/lambda/test', minutes=30)
    print(f"Test result: {len(logs)} logs fetched")