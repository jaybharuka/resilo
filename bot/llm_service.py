"""
LLM Service for AIOps Bot - AI-Powered Alert Analysis and Fix Suggestions
"""
import os
import json
from functools import lru_cache
from typing import Dict, List, Optional
from openai import OpenAI

class LLMService:
    def __init__(self):
        """Initialize the LLM service with OpenAI client"""
        self.client = None
        self.model = "gpt-3.5-turbo"
        
        # Try to initialize OpenAI client
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            self.client = OpenAI(api_key=api_key)
            print("🤖 OpenAI API initialized successfully")
        else:
            print("⚠️  OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
            print("🔧 LLM features will use mock responses for demo purposes.")

    def analyze_alert(self, alert_data: Dict) -> Dict:
        """
        Analyze an alert using AI to provide context and suggestions
        
        Args:
            alert_data: The alert data from Prometheus/Alertmanager
            
        Returns:
            Dictionary containing analysis, severity assessment, and suggestions
        """
        try:
            if not self.client:
                return self._mock_analysis(alert_data)
            
            # Extract key information from alert
            alert_name = alert_data.get('commonLabels', {}).get('alertname', 'Unknown')
            severity = alert_data.get('commonLabels', {}).get('severity', 'unknown')
            
            # Build context for LLM
            context = self._build_alert_context(alert_data)
            
            # Generate AI analysis
            analysis = self._call_llm_for_analysis(alert_name, severity, context)
            
            return {
                'ai_analysis': analysis,
                'suggested_actions': self._generate_fix_suggestions(alert_name, severity, context),
                'impact_assessment': self._assess_impact(alert_name, severity),
                'priority_level': self._calculate_priority(alert_name, severity)
            }
            
        except Exception as e:
            print(f"❌ Error in LLM analysis: {e}")
            return self._mock_analysis(alert_data)

    def _build_alert_context(self, alert_data: Dict) -> str:
        """Build context string for LLM prompt"""
        alerts = alert_data.get('alerts', [])
        context_parts = []
        
        for alert in alerts:
            labels = alert.get('labels', {})
            annotations = alert.get('annotations', {})
            
            context_parts.append(f"""
Alert: {labels.get('alertname', 'Unknown')}
Service: {labels.get('service', 'Unknown')}
Instance: {labels.get('instance', 'Unknown')}
Severity: {labels.get('severity', 'Unknown')}
Summary: {annotations.get('summary', 'No summary')}
Description: {annotations.get('description', 'No description')}
Status: {alert.get('status', 'Unknown')}
""")
        
        return "\n".join(context_parts)

    def _call_llm_for_analysis(self, alert_name: str, severity: str, context: str) -> str:
        """Call OpenAI API for alert analysis"""
        prompt = f"""
You are an expert Site Reliability Engineer (SRE) analyzing a production alert.

Alert Details:
{context}

Please provide a concise analysis including:
1. What this alert indicates
2. Potential root causes
3. Business impact assessment
4. Urgency level (Critical/High/Medium/Low)

Keep the response focused and actionable, maximum 150 words.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert SRE providing alert analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"❌ OpenAI API error: {e}")
            return f"AI analysis temporarily unavailable. Alert: {alert_name} with {severity} severity requires attention."

    def _generate_fix_suggestions(self, alert_name: str, severity: str, context: str) -> List[str]:
        """Generate specific fix suggestions based on alert type"""
        if not self.client:
            return self._mock_fix_suggestions(alert_name)
        
        prompt = f"""
As an SRE, provide specific remediation steps for this alert:

Alert: {alert_name}
Severity: {severity}
Context: {context}

List 3-5 specific actionable steps to resolve this issue, prioritized by impact.
Format as numbered list, be specific and practical.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert SRE providing remediation steps."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.2
            )
            
            suggestions = response.choices[0].message.content.strip()
            # Parse numbered list into array
            return [line.strip() for line in suggestions.split('\n') if line.strip() and any(char.isdigit() for char in line[:3])]
            
        except Exception as e:
            print(f"❌ Error generating suggestions: {e}")
            return self._mock_fix_suggestions(alert_name)

    def _assess_impact(self, alert_name: str, severity: str) -> str:
        """Assess business impact of the alert"""
        impact_mapping = {
            'critical': 'HIGH - Service disruption affecting users',
            'warning': 'MEDIUM - Performance degradation possible',
            'info': 'LOW - Monitoring notification'
        }
        
        base_impact = impact_mapping.get(severity.lower(), 'MEDIUM - Impact assessment needed')
        
        # Enhanced impact based on alert type
        if 'down' in alert_name.lower() or 'unreachable' in alert_name.lower():
            return 'CRITICAL - Service unavailable to users'
        elif 'high' in alert_name.lower() and 'request' in alert_name.lower():
            return 'HIGH - Performance issues affecting user experience'
        elif 'cpu' in alert_name.lower() or 'memory' in alert_name.lower():
            return 'MEDIUM - Resource constraints may impact performance'
        
        return base_impact

    def _calculate_priority(self, alert_name: str, severity: str) -> int:
        """Calculate priority score (1-5, 5 being highest)"""
        severity_scores = {'critical': 5, 'high': 4, 'warning': 3, 'info': 2}
        base_score = severity_scores.get(severity.lower(), 3)
        
        # Adjust based on alert type
        if 'down' in alert_name.lower():
            return 5
        elif 'high' in alert_name.lower():
            return min(5, base_score + 1)
        
        return base_score

    def _mock_analysis(self, alert_data: Dict) -> Dict:
        """Provide mock analysis when OpenAI is not available"""
        alert_name = alert_data.get('commonLabels', {}).get('alertname', 'Unknown')
        severity = alert_data.get('commonLabels', {}).get('severity', 'unknown')
        
        return {
            'ai_analysis': f"""
🤖 AI Analysis (Demo Mode):

Alert '{alert_name}' with {severity} severity indicates a system condition requiring attention.

This is a demonstration response. To enable full AI analysis:
1. Set OPENAI_API_KEY environment variable
2. Restart the bot

The alert monitoring system is working correctly and ready for AI enhancement.
""".strip(),
            'suggested_actions': self._mock_fix_suggestions(alert_name),
            'impact_assessment': self._assess_impact(alert_name, severity),
            'priority_level': self._calculate_priority(alert_name, severity)
        }

    def _mock_fix_suggestions(self, alert_name: str) -> List[str]:
        """Mock fix suggestions for demo purposes"""
        suggestions_map = {
            'HighRequestRate': [
                "1. Check application performance metrics and identify bottlenecks",
                "2. Scale application instances horizontally if needed",
                "3. Review recent deployments for performance regressions",
                "4. Implement rate limiting if traffic is unusual",
                "5. Monitor database query performance for slow queries"
            ],
            'ServiceDown': [
                "1. Check service health endpoints and logs immediately",
                "2. Verify network connectivity to the service",
                "3. Restart service if it's in a failed state",
                "4. Check resource availability (CPU, memory, disk)",
                "5. Escalate to on-call engineer if issue persists"
            ],
            'HighCPUUsage': [
                "1. Identify processes consuming high CPU using top/htop",
                "2. Check for resource-intensive operations or runaway processes",
                "3. Scale resources vertically or horizontally",
                "4. Review application code for CPU-intensive operations",
                "5. Consider implementing caching to reduce computational load"
            ]
        }
        
        return suggestions_map.get(alert_name, [
            "1. Review alert details and service logs",
            "2. Check system resources and dependencies",
            "3. Verify service configuration and connectivity",
            "4. Escalate if issue impact is severe"
        ])



@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    return LLMService()
