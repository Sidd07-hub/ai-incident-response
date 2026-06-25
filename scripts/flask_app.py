# scripts/flask_app.py
# Simple Flask app that runs on EC2
# Generates real logs and metrics for our AI agent to analyze

import boto3
import json
import logging
import os
import random
import time
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# ─────────────────────────────────────────────────────
# LOGGING SETUP
# WHY: We send logs to CloudWatch so our AI can read them
# Without proper logging, AI has nothing to analyze
# ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        # Write to file — CloudWatch agent reads this file
        logging.FileHandler('/var/log/flask_app.log'),
        # Also print to console
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# CloudWatch client for custom metrics
# WHY CUSTOM METRICS:
# AWS only collects CPU by default on EC2
# We need error count, request count, latency
# Custom metrics let us track application-level health
cloudwatch = boto3.client('cloudwatch', region_name=os.environ.get('AWS_REGION', 'us-east-1'))

# Track request statistics
stats = {
    'total_requests': 0,
    'total_errors': 0,
    'total_latency': 0
}

def send_metric(metric_name, value, unit='Count'):
    """
    Sends custom metric to CloudWatch.
    
    WHY THIS FUNCTION:
    CloudWatch alarms can watch these metrics.
    When ErrorCount exceeds threshold — alarm fires.
    Our AI agent then investigates automatically.
    """
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
        logger.error(f"Failed to send metric {metric_name}: {str(e)}")


# ─────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────

@app.route('/health')
def health():
    """Health check endpoint"""
    logger.info("Health check requested - service is running")
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'stats': stats
    })


@app.route('/api/payment', methods=['POST'])
def process_payment():
    """
    Simulates a payment processing endpoint.
    WHY THIS ENDPOINT:
    Payment service is a realistic production scenario.
    High error rate here would trigger real incidents.
    """
    start_time = time.time()
    stats['total_requests'] += 1

    try:
        # Simulate processing time
        time.sleep(random.uniform(0.1, 0.5))

        # 10% chance of random error (normal operation)
        if random.random() < 0.10:
            raise ValueError("Payment gateway timeout")

        latency = (time.time() - start_time) * 1000
        stats['total_latency'] += latency

        logger.info(f"Payment processed successfully - latency: {latency:.2f}ms")
        send_metric('RequestCount', 1)
        send_metric('Latency', latency, 'Milliseconds')

        return jsonify({'status': 'success', 'latency_ms': latency})

    except Exception as e:
        stats['total_errors'] += 1
        latency = (time.time() - start_time) * 1000

        logger.error(f"Payment processing failed: {str(e)} - latency: {latency:.2f}ms")
        send_metric('ErrorCount', 1)
        send_metric('RequestCount', 1)

        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/simulate/cpu-spike')
def simulate_cpu_spike():
    """
    Simulates high CPU usage.
    WHY THIS ENDPOINT:
    Lets us trigger REAL CPU spike on EC2.
    CloudWatch detects real CPU increase.
    AI agent receives real metrics — not fake data.
    """
    logger.warning("CPU spike simulation started")
    logger.warning("High CPU load detected - system under stress")

    # Actually consume CPU
    end_time = time.time() + 30  # 30 seconds of CPU stress
    while time.time() < end_time:
        # Burn CPU cycles
        _ = [x**2 for x in range(10000)]

    logger.warning("CPU spike simulation completed")
    return jsonify({'status': 'cpu_spike_completed', 'duration_seconds': 30})


@app.route('/simulate/memory-pressure')
def simulate_memory_pressure():
    """
    Simulates memory pressure.
    Allocates large amount of memory then releases.
    """
    logger.warning("Memory pressure simulation started")
    logger.warning("Allocating large memory blocks - potential memory leak detected")

    # Allocate ~200MB
    memory_hog = []
    for i in range(200):
        memory_hog.append(' ' * 1024 * 1024)  # 1MB each