# src/handler.py

import json
import os
import sys

# Add project root to Python path
# WHY: When Lambda runs this file, it needs to find
# src.agents and src.tools modules correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.incident_agent import IncidentAgent

def lambda_handler(event, context):
    """
    AWS Lambda entry point.
    
    AWS calls this function automatically when SNS triggers Lambda.
    
    Parameters:
    -----------
    event: dict
        The JSON payload from SNS. Contains alarm details.
        Structure:
        {
            "Records": [
                {
                    "Sns": {
                        "Message": "{...alarm details as JSON string...}",
                        "Subject": "ALARM: production-high-cpu"
                    }
                }
            ]
        }
    
    context: LambdaContext object
        Contains runtime info — we do not use this but
        must accept it because AWS always sends it.
        Useful properties if needed:
        - context.function_name
        - context.memory_limit_in_mb
        - context.get_remaining_time_in_millis()
    
    Returns:
    --------
    dict with statusCode and body
    AWS expects this format for Lambda responses.
    
    WHY THIS STRUCTURE:
    Lambda handler must be a simple, clean entry point.
    All complex logic lives in IncidentAgent.
    Handler only does 3 things:
    1. Parse the incoming event
    2. Call the agent
    3. Return success/failure response
    """
    
    print(f"Lambda handler invoked")
    print(f"Event received: {json.dumps(event, default=str)}")
    
    try:
        # ─────────────────────────────────────────
        # STEP 1: Parse SNS Event
        # ─────────────────────────────────────────
        # WHY THIS PARSING:
        # CloudWatch → SNS → Lambda wraps the alarm
        # details inside Records[0]['Sns']['Message']
        # That Message is a JSON STRING inside JSON
        # So we need to parse it twice — json.loads twice
        
        # Get the SNS record
        # Records is a list — SNS always sends one record at a time
        sns_record = event['Records'][0]['Sns']
        
        # The actual alarm details are in Message field
        # But Message is a STRING containing JSON — parse it
        message_str = sns_record.get('Message', '{}')
        alarm_details = json.loads(message_str)
        
        print(f"Parsed alarm details: {json.dumps(alarm_details, default=str)}")
        
        # ─────────────────────────────────────────
        # STEP 2: Extract Alarm Information
        # ─────────────────────────────────────────
        # CloudWatch alarm SNS message structure:
        # {
        #   "AlarmName": "production-high-cpu",
        #   "NewStateValue": "ALARM",
        #   "NewStateReason": "Threshold crossed...",
        #   "Trigger": {
        #     "MetricName": "CPUUtilization",
        #     "Namespace": "AWS/EC2",
        #     "Dimensions": [...]
        #   }
        # }
        
        alarm_name = alarm_details.get('AlarmName', 'Unknown Alarm')
        alarm_state = alarm_details.get('NewStateValue', 'UNKNOWN')
        trigger = alarm_details.get('Trigger', {})
        namespace = trigger.get('Namespace', '')
        metric_name = trigger.get('MetricName', '')
        
        print(f"Alarm Name: {alarm_name}")
        print(f"Alarm State: {alarm_state}")
        print(f"Metric: {namespace}/{metric_name}")
        
        # ─────────────────────────────────────────
        # STEP 3: Only Process ALARM State
        # ─────────────────────────────────────────
        # WHY THIS CHECK:
        # CloudWatch sends SNS notification for EVERY
        # state change — ALARM, OK, INSUFFICIENT_DATA
        # We only want to investigate when alarm FIRES
        # not when it recovers to OK
        # Without this check we would spam Slack with
        # "incident resolved" messages triggering new investigations
        
        if alarm_state != 'ALARM':
            print(f"Alarm state is {alarm_state} — not an active alarm, skipping")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Skipped — alarm state is {alarm_state}',
                    'alarm_name': alarm_name
                })
            }
        
        # ─────────────────────────────────────────
        # STEP 4: Extract Log Group from Dimensions
        # ─────────────────────────────────────────
        # Dimensions identify WHICH specific resource triggered
        # Example for Lambda: [{"name": "FunctionName", "value": "payment-service"}]
        # Example for EC2:    [{"name": "InstanceId", "value": "i-1234567890"}]
        
        log_group = ''
        dimensions = trigger.get('Dimensions', [])
        
        for dimension in dimensions:
            # Lambda function alarms have FunctionName dimension
            if dimension.get('name') == 'FunctionName':
                function_name = dimension.get('value', '')
                log_group = f"/aws/lambda/{function_name}"
                print(f"Detected Lambda function: {function_name}")
                break
        
        # ─────────────────────────────────────────
        # STEP 5: Run Incident Investigation
        # ─────────────────────────────────────────
        
        print(f"Starting incident investigation for: {alarm_name}")
        
        agent = IncidentAgent()
        incident_report = agent.investigate(
            alarm_name=alarm_name,
            namespace=namespace,
            metric_name=metric_name,
            log_group=log_group
        )
        
        # ─────────────────────────────────────────
        # STEP 6: Return Success Response
        # ─────────────────────────────────────────
        # WHY RETURN INCIDENT REPORT:
        # Lambda logs this return value in CloudWatch
        # Useful for debugging and audit trail
        # Also visible in Lambda test results in AWS console
        
        print(f"Investigation complete: {incident_report.get('incident_id')}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Incident investigated successfully',
                'incident_id': incident_report.get('incident_id'),
                'severity': incident_report.get('severity'),
                'notification_sent': incident_report.get('notification_sent')
            })
        }
    
    except KeyError as e:
        # Missing expected field in event structure
        # This means SNS sent unexpected format
        error_msg = f"Missing field in event: {str(e)}"
        print(f"ERROR: {error_msg}")
        print(f"Full event was: {json.dumps(event, default=str)}")
        
        return {
            'statusCode': 400,
            'body': json.dumps({'error': error_msg})
        }
    
    except Exception as e:
        # Any other unexpected error
        # We return 500 but do NOT raise the exception
        # WHY: If Lambda raises exception, AWS retries it 2 more times
        # We do not want 3 duplicate Slack messages for one incident
        error_msg = f"Unexpected error: {str(e)}"
        print(f"ERROR: {error_msg}")
        
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_msg})
        }


