from openai import OpenAI
import os
from typing import Dict, List, Optional
import json
from functools import lru_cache

class GeminiAIAssistant:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize AI Assistant with API key"""
        self.api_key = api_key or os.getenv('AI_API_KEY') or os.getenv('NVIDIA_API_KEY')
        if not self.api_key:
            raise ValueError("AI API key not configured. Set AI_API_KEY or NVIDIA_API_KEY.")

        # Configure OpenAI Client for Nvidia endpoint
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.api_key
        )
        
        # System context for AIOps
        self.system_context = """
        You are an advanced AIOps (Artificial Intelligence for IT Operations) assistant. 
        Your role is to help users monitor, analyze, and optimize their IT infrastructure.
        
        Key capabilities:
        - System monitoring and performance analysis
        - Predictive analytics for potential issues
        - Troubleshooting guidance
        - Best practices recommendations
        - Security monitoring insights
        - Resource optimization suggestions
        
        Always be helpful, accurate, and professional. Provide actionable insights
        and explain technical concepts clearly. Use emojis appropriately to make
        responses engaging but professional.
        """
    
    def enhance_with_system_data(self, user_message: str, system_data: Dict) -> str:
        """Enhance user query with current system data context"""
        context = f"""
        Current System Status:
        - CPU Usage: {system_data.get('cpu', 0):.1f}%
        - Memory Usage: {system_data.get('memory', 0):.1f}%
        - Disk Usage: {system_data.get('disk', 0):.1f}%
        - Network In: {system_data.get('network_in', 0):.1f} Mbps
        - Network Out: {system_data.get('network_out', 0):.1f} Mbps
        - Temperature: {system_data.get('temperature', 0):.1f}°C
        - System Status: {system_data.get('status', 'unknown')}
        - Uptime: {system_data.get('uptime', 'unknown')}
        - Active Processes: {system_data.get('active_processes', 0)}
        
        User Query: {user_message}
        
        Based on the current system metrics above, please provide a helpful response.
        """
        return context
    
    async def chat(self, message: str, system_data: Optional[Dict] = None, 
                   conversation_history: Optional[List[Dict]] = None) -> Dict:
        """
        Chat with Gemini AI with AIOps context
        
        Args:
            message: User's message
            system_data: Current system metrics
            conversation_history: Previous conversation for context
        
        Returns:
            Dict with response, metadata, and suggestions
        """
        try:
            # Prepare the full prompt with context
            messages = [{"role": "system", "content": self.system_context}]
            
            # Add conversation history if available
            if conversation_history:
                for msg in conversation_history[-5:]:
                    role = 'user' if msg.get('role') in ['user', 'User'] else 'assistant'
                    messages.append({"role": role, "content": msg.get('content', '')})
            
            if system_data:
                messages.append({"role": "user", "content": self.enhance_with_system_data(message, system_data)})
            else:
                messages.append({"role": "user", "content": message})
            
            # Generate response
            completion = self.client.chat.completions.create(
                model="abacusai/dracarys-llama-3.1-70b-instruct",
                messages=messages,
                temperature=1,
                top_p=1,
                max_tokens=4096,
                stream=False
            )
            
            # Extract and format response
            ai_response = completion.choices[0].message.content if completion.choices else "I apologize, but I couldn't generate a response at this moment."
            
            # Generate suggestions based on system data
            suggestions = self._generate_suggestions(system_data) if system_data else []
            
            return {
                "response": ai_response,
                "suggestions": suggestions,
                "system_analysis": self._analyze_system_health(system_data) if system_data else None,
                "timestamp": None,  # Will be added by the API
                "source": "gemini_ai_assistant",
                "confidence": 0.95,
                "personalized": True
            }
            
        except Exception as e:
            print(f"Error in Gemini AI chat: {e}")
            return {
                "response": f"I'm experiencing some technical difficulties. {self._get_fallback_response(message, system_data)}",
                "suggestions": [],
                "system_analysis": None,
                "timestamp": None,
                "source": "gemini_ai_assistant_fallback",
                "confidence": 0.3,
                "personalized": False,
                "error": str(e)
            }
    
    def _analyze_system_health(self, system_data: Dict) -> Dict:
        """Analyze system health and provide insights"""
        if not system_data:
            return None
        
        health_score = 100
        issues = []
        recommendations = []
        
        # CPU Analysis
        cpu = system_data.get('cpu', 0)
        if cpu > 90:
            health_score -= 30
            issues.append("🔴 Critical CPU usage")
            recommendations.append("Consider checking for resource-intensive processes")
        elif cpu > 75:
            health_score -= 15
            issues.append("🟡 High CPU usage")
            recommendations.append("Monitor CPU trends and optimize if needed")
        
        # Memory Analysis
        memory = system_data.get('memory', 0)
        if memory > 90:
            health_score -= 25
            issues.append("🔴 Critical memory usage")
            recommendations.append("Free up memory or consider adding more RAM")
        elif memory > 80:
            health_score -= 10
            issues.append("🟡 High memory usage")
            recommendations.append("Monitor memory usage patterns")
        
        # Disk Analysis
        disk = system_data.get('disk', 0)
        if disk > 95:
            health_score -= 20
            issues.append("🔴 Critical disk space")
            recommendations.append("Urgent: Free up disk space immediately")
        elif disk > 85:
            health_score -= 10
            issues.append("🟡 Low disk space")
            recommendations.append("Clean up unnecessary files")
        
        # Temperature Analysis
        temp = system_data.get('temperature', 0)
        if temp > 80:
            health_score -= 20
            issues.append("🔴 High system temperature")
            recommendations.append("Check cooling system and clean dust")
        elif temp > 70:
            health_score -= 10
            issues.append("🟡 Elevated temperature")
            recommendations.append("Monitor temperature trends")
        
        # Overall status
        if health_score >= 90:
            status = "Excellent"
            color = "🟢"
        elif health_score >= 75:
            status = "Good"
            color = "🟡"
        elif health_score >= 60:
            status = "Fair"
            color = "🟠"
        else:
            status = "Poor"
            color = "🔴"
        
        return {
            "health_score": max(0, health_score),
            "status": f"{color} {status}",
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _generate_suggestions(self, system_data: Dict) -> List[str]:
        """Generate contextual suggestions based on system state"""
        if not system_data:
            return [
                "💡 Ask me about system performance optimization",
                "🔍 Request a detailed system health analysis",
                "📊 Get recommendations for monitoring best practices"
            ]
        
        suggestions = []
        cpu = system_data.get('cpu', 0)
        memory = system_data.get('memory', 0)
        disk = system_data.get('disk', 0)
        
        if cpu > 70:
            suggestions.append("🔍 Analyze high CPU usage processes")
        if memory > 75:
            suggestions.append("💾 Check memory optimization options")
        if disk > 80:
            suggestions.append("🗂️ Get disk cleanup recommendations")
        
        # Add general suggestions if no specific issues
        if len(suggestions) == 0:
            suggestions.extend([
                "📈 Show performance optimization tips",
                "🔧 Get maintenance best practices",
                "⚡ Analyze system efficiency"
            ])
        
        return suggestions[:3]  # Limit to 3 suggestions
    
    def _get_fallback_response(self, message: str, system_data: Optional[Dict]) -> str:
        """Provide fallback response when AI is unavailable"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['cpu', 'processor', 'performance']):
            if system_data:
                return f"Your CPU is currently at {system_data.get('cpu', 0):.1f}%. I'd love to give you more detailed analysis, but I'm having connectivity issues right now."
            return "I can help you with CPU performance analysis. Please try again in a moment."
        
        if any(word in message_lower for word in ['memory', 'ram']):
            if system_data:
                return f"Memory usage is at {system_data.get('memory', 0):.1f}%. I'll provide better insights once my connection is restored."
            return "I can analyze memory usage patterns. Please try again shortly."
        
        return "I'm here to help with your AIOps needs. Please try again in a moment while I reconnect."

@lru_cache(maxsize=1)
def _create_gemini_assistant() -> GeminiAIAssistant:
    """Create and cache a single assistant instance per process."""
    return GeminiAIAssistant()

def get_gemini_assistant() -> GeminiAIAssistant:
    """Get or create Gemini AI Assistant instance"""
    try:
        return _create_gemini_assistant()
    except ValueError as e:
        print(f"Gemini AI not available: {e}")
        return None