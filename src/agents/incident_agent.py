# src/agents/incident_agent.py

import json
import os
import boto3
from datetime import datetime
from dotenv import load_dotenv

# Import our three tools we already built
# This is why we built them separately — clean imports
from src.tools.cloudwatch_reader import CloudWatchReader
from src.tools.groq_analyzer import GroqAnalyzer
from src.tools.slack_notifier import SlackNotifier

load_dotenv()

class IncidentAgent:
    """
    The main AI agent that orchestrates incident response.
    
    WHY THIS CLASS EXISTS:
    Without this class, the Lambda handler would contain
    all the logic — reading logs, calling AI, posting Slack.
    That would be hundreds of lines in one function.
    
    This class separates the ORCHESTRATION logic from
    the TOOL logic. Agent decides what to do.
    Tools do the actual work.
    
    This is the Single Responsibility Principle:
    - CloudWatchReader: only reads AWS data
    - GroqAnalyzer: only calls AI
    - SlackNotifier: only posts to Slack
    - IncidentAgent: only orchestrates the above three
    
    INTERVIEW GOLD:
    "I followed SOLID principles. Each class has one job.
    This makes the code testable, maintainable, and scalable."
    """
    
    def __init__(self):
        print("Initializing Incident Agent...")
        
        # Initialize all three tools
        # If any tool fails to initialize, agent fails fast
        # Better than failing silently mid-investigation
        self.cloudwatch = CloudWatchReader()
        self.analyzer = GroqAnalyzer()
        self.notifier = SlackNotifier()
        
        # S3 client for storing incident reports
        # WHY S3: Audit trail — every incident permanently stored
        # Compliance requirement in most companies
        self.s3_client = boto3.client('s3')
        self.s3_bucket = os.getenv('S3_BUCKET_NAME', '')
        
        print("✅ Incident Agent initialized successfully")
        print(f"   - CloudWatch Reader: ready")
        print(f"   - Groq AI Analyzer: ready")
        print(f"   - Slack Notifier: ready")
    
    def investigate(self, alarm_name: str, 
                    namespace: str = '',
                    metric_name: str = '',
                    log_group: str = '') -> dict:
        """
        Main method — runs the full incident investigation.
        
        This follows the ReAct pattern:
        1. OBSERVE: Gather data (logs + metrics)
        2. REASON:  AI analyzes the data
        3. ACT:     Notify team via Slack
        4. STORE:   Save report to S3
        
        alarm_name:  Name of the CloudWatch alarm that fired
        namespace:   AWS namespace (AWS/EC2, AWS/Lambda etc)
        metric_name: Which metric triggered (CPUUtilization etc)
        log_group:   CloudWatch log group to read from
        
        Returns: Complete incident report dictionary
        """
        
        print("\n" + "="*60)
        print(f"🚨 INCIDENT INVESTIGATION STARTED")
        print(f"   Alarm: {alarm_name}")
        print(f"   Time:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        # Generate unique incident ID
        # Used to track this incident across all systems
        incident_id = f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # ─────────────────────────────────────────────
        # STEP 1: OBSERVE — Gather Evidence
        # ─────────────────────────────────────────────
        # WHY THIS STEP:
        # AI is only as good as the data you give it.
        # Garbage in = garbage out.
        # We collect BOTH logs (what happened) and 
        # metrics (how severe) for complete picture.
        
        print("\n📊 STEP 1: Gathering evidence from CloudWatch...")
        
        # Determine log group from alarm name if not provided
        # Convention: alarm name contains service name
        # Example: 'payment-service-high-cpu' -> '/aws/lambda/payment-service'
        if not log_group:
            log_group = self._extract_log_group(alarm_name)
        
        # Fetch logs — last 30 minutes
        logs = self.cloudwatch.get_recent_logs(
            log_group_name=log_group,
            minutes=30
        )
        
        # Fetch metrics if namespace and metric provided
        metrics = {}
        if namespace and metric_name:
            metrics = self.cloudwatch.get_metric_data(
                namespace=namespace,
                metric_name=metric_name
            )
        
        print(f"   ✅ Collected {len(logs)} log lines")
        print(f"   ✅ Collected metric data: {bool(metrics)}")
        
        # ─────────────────────────────────────────────
        # STEP 2: REASON — AI Analysis
        # ─────────────────────────────────────────────
        # WHY THIS STEP:
        # Raw logs are hard to read under pressure at 2 AM.
        # AI converts 100 log lines into 3 actionable sentences.
        # This is the core value of the entire project.
        
        print("\n🤖 STEP 2: AI analyzing incident...")
        
        analysis = self.analyzer.analyze_incident(
            alarm_name=alarm_name,
            logs=logs,
            metrics=metrics
        )
        
        print(f"   ✅ AI analysis complete")
        print(f"   Severity: {analysis.get('severity', 'UNKNOWN')}")
        print(f"   Confidence: {analysis.get('confidence', 'UNKNOWN')}")
        
        # ─────────────────────────────────────────────
        # STEP 3: BUILD COMPLETE INCIDENT REPORT
        # ─────────────────────────────────────────────
        # Combine alarm info + AI analysis into one report
        # This single dictionary flows through the entire system
        
        incident_report = {
            'incident_id': incident_id,
            'alarm_name': alarm_name,
            'timestamp': datetime.now().isoformat(),
            'log_group': log_group,
            'logs_analyzed': len(logs),
            'severity': analysis.get('severity', 'HIGH'),
            'affected_service': analysis.get('affected_service', 'Unknown'),
            'root_cause': analysis.get('root_cause', 'Under investigation'),
            'immediate_action': analysis.get('immediate_action', 'Investigate manually'),
            'prevention': analysis.get('prevention', 'To be determined'),
            'confidence': analysis.get('confidence', 'MEDIUM'),
            'status': 'OPEN'
        }
        
        # ─────────────────────────────────────────────
        # STEP 4: ACT — Notify Team
        # ─────────────────────────────────────────────
        # WHY NOTIFY BEFORE STORING:
        # Notification is time-critical — team needs to know NOW.
        # S3 storage can fail without affecting the notification.
        # Most important action happens first.
        
        print("\n📱 STEP 3: Notifying team via Slack...")
        
        notification_sent = self.notifier.send_incident_report(incident_report)
        incident_report['notification_sent'] = notification_sent
        
        if notification_sent:
            print("   ✅ Team notified via Slack")
        else:
            print("   ⚠️ Slack notification failed — check webhook URL")
        
        # ─────────────────────────────────────────────
        # STEP 5: STORE — Save to S3
        # ─────────────────────────────────────────────
        # WHY S3 STORAGE:
        # Audit trail for compliance
        # Post-incident analysis — find patterns across incidents
        # Input for future AI training
        
        print("\n💾 STEP 4: Storing incident report...")
        
        if self.s3_bucket:
            stored = self._store_incident(incident_report)
            incident_report['stored_in_s3'] = stored
        else:
            print("   ⚠️ S3_BUCKET_NAME not set — skipping storage")
            print("   (This is fine for local testing)")
            incident_report['stored_in_s3'] = False
        
        # ─────────────────────────────────────────────
        # STEP 6: AUTO-REMEDIATION DECISION
        # ─────────────────────────────────────────────
        # WHY THIS STEP:
        # For known incident patterns, we can auto-fix.
        # But ONLY for LOW risk actions.
        # HIGH risk actions always need human approval.
        # This is the Human-in-the-Loop (HITL) pattern.
        
        if analysis.get('severity') in ['CRITICAL', 'HIGH']:
            print("\n⚠️  STEP 5: High severity — human approval required")
            print("   Auto-remediation NOT triggered")
            print("   Engineer must click Acknowledge in Slack")
            incident_report['auto_remediated'] = False
            incident_report['remediation_note'] = 'Human approval required'
        else:
            print("\n✅ STEP 5: Low/Medium severity — safe for auto-remediation")
            incident_report['auto_remediated'] = False
            incident_report['remediation_note'] = 'Auto-remediation available'
        
        print("\n" + "="*60)
        print(f"✅ INVESTIGATION COMPLETE: {incident_id}")
        print(f"   Severity: {incident_report['severity']}")
        print(f"   Slack: {'Sent' if notification_sent else 'Failed'}")
        print("="*60 + "\n")
        
        return incident_report
    
    def _extract_log_group(self, alarm_name: str) -> str:
        """
        Tries to guess log group name from alarm name.
        
        WHY THIS METHOD:
        CloudWatch alarm names often contain the service name.
        Convention: 'payment-service-high-cpu' 
                 -> '/aws/lambda/payment-service'
        
        This saves us from needing to configure log group
        for every single alarm separately.
        
        In production you would store this mapping in
        DynamoDB or AWS Parameter Store.
        """
        
        # Common patterns for log groups
        # Remove common alarm suffixes to get service name
        service_name = alarm_name
        
        suffixes_to_remove = [
            '-high-cpu', '-high-memory', '-high-errors',
            '-alarm', '-alert', '-monitor',
            '_high_cpu', '_alarm', '_alert'
        ]
        
        for suffix in suffixes_to_remove:
            service_name = service_name.replace(suffix, '')
        
        # Default to Lambda log group format
        # Most common in modern AWS architectures
        log_group = f"/aws/lambda/{service_name}"
        
        print(f"   Extracted log group: {log_group}")
        return log_group
    
    def _store_incident(self, incident_report: dict) -> bool:
        """
        Saves incident report to S3 as JSON file.
        
        WHY JSON IN S3:
        Simple, readable, queryable with Athena later.
        File path includes date for easy organization.
        Example: incidents/2026/04/08/INC-20260408-230641.json
        """
        try:
            incident_id = incident_report.get('incident_id', 'unknown')
            date_path = datetime.now().strftime('%Y/%m/%d')
            s3_key = f"incidents/{date_path}/{incident_id}.json"
            
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(incident_report, indent=2, default=str),
                ContentType='application/json'
            )
            
            print(f"   ✅ Stored at s3://{self.s3_bucket}/{s3_key}")
            return True
            
        except Exception as e:
            print(f"   ⚠️ S3 storage failed: {str(e)}")
            return False


# TEST BLOCK
if __name__ == "__main__":
    
    print("🧪 TESTING FULL INCIDENT AGENT")
    print("This will run a complete end-to-end test:")
    print("CloudWatch -> AI Analysis -> Slack Notification")
    print()
    
    # Initialize agent
    agent = IncidentAgent()
    
    # Simulate a real incident
    # This is exactly what Lambda will send when a real alarm fires
    result = agent.investigate(
        alarm_name="payment-service-high-errors",
        namespace="AWS/Lambda",
        metric_name="Errors",
        log_group="/aws/lambda/payment-service"
    )
    
    print("\n📋 FINAL INCIDENT REPORT:")
    print(json.dumps(result, indent=2, default=str))