# ─────────────────────────────────────────────────────
# LOCAL TEST BLOCK
# Simulates exactly what AWS SNS sends to Lambda
# This is the real SNS event format — not fake data
# ─────────────────────────────────────────────────────
if __name__ == "__main__":
    
    # This is the EXACT format CloudWatch alarm sends via SNS
    # When you test on AWS, this is what the real event looks like
    # We simulate it here for local testing
    
    simulated_sns_event = {
        "Records": [
            {
                "Sns": {
                    "Subject": "ALARM: payment-service-high-errors",
                    
                    # Message is a JSON string inside JSON
                    # This is how AWS SNS actually sends it
                    "Message": json.dumps({
                        "AlarmName": "payment-service-high-errors",
                        "AlarmDescription": "Payment service error rate exceeded threshold",
                        "NewStateValue": "ALARM",
                        "NewStateReason": "Threshold Crossed: 15 out of last 15 datapoints were greater than the threshold (10.0). The most recent datapoints: [45.0, 52.0, 48.0].",
                        "OldStateValue": "OK",
                        "Trigger": {
                            "MetricName": "Errors",
                            "Namespace": "AWS/Lambda",
                            "Dimensions": [
                                {
                                    "name": "FunctionName",
                                    "value": "payment-service"
                                }
                            ],
                            "Period": 300,
                            "Threshold": 10.0,
                            "ComparisonOperator": "GreaterThanThreshold"
                        }
                    })
                }
            }
        ]
    }
    
    print("=" * 60)
    print("TESTING LAMBDA HANDLER LOCALLY")
    print("Simulating real AWS SNS event")
    print("=" * 60)
    
    # Simulate Lambda context object
    # In real Lambda, AWS provides this automatically
    class MockContext:
        function_name = "ai-incident-handler"
        memory_limit_in_mb = 512
        
        def get_remaining_time_in_millis(self):
            return 270000  # 4.5 minutes remaining
    
    result = lambda_handler(simulated_sns_event, MockContext())
    
    print("\n" + "=" * 60)
    print("LAMBDA RESPONSE:")
    print("=" * 60)
    print(json.dumps(result, indent=2))