#!/bin/bash
# scripts/setup_ec2.sh
# This script runs automatically when EC2 starts
# It installs everything needed for our Flask app

# WHY USER DATA SCRIPT:
# True DevOps approach — no manual SSH installation
# Everything is automated and reproducible
# If we destroy and recreate EC2, it self-configures

set -e  # Exit on any error
exec > /var/log/user-data.log 2>&1  # Log everything

echo "=========================================="
echo "EC2 Setup Script Starting"
echo "Project: ${project_name}"
echo "Region: ${aws_region}"
echo "Time: $(date)"
echo "=========================================="

# ─────────────────────────────────────────────
# STEP 1: Update system packages
# ─────────────────────────────────────────────
echo "Step 1: Updating system packages..."
yum update -y
echo "System packages updated"

# ─────────────────────────────────────────────
# STEP 2: Install Python and pip
# ─────────────────────────────────────────────
echo "Step 2: Installing Python..."
yum install -y python3 python3-pip
echo "Python version: $(python3 --version)"

# ─────────────────────────────────────────────
# STEP 3: Install stress tool
# WHY: We use stress to simulate CPU/memory load
# This creates REAL incidents our AI can detect
# ─────────────────────────────────────────────
echo "Step 3: Installing stress tool..."
amazon-linux-extras install epel -y
yum install -y stress
echo "Stress tool installed"

# ─────────────────────────────────────────────
# STEP 4: Install Flask and dependencies
# ─────────────────────────────────────────────
echo "Step 4: Installing Flask..."
pip3 install flask boto3
echo "Flask installed"

# ─────────────────────────────────────────────
# STEP 5: Install CloudWatch Agent
# WHY: Default EC2 metrics only include CPU
# CloudWatch agent adds: memory, disk, network
# Our AI agent needs these for accurate diagnosis
# ─────────────────────────────────────────────
echo "Step 5: Installing CloudWatch agent..."
yum install -y amazon-cloudwatch-agent

# CloudWatch agent configuration
# Tells agent WHAT to collect and WHERE to send it
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWCONFIG'
{
    "agent": {
        "metrics_collection_interval": 60,
        "run_as_user": "root"
    },
    "logs": {
        "logs_collected": {
            "files": {
                "collect_list": [
                    {
                        "file_path": "/var/log/flask_app.log",
                        "log_group_name": "/ec2/flask-app",
                        "log_stream_name": "{instance_id}",
                        "timezone": "UTC"
                    },
                    {
                        "file_path": "/var/log/user-data.log",
                        "log_group_name": "/ec2/setup-logs",
                        "log_stream_name": "{instance_id}",
                        "timezone": "UTC"
                    }
                ]
            }
        }
    },
    "metrics": {
        "namespace": "CWAgent",
        "metrics_collected": {
            "mem": {
                "measurement": [
                    "mem_used_percent",
                    "mem_available_percent"
                ],
                "metrics_collection_interval": 60
            },
            "disk": {
                "measurement": [
                    "used_percent",
                    "free"
                ],
                "metrics_collection_interval": 60,
                "resources": ["/"]
            },
            "cpu": {
                "measurement": [
                    "cpu_usage_active",
                    "cpu_usage_system",
                    "cpu_usage_user"
                ],
                "metrics_collection_interval": 60
            },
            "net": {
                "measurement": [
                    "net_bytes_recv",
                    "net_bytes_sent"
                ],
                "metrics_collection_interval": 60
            }
        }
    }
}
CWCONFIG

# Start CloudWatch agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
    -s

echo "CloudWatch agent started"

# ─────────────────────────────────────────────
# STEP 6: Copy Flask app and start it
# ─────────────────────────────────────────────
echo "Step 6: Setting up Flask app..."

# Create app directory
mkdir -p /opt/flask-app

# Create Flask app directly
cat > /opt/flask-app/app.py << 'FLASKAPP'
import boto3
import json
import logging
import os
import random
import time
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler('/var/log/flask_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

cloudwatch = boto3.client('cloudwatch', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))

