# src/tools/auto_remediation.py
import boto3
import os
import time
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class AutoRemediation:

    def __init__(self):
        self.ssm = boto3.client('ssm', region_name=os.getenv('AWS_REGION_NAME', 'us-east-1'))
        self.ec2 = boto3.client('ec2', region_name=os.getenv('AWS_REGION_NAME', 'us-east-1'))
        self.project_name = os.getenv('PROJECT_NAME', 'ai-incident-response')
        print("AutoRemediation initialized")

    def execute(self, action: str, incident_report: dict) -> dict:
        """
        Executes remediation action on EC2.
        
        WHY SSM INSTEAD OF SSH:
        SSH requires open port 22 and key management.
        SSM (Systems Manager) lets us run commands
        on EC2 without SSH — more secure, no open ports.
        Lambda sends command → SSM executes on EC2.
        This is AWS best practice for remote execution.
        """
        print(f"Executing remediation: {action}")
        
        # Get EC2 instance ID from SSM Parameter Store
        instance_id = self._get_instance_id()
        
        if not instance_id:
            return self._failed_result(action, "EC2 instance ID not found in SSM")

        # Route to correct remediation method
        if 'restart_flask' in action or 'restart_service' in action:
            return self._restart_flask_service(instance_id)
        elif 'kill_stress' in action:
            return self._kill_stress_process(instance_id)
        elif 'clear_logs' in action:
            return self._clear_logs(instance_id)
        elif 'restart_flask' in action:
            return self._restart_flask_service(instance_id)
        else:
            return self._restart_flask_service(instance_id)

    def _get_instance_id(self) -> str:
        """
        Gets EC2 instance ID from SSM Parameter Store.
        
        WHY SSM PARAMETER STORE:
        We cannot hardcode instance ID — it changes
        every time we destroy and recreate EC2.
        Terraform stores the ID in SSM automatically.
        Lambda reads it dynamically at runtime.
        """
        try:
            param_name = f"/{self.project_name}/ec2-instance-id"
            response = self.ssm.get_parameter(Name=param_name)
            instance_id = response['Parameter']['Value']
            print(f"Found EC2 instance: {instance_id}")
            return instance_id
        except Exception as e:
            print(f"Failed to get instance ID: {str(e)}")
            return None

    def _run_ssm_command(self, instance_id: str, 
                          commands: list, 
                          description: str) -> dict:
        """
        Runs shell commands on EC2 via SSM.
        
        WHY THIS APPROACH:
        SSM Send Command is the AWS-native way to
        execute commands on EC2 instances remotely.
        No SSH needed. Fully audited. IAM controlled.
        Every command execution is logged in AWS CloudTrail.
        """
        try:
            # Send command to EC2
            response = self.ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName='AWS-RunShellScript',
                Parameters={'commands': commands},
                Comment=description
            )

            command_id = response['Command']['CommandId']
            print(f"SSM command sent: {command_id}")

            # Wait for command to complete
            # Max 60 seconds wait
            for attempt in range(12):
                time.sleep(5)
                try:
                    result = self.ssm.get_command_invocation(
                        CommandId=command_id,
                        InstanceId=instance_id
                    )
                    status = result['Status']
                    print(f"Command status: {status}")

                    if status == 'Success':
                        return {
                            'success': True,
                            'status': 'Success',
                            'output': result.get('StandardOutputContent', ''),
                            'command_id': command_id
                        }
                    elif status in ['Failed', 'TimedOut', 'Cancelled']:
                        return {
                            'success': False,
                            'status': status,
                            'error': result.get('StandardErrorContent', ''),
                            'command_id': command_id
                        }
                except Exception:
                    continue

            return {
                'success': False,
                'status': 'Timeout',
                'error': 'Command did not complete within 60 seconds',
                'command_id': command_id
            }

        except Exception as e:
            return {
                'success': False,
                'status': 'Error',
                'error': str(e)
            }

    def _restart_flask_service(self, instance_id: str) -> dict:
        """
        Restarts Flask application service on EC2.
        
        WHY SYSTEMD:
        Flask runs as a systemd service.
        systemctl restart is clean — stops gracefully,
        waits for active connections to close,
        then starts fresh. No data loss.
        """
        print("Restarting Flask service...")
        result = self._run_ssm_command(
            instance_id=instance_id,
            commands=[
                'systemctl restart flask-app',
                'sleep 3',
                'systemctl status flask-app --no-pager'
            ],
            description='AI Auto-Remediation: Restart Flask service'
        )

        result['action'] = 'restart_flask_service'
        result['timestamp'] = datetime.utcnow().isoformat()
        result['message'] = (
            'Flask service restarted successfully'
            if result['success']
            else 'Failed to restart Flask service'
        )
        return result

    def _kill_stress_process(self, instance_id: str) -> dict:
        """
        Kills stress process causing high CPU.
        
        WHY PKILL:
        stress command runs multiple worker processes.
        pkill kills all processes matching name at once.
        Faster than finding individual PIDs.
        """
        print("Killing stress process...")
        result = self._run_ssm_command(
            instance_id=instance_id,
            commands=[
                'pkill -f stress || echo "No stress process found"',
                'sleep 2',
                'echo "CPU should normalize in 1-2 minutes"'
            ],
            description='AI Auto-Remediation: Kill CPU stress process'
        )

        result['action'] = 'kill_stress_process'
        result['timestamp'] = datetime.utcnow().isoformat()
        result['message'] = (
            'Stress process killed — CPU normalizing'
            if result['success']
            else 'Failed to kill stress process'
        )
        return result

    def _clear_logs(self, instance_id: str) -> dict:
        """Clears large log files to free disk space."""
        print("Clearing logs...")
        result = self._run_ssm_command(
            instance_id=instance_id,
            commands=[
                'truncate -s 0 /var/log/flask_app.log',
                'echo "Logs cleared at $(date)"'
            ],
            description='AI Auto-Remediation: Clear application logs'
        )

        result['action'] = 'clear_logs'
        result['timestamp'] = datetime.utcnow().isoformat()
        result['message'] = (
            'Application logs cleared successfully'
            if result['success']
            else 'Failed to clear logs'
        )
        return result

    def _failed_result(self, action: str, error: str) -> dict:
        return {
            'success': False,
            'action': action,
            'status': 'Failed',
            'error': error,
            'timestamp': datetime.utcnow().isoformat(),
            'message': f'Remediation failed: {error}'
        }


if __name__ == "__main__":
    remediation = AutoRemediation()
    print("AutoRemediation initialized successfully")
    print("Note: Full test requires EC2 instance running")
    print("Will test after terraform apply")