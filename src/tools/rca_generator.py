# src/tools/rca_generator.py
import json
import os
import boto3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class RCAGenerator:
    """
    Generates detailed Root Cause Analysis reports.
    
    WHY THIS EXISTS:
    AI gives a quick diagnosis — 2-3 sentences.
    RCA is a formal document that includes:
    - Full timeline of events
    - Root cause with evidence
    - Impact assessment
    - What was done to fix it
    - How to prevent recurrence
    
    Companies require RCA for every production incident.
    This automates what used to take 1-2 hours manually.
    """

    def __init__(self):
        self.s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION_NAME', 'us-east-1'))
        self.s3_bucket = os.getenv('S3_BUCKET_NAME', '')
        print("RCAGenerator initialized")

    def generate(self, incident_report: dict,
                 risk_assessment: dict,
                 remediation_result: dict,
                 logs: list) -> dict:
        """
        Generates complete RCA report.
        
        Combines all data from the incident:
        - Original alarm details
        - AI analysis
        - Risk assessment decision
        - Remediation action taken
        - Evidence from logs
        """

        incident_id = incident_report.get('incident_id', 'UNKNOWN')
        print(f"Generating RCA for incident: {incident_id}")

        # Build timeline of events
        timeline = self._build_timeline(
            incident_report, 
            risk_assessment, 
            remediation_result
        )

        # Extract evidence from logs
        evidence = self._extract_evidence(logs)

        # Calculate impact
        impact = self._assess_impact(incident_report)

        # Build complete RCA document
        rca = {
            'rca_id': f"RCA-{incident_id}",
            'incident_id': incident_id,
            'generated_at': datetime.utcnow().isoformat(),
            'generated_by': 'AI Incident Response System',

            # Section 1: Executive Summary
            'executive_summary': {
                'title': f"Incident RCA: {incident_report.get('alarm_name', 'Unknown')}",
                'severity': incident_report.get('severity', 'UNKNOWN'),
                'affected_service': incident_report.get('affected_service', 'Unknown'),
                'duration': 'Under investigation',
                'status': 'Resolved' if remediation_result.get('success') else 'Under investigation',
                'summary': incident_report.get('root_cause', 'Under investigation')
            },

            # Section 2: Timeline
            # WHY TIMELINE:
            # Shows exact sequence of events.
            # Critical for understanding what triggered what.
            # Also required for compliance audits.
            'timeline': timeline,

            # Section 3: Root Cause Analysis
            'root_cause_analysis': {
                'primary_cause': incident_report.get('root_cause', 'Unknown'),
                'contributing_factors': self._identify_contributing_factors(
                    incident_report, logs
                ),
                'evidence': evidence,
                'ai_confidence': incident_report.get('confidence', 'LOW')
            },

            # Section 4: Impact Assessment
            'impact_assessment': impact,

            # Section 5: Remediation
            'remediation': {
                'action_taken': remediation_result.get('action', 'None'),
                'executed_automatically': not risk_assessment.get('requires_approval', True),
                'result': 'Success' if remediation_result.get('success') else 'Failed',
                'output': remediation_result.get('output', ''),
                'risk_level': risk_assessment.get('action_risk_level', 'UNKNOWN'),
                'decision_reasoning': risk_assessment.get('reasoning', '')
            },

            # Section 6: Prevention
            # WHY THIS SECTION:
            # RCA is useless without prevention steps.
            # This is what stops the same incident
            # from happening again next week.
            'prevention': {
                'immediate_actions': incident_report.get('immediate_action', ''),
                'long_term_prevention': incident_report.get('prevention', ''),
                'monitoring_improvements': self._suggest_monitoring(incident_report),
                'recommended_alerts': self._suggest_alerts(incident_report)
            },

            # Section 7: Raw Data
            'raw_data': {
                'logs_analyzed': len(logs),
                'log_sample': logs[-10:] if logs else [],
                'alarm_name': incident_report.get('alarm_name', ''),
                'log_group': incident_report.get('log_group', '')
            }
        }

        # Save RCA to S3
        s3_path = self._save_to_s3(rca, incident_id)
        rca['s3_path'] = s3_path

        print(f"RCA generated: {rca['rca_id']}")
        return rca

    def _build_timeline(self, incident_report: dict,
                        risk_assessment: dict,
                        remediation_result: dict) -> list:
        """Builds chronological timeline of incident events."""
        now = datetime.utcnow().isoformat()

        timeline = [
            {
                'time': incident_report.get('timestamp', now),
                'event': 'Incident Detected',
                'details': f"CloudWatch alarm fired: {incident_report.get('alarm_name')}"
            },
            {
                'time': now,
                'event': 'AI Analysis Completed',
                'details': f"Severity: {incident_report.get('severity')} | "
                          f"Confidence: {incident_report.get('confidence')}"
            },
            {
                'time': now,
                'event': 'Risk Assessment Completed',
                'details': f"Decision: {risk_assessment.get('decision')} | "
                          f"Action Risk: {risk_assessment.get('action_risk_level')}"
            }
        ]

        if remediation_result.get('action'):
            timeline.append({
                'time': remediation_result.get('timestamp', now),
                'event': 'Remediation Executed',
                'details': f"Action: {remediation_result.get('action')} | "
                          f"Result: {'Success' if remediation_result.get('success') else 'Failed'}"
            })

        if remediation_result.get('success'):
            timeline.append({
                'time': now,
                'event': 'Incident Resolved',
                'details': remediation_result.get('message', 'Resolved by auto-remediation')
            })

        return timeline

    def _extract_evidence(self, logs: list) -> list:
        """
        Extracts key evidence lines from logs.
        
        WHY: RCA needs specific evidence not all 100 log lines.
        We extract ERROR and WARN lines as key evidence.
        """
        evidence = []
        keywords = ['ERROR', 'CRITICAL', 'FATAL', 'Exception',
                   'failed', 'timeout', 'refused', 'exhausted']

        for log in logs:
            for keyword in keywords:
                if keyword.lower() in log.lower():
                    evidence.append(log.strip())
                    break

        # Return max 10 evidence lines
        return evidence[:10]

    def _assess_impact(self, incident_report: dict) -> dict:
        """Assesses business impact of the incident."""
        severity = incident_report.get('severity', 'MEDIUM')

        impact_map = {
            'CRITICAL': {
                'user_impact': 'Complete service outage — all users affected',
                'business_impact': 'High — revenue loss possible',
                'data_risk': 'Possible data integrity issues',
                'estimated_affected_users': 'All users'
            },
            'HIGH': {
                'user_impact': 'Degraded service — some users affected',
                'business_impact': 'Medium — performance degradation',
                'data_risk': 'Low data risk',
                'estimated_affected_users': 'Subset of users'
            },
            'MEDIUM': {
                'user_impact': 'Minor degradation — most users unaffected',
                'business_impact': 'Low — minor performance issue',
                'data_risk': 'No data risk',
                'estimated_affected_users': 'Few users'
            },
            'LOW': {
                'user_impact': 'No user impact',
                'business_impact': 'Minimal',
                'data_risk': 'No data risk',
                'estimated_affected_users': 'None'
            }
        }

        return impact_map.get(severity, impact_map['MEDIUM'])

    def _identify_contributing_factors(self, 
                                        incident_report: dict,
                                        logs: list) -> list:
        """Identifies factors that contributed to the incident."""
        factors = []
        root_cause = incident_report.get('root_cause', '').lower()

        if 'memory' in root_cause:
            factors.append('Insufficient memory allocation')
            factors.append('Possible memory leak in application')

        if 'cpu' in root_cause:
            factors.append('High CPU utilization')
            factors.append('Insufficient compute resources')

        if 'database' in root_cause or 'connection' in root_cause:
            factors.append('Database connection pool exhaustion')
            factors.append('High concurrent request volume')

        if 'timeout' in root_cause:
            factors.append('Network latency or slow downstream service')
            factors.append('Insufficient timeout configuration')

        if not factors:
            factors.append('Root cause under investigation')
            factors.append('Insufficient log data for full analysis')

        return factors

    def _suggest_monitoring(self, incident_report: dict) -> list:
        """Suggests monitoring improvements to catch this earlier."""
        suggestions = [
            'Add anomaly detection on CloudWatch metrics',
            'Set up composite alarms for correlated failures',
            'Implement log-based metrics for application errors',
            'Add dashboard for real-time service health visibility'
        ]

        severity = incident_report.get('severity', 'MEDIUM')
        if severity in ['CRITICAL', 'HIGH']:
            suggestions.append('Consider PagerDuty integration for CRITICAL alerts')
            suggestions.append('Add synthetic monitoring to detect issues before users do')

        return suggestions

    def _suggest_alerts(self, incident_report: dict) -> list:
        """Suggests new CloudWatch alarms to add."""
        return [
            'Add alarm for P99 latency > 2 seconds',
            'Add alarm for error rate > 1% over 5 minutes',
            'Add alarm for memory utilization > 80%',
            'Add alarm for disk utilization > 85%',
            'Add alarm for connection pool utilization > 80%'
        ]

    def _save_to_s3(self, rca: dict, incident_id: str) -> str:
        """
        Saves RCA report to S3.
        
        WHY S3:
        RCA documents are audit artifacts.
        Companies must retain them for compliance.
        S3 provides durable, cheap, long-term storage.
        Future: query all RCAs with Athena to find patterns.
        """
        if not self.s3_bucket:
            print("S3 bucket not configured — skipping RCA storage")
            return ''

        try:
            date_path = datetime.utcnow().strftime('%Y/%m/%d')
            s3_key = f"rca/{date_path}/RCA-{incident_id}.json"

            self.s3.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(rca, indent=2, default=str),
                ContentType='application/json'
            )

            s3_path = f"s3://{self.s3_bucket}/{s3_key}"
            print(f"RCA saved to: {s3_path}")
            return s3_path

        except Exception as e:
            print(f"Failed to save RCA to S3: {str(e)}")
            return ''

    def format_for_slack(self, rca: dict) -> str:
        """
        Formats RCA as readable Slack message.
        Short version — full version is in S3.
        """
        summary = rca.get('executive_summary', {})
        prevention = rca.get('prevention', {})
        remediation = rca.get('remediation', {})
        timeline = rca.get('timeline', [])

        slack_text = f"""
*📋 ROOT CAUSE ANALYSIS REPORT*
*RCA ID:* {rca.get('rca_id')}
*Generated:* {rca.get('generated_at')}

*📊 Summary*
- Severity: {summary.get('severity')}
- Service: {summary.get('affected_service')}
- Status: {summary.get('status')}

*🔍 Root Cause*
{summary.get('summary')}

*⚡ Remediation Taken*
- Action: {remediation.get('action_taken')}
- Result: {remediation.get('result')}
- Auto-executed: {remediation.get('executed_automatically')}

*📅 Timeline*
{self._format_timeline(timeline)}

*🛡️ Prevention*
{prevention.get('long_term_prevention')}

*📁 Full RCA:* {rca.get('s3_path', 'Not stored')}
        """.strip()

        return slack_text

    def _format_timeline(self, timeline: list) -> str:
        """Formats timeline as readable text."""
        if not timeline:
            return "No timeline available"

        lines = []
        for event in timeline:
            lines.append(f"• {event.get('event')}: {event.get('details')}")

        return '\n'.join(lines)


