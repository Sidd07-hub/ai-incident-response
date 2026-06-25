# src/tools/risk_assessor.py

# WHY THIS FILE EXISTS:
# AI can diagnose perfectly but executing wrong fix
# can make things WORSE than the original incident.
# Risk assessor is the safety layer between
# AI recommendation and actual execution.
#
# HUMAN IN THE LOOP (HITL) PATTERN:
# This is a key concept in Agentic AI.
# AI should NOT have unlimited autonomy.
# For high-risk actions — human must approve.
# For low-risk actions — AI can act automatically.

class RiskAssessor:

    def __init__(self):
        # Define which actions are safe to auto-execute
        # and which need human approval
        #
        # LOW RISK = auto-execute immediately
        # These actions have minimal blast radius
        # Worst case: service restarts (expected downtime seconds)
        self.low_risk_actions = [
            'restart_service',
            'clear_logs',
            'restart_flask',
            'kill_stress_process',
            'clear_cache',
            'reload_config'
        ]

        # HIGH RISK = always need human approval
        # These actions have large blast radius
        # Worst case: data loss, extended downtime
        self.high_risk_actions = [
            'reboot_instance',
            'terminate_instance',
            'scale_down',
            'delete_data',
            'modify_database',
            'change_security_group',
            'modify_iam_policy'
        ]

        print("RiskAssessor initialized")

    def assess(self, incident_report: dict, 
               suggested_action: str) -> dict:
        """
        Assesses risk level of a suggested action.

        incident_report: Full incident details from AI
        suggested_action: What action AI recommends

        Returns: Risk assessment with decision

        DECISION LOGIC:
        1. If severity is CRITICAL + action is HIGH RISK
           → Human approval required immediately
        2. If severity is HIGH + action is HIGH RISK
           → Human approval required
        3. If severity is LOW/MEDIUM + action is LOW RISK
           → Auto-execute safely
        4. If severity is CRITICAL + action is LOW RISK
           → Auto-execute BUT warn team
        """

        severity = incident_report.get('severity', 'HIGH')
        affected_service = incident_report.get('affected_service', 'unknown')
        root_cause = incident_report.get('root_cause', '')

        print(f"Assessing risk for action: {suggested_action}")
        print(f"Incident severity: {severity}")

        # Determine action risk level
        action_risk = self._get_action_risk(suggested_action)

        # Make decision based on severity + action risk
        decision = self._make_decision(severity, action_risk)

        # Build warning message if needed
        warning = self._build_warning(
            severity, action_risk, 
            suggested_action, affected_service
        )

        assessment = {
            'action': suggested_action,
            'action_risk_level': action_risk,
            'incident_severity': severity,
            'decision': decision,
            'auto_execute': decision == 'AUTO_EXECUTE',
            'requires_approval': decision == 'REQUIRES_APPROVAL',
            'warning_message': warning,
            'affected_service': affected_service,
            'reasoning': self._explain_decision(
                decision, severity, action_risk, suggested_action
            )
        }

        print(f"Risk decision: {decision}")
        return assessment

    def _get_action_risk(self, action: str) -> str:
        """
        Determines if an action is LOW or HIGH risk.

        WHY THIS METHOD:
        Same action can have different risk levels
        depending on context. We check against
        predefined lists of safe vs dangerous actions.
        """
        action_lower = action.lower()

        # Check if it matches any low risk action
        for low_risk in self.low_risk_actions:
            if low_risk in action_lower:
                return 'LOW'

        # Check if it matches any high risk action
        for high_risk in self.high_risk_actions:
            if high_risk in action_lower:
                return 'HIGH'

        # Unknown action — treat as HIGH risk by default
        # WHY DEFAULT HIGH: Safety first.
        # Unknown actions should always need human review.
        return 'HIGH'

    def _make_decision(self, severity: str, 
                       action_risk: str) -> str:
        """
        Core decision logic.

        Matrix:
        Severity  | Action Risk | Decision
        --------- | ----------- | --------
        CRITICAL  | HIGH        | REQUIRES_APPROVAL
        CRITICAL  | LOW         | AUTO_EXECUTE + WARN
        HIGH      | HIGH        | REQUIRES_APPROVAL
        HIGH      | LOW         | AUTO_EXECUTE
        MEDIUM    | HIGH        | REQUIRES_APPROVAL
        MEDIUM    | LOW         | AUTO_EXECUTE
        LOW       | HIGH        | REQUIRES_APPROVAL
        LOW       | LOW         | AUTO_EXECUTE
        """
        if action_risk == 'HIGH':
            # High risk actions ALWAYS need approval
            # regardless of severity
            return 'REQUIRES_APPROVAL'

        if action_risk == 'LOW':
            # Low risk actions can auto-execute
            return 'AUTO_EXECUTE'

        # Default — require approval
        return 'REQUIRES_APPROVAL'

    def _build_warning(self, severity: str, action_risk: str,
                       action: str, affected_service: str) -> str:
        """
        Builds warning message shown in Slack
        before executing any action.

        WHY WARNINGS:
        Senior engineer suggestion — always warn team
        before executing actions, even automatic ones.
        Team needs to know what is happening.
        """
        if action_risk == 'HIGH':
            return (
                f"⚠️ HIGH RISK ACTION DETECTED\n"
                f"Action: `{action}`\n"
                f"Affected Service: `{affected_service}`\n"
                f"Severity: `{severity}`\n"
                f"This action requires manual approval before execution.\n"
                f"Please review carefully — this could affect production."
            )

        elif severity == 'CRITICAL' and action_risk == 'LOW':
            return (
                f"🟡 NOTICE: Auto-executing low-risk action\n"
                f"Action: `{action}`\n"
                f"Affected Service: `{affected_service}`\n"
                f"Severity: `{severity}`\n"
                f"Action is safe to execute automatically.\n"
                f"Team notified for awareness."
            )

        else:
            return (
                f"✅ Auto-executing safe remediation action\n"
                f"Action: `{action}`\n"
                f"Affected Service: `{affected_service}`"
            )

    def _explain_decision(self, decision: str, severity: str,
                          action_risk: str, action: str) -> str:
        """
        Explains WHY this decision was made.
        Shown in Slack and stored in RCA report.

        WHY EXPLANATION:
        Engineers need to understand WHY AI made a decision.
        Blind AI decisions without explanation reduce trust.
        Explainable AI is a production requirement.
        """
        if decision == 'REQUIRES_APPROVAL':
            return (
                f"Human approval required because action '{action}' "
                f"is classified as HIGH RISK. "
                f"High risk actions are never auto-executed "
                f"regardless of incident severity to prevent "
                f"accidental production impact."
            )

        elif decision == 'AUTO_EXECUTE':
            return (
                f"Auto-executing because action '{action}' "
                f"is classified as LOW RISK with incident "
                f"severity {severity}. "
                f"Low risk actions with known safe outcomes "
                f"are executed automatically to minimize MTTR."
            )

        return "Decision reasoning unavailable."


# TEST BLOCK
if __name__ == "__main__":
    import json

    assessor = RiskAssessor()

    # Test 1: Low risk action
    print("\n" + "="*50)
    print("TEST 1: Low risk action")
    print("="*50)
    result1 = assessor.assess(
        incident_report={
            'severity': 'HIGH',
            'affected_service': 'flask-app',
            'root_cause': 'Service crashed due to memory error'
        },
        suggested_action='restart_service'
    )
    print(json.dumps(result1, indent=2))

    # Test 2: High risk action
    print("\n" + "="*50)
    print("TEST 2: High risk action")
    print("="*50)
    result2 = assessor.assess(
        incident_report={
            'severity': 'CRITICAL',
            'affected_service': 'database',
            'root_cause': 'Database connection exhausted'
        },
        suggested_action='reboot_instance'
    )
    print(json.dumps(result2, indent=2))