def send_metric(metric_name, value, unit='Count'):
    try:
        cloudwatch.put_metric_data(
            Namespace='FlaskApp',
            MetricData=[{
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }]
        )
    except Exception as e:
        logger.error(f"Failed to send metric: {str(e)}")

@app.route('/health')
def health():
    logger.info("Health check - service running normally")
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/simulate/cpu-spike')
def cpu_spike():
    logger.warning("CPU SPIKE DETECTED - High load starting")
    logger.warning("Process consuming excessive CPU resources")
    end_time = time.time() + 60
    while time.time() < end_time:
        _ = [x**2 for x in range(10000)]
    logger.warning("CPU spike ended")
    return jsonify({'status': 'cpu_spike_completed'})

@app.route('/simulate/error-storm')
def error_storm():
    logger.error("ERROR STORM STARTING - Multiple failures detected")
    for i in range(20):
        error_types = [
            "Database connection pool exhausted - max 100 connections reached",
            "Request timeout after 30s - upstream service not responding",
            "Out of memory - heap size exceeded limit",
            "Connection refused - service unavailable on port 8080"
        ]
        error = random.choice(error_types)
        logger.error(f"CRITICAL ERROR [{i+1}/20]: {error}")
        send_metric('ErrorCount', 1)
        time.sleep(0.3)
    logger.error("ERROR STORM COMPLETE")
    return jsonify({'status': 'error_storm_completed', 'errors': 20})

@app.route('/simulate/memory-pressure')
def memory_pressure():
    logger.warning("MEMORY PRESSURE - High memory consumption detected")
    memory_hog = []
    for i in range(100):
        memory_hog.append(' ' * 1024 * 1024)
        if i % 10 == 0:
            logger.warning(f"Memory usage increasing: {i+1}MB allocated")
    logger.warning("Memory pressure simulation complete")
    del memory_hog
    return jsonify({'status': 'memory_pressure_completed'})

@app.route('/simulate/slow-response')
def slow_response():
    logger.warning("SLOW RESPONSE - Database query taking too long")
    logger.warning("Connection pool waiting - possible deadlock detected")
    time.sleep(8)
    send_metric('Latency', 8000, 'Milliseconds')
    logger.warning("Slow response completed")
    return jsonify({'status': 'slow_response_completed'})

if __name__ == '__main__':
    logger.info("=== Flask App Starting ===")
    logger.info("AI Incident Response Demo Application")
    app.run(host='0.0.0.0', port=5000, debug=False)
FLASKAPP

echo "Flask app created"

# ─────────────────────────────────────────────
# STEP 7: Create systemd service
# WHY SYSTEMD:
# App starts automatically on EC2 reboot
# If app crashes, systemd restarts it
# Production-grade process management
# ─────────────────────────────────────────────
cat > /etc/systemd/system/flask-app.service << 'SYSTEMD'
[Unit]
Description=Flask AI Incident Response Demo App
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/flask-app
Environment=AWS_DEFAULT_REGION=${aws_region}
ExecStart=/usr/bin/python3 /opt/flask-app/app.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/flask_app.log
StandardError=append:/var/log/flask_app.log

[Install]
WantedBy=multi-user.target
SYSTEMD

# Create log file with correct permissions
touch /var/log/flask_app.log
chmod 666 /var/log/flask_app.log

# Enable and start Flask service
systemctl daemon-reload
systemctl enable flask-app
systemctl start flask-app

echo "Flask service started"

# ─────────────────────────────────────────────
# STEP 8: Verify everything is running
# ─────────────────────────────────────────────
echo "Step 8: Verifying setup..."
sleep 5

# Check Flask is running
if systemctl is-active --quiet flask-app; then
    echo "Flask app is running"
else
    echo "Flask app failed to start - check logs"
    systemctl status flask-app
fi

# Check CloudWatch agent
if systemctl is-active --quiet amazon-cloudwatch-agent; then
    echo "CloudWatch agent is running"
else
    echo "CloudWatch agent not running"
fi

echo "=========================================="
echo "EC2 Setup Complete!"
echo "Flask app: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):5000"
echo "=========================================="