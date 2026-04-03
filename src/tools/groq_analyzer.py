# src/tools/groq_analyzer.py

import json
import os
from groq import Groq
from dotenv import load_dotenv

# Load .env file so we can read GROQ_API_KEY
# WHY: We never hardcode API keys in code
# dotenv reads the .env file and makes keys available via os.environ
load_dotenv()

class GroqAnalyzer:
    
    def __init__(self):
        # Initialize Groq client with API key from .env file
        # If key is missing, this will raise an error immediately
        # WHY FAIL FAST: Better to crash at startup than fail silently later
        api_key = os.getenv('GROQ_API_KEY')
        
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found. "
                "Check your .env file has GROQ_API_KEY=your_key_here"
            )
        
        self.client = Groq(api_key=api_key)
        
        # Model we are using
        # WHY llama-3.3-70b-versatile:
        # 70 billion parameters = very intelligent
        # versatile = good at reasoning, analysis, structured output
        # Free on Groq with generous rate limits
        self.model = "llama-3.3-70b-versatile"
        
        print(f"GroqAnalyzer initialized with model: {self.model}")
    
    def analyze_incident(self, alarm_name: str, 
                         logs: list, 
                         metrics: dict) -> dict:
        """
        Sends incident data to Groq LLM for analysis.
        
        alarm_name: Name of the CloudWatch alarm that fired
        logs: List of log lines from CloudWatch (last 30 mins)
        metrics: Dictionary of metric data (CPU, errors etc)
        
        Returns: Dictionary with severity, root_cause, recommendation
        """
        
        # Format logs into readable text for the AI
        # Take last 50 lines maximum
        # WHY 50: More lines = more tokens = slower and costlier
        # 50 recent lines almost always contain the root cause
        if len(logs) > 50:
            logs_text = '\n'.join(logs[-50:])
            print("Using last 50 log lines for analysis")
        else:
            logs_text = '\n'.join(logs) if logs else "No logs available"
        
        # Format metrics as readable JSON string
        metrics_text = json.dumps(metrics, indent=2, default=str)
        
        # THE PROMPT — Most Critical Part of This Entire Project
        # 
        # WHY THIS STRUCTURE:
        # 1. Role definition — tells AI WHO it is (expert SRE)
        #    Without this, AI gives generic answers
        #    With this, AI thinks and responds like an expert
        #
        # 2. Structured input — separates alarm, logs, metrics clearly
        #    AI can focus on each section without confusion
        #
        # 3. Exact output format — tells AI EXACTLY what JSON to return
        #    Without this, AI adds explanation text that breaks JSON parsing
        #
        # 4. Examples in format — shows AI the expected values
        #    AI follows examples very accurately
        
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

=== YOUR TASK ===
Analyze the above data and identify:
1. What exactly went wrong
2. Why it went wrong  
3. How to fix it right now
4. How to prevent it in future

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
}}

