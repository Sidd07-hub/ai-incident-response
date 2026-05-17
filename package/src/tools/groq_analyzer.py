# src/tools/groq_analyzer.py
# Uses OpenRouter API — no Cloudflare blocking, works in India + AWS Lambda

import json
import os
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

class GroqAnalyzer:
    
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")
        
        # OpenRouter supports same models as Groq
        # meta-llama/llama-3.3-70b-instruct is free tier
        self.model = "openrouter/free"
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        print(f"AI Analyzer initialized with model: {self.model}")
    
    def analyze_incident(self, alarm_name: str,
                         logs: list,
                         metrics: dict) -> dict:

        if len(logs) > 50:
            logs_text = '\n'.join(logs[-50:])
        else:
            logs_text = '\n'.join(logs) if logs else "No logs available"
        
        metrics_text = json.dumps(metrics, indent=2, default=str)
        
        prompt = f"""You are a senior AWS Site Reliability Engineer (SRE) 
with 10 years of experience diagnosing production incidents.

A production incident has been detected. Analyze the data below 
and provide a precise diagnosis.

=== INCIDENT ALARM ===
Alarm Name: {alarm_name}

=== APPLICATION LOGS (Last 30 minutes) ===
{logs_text}

=== METRIC DATA ===
{metrics_text}

=== REQUIRED OUTPUT FORMAT ===
Return ONLY this JSON. No explanation before or after. No markdown.
No code blocks. Pure JSON only:

{{
    "severity": "CRITICAL or HIGH or MEDIUM or LOW",
    "affected_service": "name of the service that is failing",
    "root_cause": "clear 2-3 sentence explanation of what caused this",
    "immediate_action": "exact steps to fix this RIGHT NOW",
    "prevention": "how to prevent this from happening again",
    "confidence": "HIGH or MEDIUM or LOW based on how clear the logs are"
}}"""

        print(f"Sending incident data to AI for analysis...")
        print(f"Alarm: {alarm_name}")
        print(f"Log lines analyzed: {len(logs)}")
        
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1000,
                "temperature": 0.1
            }
            
            data = json.dumps(payload).encode('utf-8')
            
            req = urllib.request.Request(
                self.api_url,
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}',
                    'HTTP-Referer': 'https://github.com/ai-incident-response',
                    'X-Title': 'AI Incident Response'
                },
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                response_body = json.loads(response.read().decode('utf-8'))
            
            ai_response = response_body['choices'][0]['message']['content'].strip()
            print(f"AI response received: {len(ai_response)} characters")
            
            return self._parse_ai_response(ai_response)
            
        except Exception as e:
            print(f"Error calling AI API: {str(e)}")
            return self._fallback_response(alarm_name, str(e))
    
    def _parse_ai_response(self, response_text: str) -> dict:
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end > start:
                try:
                    return json.loads(response_text[start:end])
                except json.JSONDecodeError:
                    pass
            return self._fallback_response("unknown", "JSON parsing failed")
    
    def _fallback_response(self, alarm_name: str, error: str) -> dict:
        return {
            "severity": "HIGH",
            "affected_service": alarm_name,
            "root_cause": f"AI analysis unavailable. Error: {error}.",
            "immediate_action": "Check CloudWatch logs manually in AWS Console.",
            "prevention": "Investigate root cause after resolving incident.",
            "confidence": "LOW"
        }


if __name__ == "__main__":
    test_logs = [
        "ERROR OutOfMemoryError: Java heap space",
        "ERROR Failed to process request: timeout",
        "WARN Connection pool exhausted",
        "ERROR Database connection failed: too many connections",
    ]
    test_metrics = {
        "metric_name": "CPUUtilization",
        "datapoints": [
            {"time": "14:20", "average": 95.3, "maximum": 99.8}
        ]
    }
    
    analyzer = GroqAnalyzer()
    result = analyzer.analyze_incident(
        "production-high-cpu-alarm",
        test_logs,
        test_metrics
    )
    print(json.dumps(result, indent=2))