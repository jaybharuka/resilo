"""
Enhanced AI Response System for AIOps Chatbot
Advanced natural language understanding and intelligent analysis
"""

import json
import re
from datetime import datetime
import google.generativeai as genai

class EnhancedAIAnalyzer:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.conversation_context = []
        self.system_analysis_cache = {}
        
    def analyze_user_intent_advanced(self, user_message, system_data):
        """Advanced intent analysis using AI"""
        
        # Create detailed context for AI understanding
        context_prompt = f"""
You are an expert system administrator AI. Analyze this user query and system data to understand exactly what the user wants.

User Query: "{user_message}"

Current System Status:
- CPU Usage: {system_data.get('cpu', {}).get('usage_percent', 0):.1f}%
- Memory Usage: {system_data.get('memory', {}).get('percent', 0):.1f}%
- Disk Usage: {system_data.get('disk', {}).get('percent', 0):.1f}%
- Recent Issues: {len(system_data.get('recent_events', []))} detected

Top Resource Consumers:
{self._format_top_processes(system_data.get('top_processes', []))}

Based on this data, identify:
1. The user's specific intent (what they want to know)
2. Which system metrics are problematic (above normal thresholds)
3. The most relevant information to address their question

Respond with a JSON object:
{{
    "user_intent": "specific intent description",
    "problematic_areas": ["list of actual issues"],
    "priority_response": "what to focus the response on",
    "requires_deep_analysis": true/false
}}
"""
        
        try:
            response = self.model.generate_content(context_prompt)
            intent_analysis = json.loads(response.text)
            return intent_analysis
        except Exception as e:
            # Fallback to rule-based analysis
            return self._fallback_intent_analysis(user_message, system_data)
    
    def generate_intelligent_response(self, user_message, system_data, conversation_history=None):
        """Generate highly contextual and intelligent responses"""
        
        # First, understand what the user is actually asking
        intent_analysis = self.analyze_user_intent_advanced(user_message, system_data)
        
        # Build comprehensive context for response generation
        response_prompt = f"""
You are an expert AIOps system administrator providing personalized technical support.

User Question: "{user_message}"

Intent Analysis: {json.dumps(intent_analysis, indent=2)}

Detailed System Analysis:
{self._create_detailed_system_context(system_data)}

Previous Conversation Context:
{self._format_conversation_history(conversation_history or [])}

Instructions:
1. DIRECTLY answer the user's specific question - don't give generic overviews
2. If they ask "what needs attention", identify the SPECIFIC problematic metrics
3. If they ask about performance, analyze the ROOT CAUSE of issues
4. If they ask about errors, identify ACTUAL problems, not just list metrics
5. Provide ACTIONABLE solutions, not just observations
6. Use the actual system data provided - be specific with numbers
7. Format response in HTML with proper emphasis and structure

Response Requirements:
- Be conversational and helpful, not robotic
- Focus on what the user actually asked about
- Provide specific recommendations based on real data
- If multiple issues exist, prioritize them by severity
- Include relevant process names and specific metrics when applicable

Generate a response that directly addresses their question with intelligent analysis:
"""
        
        try:
            response = self.model.generate_content(response_prompt)
            
            # Store conversation for context
            self.conversation_context.append({
                'user_message': user_message,
                'ai_response': response.text,
                'timestamp': datetime.now().isoformat(),
                'system_state': system_data
            })
            
            # Keep only last 5 exchanges for context
            if len(self.conversation_context) > 5:
                self.conversation_context = self.conversation_context[-5:]
            
            return response.text
            
        except Exception as e:
            return self._generate_enhanced_fallback(user_message, system_data, intent_analysis)
    
    def _create_detailed_system_context(self, system_data):
        """Create comprehensive system context for AI"""
        
        context = []
        
        # CPU Analysis
        cpu_data = system_data.get('cpu', {})
        cpu_usage = cpu_data.get('usage_percent', 0)
        context.append(f"CPU: {cpu_usage:.1f}% usage ({'NORMAL' if cpu_usage < 70 else 'HIGH' if cpu_usage < 90 else 'CRITICAL'})")
        
        # Memory Analysis
        memory_data = system_data.get('memory', {})
        memory_usage = memory_data.get('percent', 0)
        memory_used = memory_data.get('used_gb', 0)
        memory_total = memory_data.get('total_gb', 0)
        context.append(f"Memory: {memory_usage:.1f}% used ({memory_used:.1f}GB / {memory_total:.1f}GB) - {'NORMAL' if memory_usage < 70 else 'HIGH' if memory_usage < 85 else 'CRITICAL'}")
        
        # Disk Analysis
        disk_data = system_data.get('disk', {})
        disk_usage = disk_data.get('percent', 0)
        disk_free = disk_data.get('free_gb', 0)
        context.append(f"Disk: {disk_usage:.1f}% used ({disk_free:.1f}GB free) - {'NORMAL' if disk_usage < 80 else 'HIGH' if disk_usage < 90 else 'CRITICAL'}")
        
        # Process Analysis
        top_processes = system_data.get('top_processes', [])[:5]
        if top_processes:
            context.append("Top Resource Consumers:")
            for proc in top_processes:
                context.append(f"  - {proc.get('name', 'Unknown')}: CPU {proc.get('cpu_percent', 0):.1f}%, Memory {proc.get('memory_percent', 0):.1f}%")
        
        # Recent Events
        events = system_data.get('recent_events', [])
        if events:
            context.append("Recent System Issues:")
            for event in events[:3]:
                context.append(f"  - {event.get('type', 'Unknown')}: {event.get('message', 'No details')}")
        
        return "\n".join(context)
    
    def _format_top_processes(self, processes):
        """Format process list for AI context"""
        if not processes:
            return "No high-resource processes detected"
        
        formatted = []
        for proc in processes[:5]:
            formatted.append(f"- {proc.get('name', 'Unknown')}: CPU {proc.get('cpu_percent', 0):.1f}%, RAM {proc.get('memory_percent', 0):.1f}%")
        
        return "\n".join(formatted)
    
    def _format_conversation_history(self, history):
        """Format conversation history for context"""
        if not history:
            return "No previous conversation"
        
        formatted = []
        for exchange in history[-3:]:  # Last 3 exchanges
            formatted.append(f"User: {exchange.get('user_message', '')}")
            formatted.append(f"AI: {exchange.get('ai_response', '')[:100]}...")
        
        return "\n".join(formatted)
    
    def _fallback_intent_analysis(self, user_message, system_data):
        """Fallback intent analysis when AI fails"""
        
        message_lower = user_message.lower()
        problematic_areas = []
        
        # Check system thresholds
        memory_usage = system_data.get('memory', {}).get('percent', 0)
        cpu_usage = system_data.get('cpu', {}).get('usage_percent', 0)
        disk_usage = system_data.get('disk', {}).get('percent', 0)
        
        if memory_usage > 80:
            problematic_areas.append(f"High memory usage ({memory_usage:.1f}%)")
        if cpu_usage > 70:
            problematic_areas.append(f"High CPU usage ({cpu_usage:.1f}%)")
        if disk_usage > 85:
            problematic_areas.append(f"Low disk space ({disk_usage:.1f}% used)")
        
        # Determine intent
        if any(word in message_lower for word in ['attention', 'problem', 'issue', 'wrong', 'fix']):
            intent = "identify_problems"
            priority = "problematic_areas"
        elif any(word in message_lower for word in ['performance', 'slow', 'speed', 'fast']):
            intent = "performance_analysis"
            priority = "performance_bottlenecks"
        else:
            intent = "general_inquiry"
            priority = "system_overview"
        
        return {
            "user_intent": intent,
            "problematic_areas": problematic_areas,
            "priority_response": priority,
            "requires_deep_analysis": len(problematic_areas) > 0
        }
    
    def _generate_enhanced_fallback(self, user_message, system_data, intent_analysis):
        """Enhanced fallback response when AI is unavailable"""
        
        message_lower = user_message.lower()
        problematic_areas = intent_analysis.get('problematic_areas', [])
        
        if any(word in message_lower for word in ['attention', 'problem', 'issue', 'wrong']):
            if problematic_areas:
                response = f"🚨 <strong>Areas Requiring Attention:</strong><br><br>"
                for i, area in enumerate(problematic_areas, 1):
                    response += f"{i}. <strong>{area}</strong><br>"
                
                response += "<br><strong>Immediate Actions:</strong><br>"
                if "memory" in str(problematic_areas).lower():
                    response += "• Close unnecessary applications to free up RAM<br>"
                if "cpu" in str(problematic_areas).lower():
                    response += "• Identify and close CPU-intensive processes<br>"
                if "disk" in str(problematic_areas).lower():
                    response += "• Clean up temporary files and unused programs<br>"
                
                return response
            else:
                return "✅ <strong>Good News!</strong><br><br>I've analyzed your system and found no areas requiring immediate attention. All metrics are within normal ranges:<br>• CPU usage is healthy<br>• Memory usage is acceptable<br>• Disk space is adequate<br><br>Your system is running smoothly!"
        
        # Default to more intelligent system overview
        memory_usage = system_data.get('memory', {}).get('percent', 0)
        cpu_usage = system_data.get('cpu', {}).get('usage_percent', 0)
        disk_usage = system_data.get('disk', {}).get('percent', 0)
        
        response = f"🤖 <strong>System Analysis Results:</strong><br><br>"
        
        if problematic_areas:
            response += f"⚠️ <strong>Found {len(problematic_areas)} issue(s) requiring attention:</strong><br>"
            for area in problematic_areas:
                response += f"• {area}<br>"
            response += "<br>Would you like me to provide detailed troubleshooting steps for any of these issues?"
        else:
            response += "✅ <strong>System Status: Healthy</strong><br>"
            response += f"• CPU: {cpu_usage:.1f}% (Normal)<br>"
            response += f"• Memory: {memory_usage:.1f}% ({'Normal' if memory_usage < 70 else 'Elevated'})<br>"
            response += f"• Disk: {disk_usage:.1f}% used (Adequate)<br>"
        
        return response

# Global instance for use in chatbot
enhanced_ai = None

def initialize_enhanced_ai(api_key):
    """Initialize the enhanced AI analyzer"""
    global enhanced_ai
    enhanced_ai = EnhancedAIAnalyzer(api_key)
    return enhanced_ai