Severity guide:
- CRITICAL: Service is completely down, users cannot access it
- HIGH: Service is degraded, some users affected
- MEDIUM: Performance issue, no user impact yet
- LOW: Warning sign, needs attention but not urgent"""

        print("Sending incident data to Groq AI for analysis...")
        print(f"Alarm: {alarm_name}")
        print(f"Log lines analyzed: {len(logs)}")
        
        try:
            # Make the API call to Groq
            # This is where the AI actually thinks and responds
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        # 'user' role means this is our input to the AI
                        # Alternative is 'system' role for instructions
                        # WHY user role here: we combine instructions + data
                        # in one message for simplicity
                        "role": "user",
                        "content": prompt
                    }
                ],
                # Maximum tokens in the response
                # 1000 tokens is enough for our JSON response
                # WHY NOT MORE: We only need structured JSON, not essays
                max_tokens=1000,
                
                # Temperature controls creativity vs consistency
                # 0.1 = very consistent, focused, less creative
                # WHY LOW TEMPERATURE:
                # We need consistent JSON output every time
                # High temperature (0.8+) would give different formats each run
                # which breaks our JSON parser
                temperature=0.1,
            )
            
            # Extract the text response from API result
            ai_response = response.choices[0].message.content.strip()
            print(f"AI response received: {len(ai_response)} characters")
            
            # Parse JSON from AI response
            analysis = self._parse_ai_response(ai_response)
            return analysis
            
        except Exception as e:
            print(f"Error calling Groq API: {str(e)}")
            # Return a fallback response so the system keeps running
            # WHY FALLBACK: Notification must go out even if AI fails
            return self._fallback_response(alarm_name, str(e))
    
    def _parse_ai_response(self, response_text: str) -> dict:
        """
        Parses the JSON response from AI.
        
        WHY SEPARATE METHOD:
        Parsing logic is complex. Keeping it separate makes
        the main method clean and this method easy to test.
        """
        try:
            # Direct JSON parse — works when AI follows instructions
            return json.loads(response_text)
            
        except json.JSONDecodeError:
            # AI sometimes adds markdown code blocks like ```json
            # even when told not to. We handle this gracefully.
            print("Direct JSON parse failed, trying to extract JSON...")
            
            # Find JSON content between curly braces
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            
            if start != -1 and end > start:
                json_str = response_text[start:end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    print("JSON extraction also failed")
            
            # If all parsing fails, return structured error response
            return self._fallback_response("unknown", "JSON parsing failed")
    
    def _fallback_response(self, alarm_name: str, error: str) -> dict:
        """
        Returns when AI call fails.
        System still notifies team — just without AI analysis.
        
        WHY THIS EXISTS:
        The notification pipeline should NEVER go down because AI failed.
        Team must always be notified of incidents.
        Degraded notification is better than no notification.
        """
        return {
            "severity": "HIGH",
            "affected_service": alarm_name,
            "root_cause": f"AI analysis unavailable. Error: {error}. "
                         f"Please investigate manually.",
            "immediate_action": "Check CloudWatch logs and metrics manually "
                               "in AWS Console.",
            "prevention": "Investigate root cause after resolving incident.",
            "confidence": "LOW"
        }


# TEST BLOCK
# Run this file directly to test: python src/tools/groq_analyzer.py
if __name__ == "__main__":
    
    # Sample test data simulating a real incident
    test_alarm = "production-high-cpu-alarm"
    
    test_logs = [
        "2024-01-15 14:30:01 ERROR OutOfMemoryError: Java heap space",
        "2024-01-15 14:30:02 ERROR Failed to process request: timeout",
        "2024-01-15 14:30:03 WARN Connection pool exhausted, waiting...",
        "2024-01-15 14:30:05 ERROR Database connection failed: too many connections",
        "2024-01-15 14:30:06 ERROR Request failed after 3 retries",
        "2024-01-15 14:30:08 WARN Memory usage at 94%",
        "2024-01-15 14:30:10 ERROR Service unavailable: upstream timeout",
    ]
    
    test_metrics = {
        "metric_name": "CPUUtilization",
        "namespace": "AWS/EC2",
        "datapoints": [
            {"time": "14:00", "average": 45.2, "maximum": 52.1, "minimum": 38.0},
            {"time": "14:05", "average": 58.3, "maximum": 67.4, "minimum": 49.2},
            {"time": "14:10", "average": 72.1, "maximum": 85.3, "minimum": 65.0},
            {"time": "14:15", "average": 88.5, "maximum": 97.2, "minimum": 79.1},
            {"time": "14:20", "average": 95.3, "maximum": 99.8, "minimum": 89.4},
        ]
    }
    
    print("=" * 50)
    print("TESTING GROQ AI ANALYZER")
    print("=" * 50)
    
    analyzer = GroqAnalyzer()
    result = analyzer.analyze_incident(test_alarm, test_logs, test_metrics)
    
    print("\n" + "=" * 50)
    print("AI ANALYSIS RESULT:")
    print("=" * 50)
    print(json.dumps(result, indent=2))