if __name__ == "__main__":
    generator = RCAGenerator()

    # Test with sample data
    sample_incident = {
        'incident_id': 'INC-20260522-120000',
        'alarm_name': 'ai-incident-response-ec2-high-cpu',
        'severity': 'HIGH',
        'affected_service': 'Flask App on EC2',
        'root_cause': 'CPU spike caused by stress test process consuming all available cores',
        'immediate_action': 'Kill stress process immediately',
        'prevention': 'Add CPU limits and auto-scaling policies',
        'confidence': 'HIGH',
        'timestamp': datetime.utcnow().isoformat(),
        'log_group': '/ec2/flask-app'
    }

    sample_risk = {
        'decision': 'AUTO_EXECUTE',
        'action_risk_level': 'LOW',
        'requires_approval': False,
        'reasoning': 'Low risk action safe to auto-execute'
    }

    sample_remediation = {
        'action': 'kill_stress_process',
        'success': True,
        'output': 'Stress process killed successfully',
        'message': 'CPU normalizing',
        'timestamp': datetime.utcnow().isoformat()
    }

    sample_logs = [
        "ERROR: CPU at 98% - system unresponsive",
        "WARNING: High load average detected",
        "ERROR: Request timeout after 30s"
    ]

    rca = generator.generate(
        sample_incident,
        sample_risk,
        sample_remediation,
        sample_logs
    )

    print("\nRCA GENERATED:")
    print(json.dumps(rca, indent=2, default=str))

    print("\nSLACK FORMAT:")
    print(generator.format_for_slack(rca))