# src/tools/slack_notifier.py

import os
import json
import urllib.request
import urllib.error
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class SlackNotifier:
    
    def __init__(self):
        self.webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        
        if not self.webhook_url:
            raise ValueError(
                "SLACK_WEBHOOK_URL not found. "
                "Check your .env file."
            )
        
        print("SlackNotifier initialized successfully")
    
    def send_incident_report(self, incident_report: dict) -> bool:
        """
        Sends formatted incident report to Slack.
        
        incident_report: Dictionary containing all incident details
                        Keys: incident_id, alarm_name, severity,
                              affected_service, root_cause,
                              immediate_action, prevention, confidence
        
        Returns: True if sent successfully, False if failed
        
        WHY RETURN BOOL:
        Caller needs to know if notification succeeded.
        If Slack is down, we should log the failure
        but not crash the entire incident pipeline.
        """
        
        
        severity_config = {
            'CRITICAL': {'emoji': '🔴', 'color': '#FF0000'},
            'HIGH':     {'emoji': '🟠', 'color': '#FF8C00'},
            'MEDIUM':   {'emoji': '🟡', 'color': '#FFD700'},
            'LOW':      {'emoji': '🟢', 'color': '#008000'},
        }
        
        severity = incident_report.get('severity', 'HIGH')
        config = severity_config.get(severity, severity_config['HIGH'])
        emoji = config['emoji']
        
       
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        
      
        incident_id = f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
       
        
        blocks = [
            
           
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} INCIDENT ALERT: {incident_report.get('alarm_name', 'Unknown')}",
                    "emoji": True
                }
            },
            
            
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Incident ID:*\n{incident_id}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{emoji} {severity}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Affected Service:*\n{incident_report.get('affected_service', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*AI Confidence:*\n{incident_report.get('confidence', 'MEDIUM')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time Detected:*\n{timestamp}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Analysis By:*\nGroq AI (Llama 3.3 70B)"
                    }
                ]
            },
            
         
            {"type": "divider"},
            
           
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🔍 Root Cause:*\n{incident_report.get('root_cause', 'Under investigation')}"
                }
            },
            
            
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚡ Immediate Action Required:*\n{incident_report.get('immediate_action', 'Investigate manually')}"
                }
            },
            
           
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🛡️ Prevention:*\n{incident_report.get('prevention', 'To be determined')}"
                }
            },
            
         
            {"type": "divider"},
            
            
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Acknowledge",
                            "emoji": True
                        },
                        
                        "style": "primary",
                        "value": f"acknowledge_{incident_id}"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📋 View Logs",
                            "emoji": True
                        },
                        "value": f"view_logs_{incident_id}",
                        
                        "url": "https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🚨 Escalate",
                            "emoji": True
                        },
                       
                        "style": "danger",
                        "value": f"escalate_{incident_id}"
                    }
                ]
            },
            
            
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🤖 Automated analysis by AI Incident Response System | {timestamp}"
                    }
                ]
            }
        ]
        
       
        payload = {"blocks": blocks}
        
      
        return self._send_to_slack(payload)
    
    def send_simple_message(self, message: str) -> bool:
        """
        Sends a plain text message to Slack.
        Used for system status updates, not incident reports.
        
        WHY THIS METHOD EXISTS:
        Sometimes we need to send simple messages like:
        'Incident INC-001 resolved' or 'System test successful'
        Block Kit is overkill for these simple notifications.
        """
        payload = {"text": message}
        return self._send_to_slack(payload)
    
    def _send_to_slack(self, payload: dict) -> bool:
        """
        Actual HTTP POST to Slack webhook.
        Private method — only called internally.
        
        WHY PRIVATE METHOD (underscore prefix):
        send_incident_report and send_simple_message are the
        public interface. _send_to_slack is implementation detail.
        This separation makes testing easier — mock the HTTP call,
        test the message formatting separately.
        """
        try:
           
            data = json.dumps(payload).encode('utf-8')
            
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
          
            with urllib.request.urlopen(req, timeout=10) as response:
                response_text = response.read().decode('utf-8')
                
               
                if response_text == 'ok':
                    print("✅ Slack notification sent successfully")
                    return True
                else:
                    print(f"⚠️ Unexpected Slack response: {response_text}")
                    return False
                    
        except urllib.error.HTTPError as e:
        
            print(f"❌ Slack HTTP error: {e.code} - {e.reason}")
            return False
            
        except urllib.error.URLError as e:
            
            print(f"❌ Slack URL error: {str(e)}")
            return False
            
        except Exception as e:
            print(f"❌ Unexpected error sending to Slack: {str(e)}")
            return False


# TEST BLOCK
if __name__ == "__main__":
    
    
    sample_incident = {
        "alarm_name": "production-high-cpu-alarm",
        "severity": "CRITICAL",
        "affected_service": "Java-based application on EC2",
        "root_cause": "Java heap space exhausted due to memory leak. "
                     "Connection pool exhausted causing cascade failures. "
                     "Database connections maxed out.",
        "immediate_action": "1. Scale up EC2 instance type immediately. "
                           "2. Restart Java application to recover from OOM. "
                           "3. Increase Java heap size: -Xmx4g flag.",
        "prevention": "Implement auto-scaling based on memory metrics. "
                     "Add heap dump alerts at 80% memory. "
                     "Optimize garbage collection settings.",
        "confidence": "HIGH"
    }
    
    print("=" * 50)
    print("TESTING SLACK NOTIFIER")
    print("=" * 50)
    
    notifier = SlackNotifier()
    success = notifier.send_incident_report(sample_incident)
    
    if success:
        print("\n🎉 Check your #incident-alerts Slack channel!")
        print("You should see a formatted incident report.")
    else:
        print("\n❌ Failed to send. Check your SLACK_WEBHOOK_URL in .env")