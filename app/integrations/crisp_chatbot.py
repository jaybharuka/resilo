"""
Enhanced Chatbot with Crisp, Actionable Responses
Optimized for quick problem resolution and clear communication
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

class CrispChatbot:
    def __init__(self):
        # Configure Gemini with optimized prompts
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-pro')
        
        # Response templates for different scenarios
        self.response_templates = {
            'system_normal': "✅ {metric} at {value}%. System healthy.",
            'system_warning': "⚠️ {metric} at {value}%. Action needed: {action}",
            'system_critical': "🚨 {metric} at {value}%. URGENT: {action}",
            'quick_fix': "💡 Quick fix: {solution}",
            'next_steps': "📋 Next: {steps}"
        }
        
        # Action mappings for common issues
        self.quick_actions = {
            'high_cpu': [
                "Check Task Manager for CPU-heavy processes",
                "Close unnecessary applications",
                "Restart if CPU stays >90% for 5+ minutes"
            ],
            'high_memory': [
                "Close browser tabs and unused apps",
                "Restart memory-intensive applications", 
                "Check for memory leaks in Task Manager"
            ],
            'disk_full': [
                "Run Disk Cleanup utility",
                "Empty Recycle Bin",
                "Move large files to external storage"
            ],
            'network_slow': [
                "Check network speed at speedtest.net",
                "Restart router/modem",
                "Close bandwidth-heavy applications"
            ]
        }

    def get_crisp_response(self, message: str, system_context: Dict) -> str:
        """Generate crisp, actionable responses"""
        
        # Check for specific system queries first
        message_lower = message.lower()
        
        # Direct system status queries
        if any(word in message_lower for word in ['cpu', 'processor']):
            return self._handle_cpu_query(system_context)
        elif any(word in message_lower for word in ['memory', 'ram']):
            return self._handle_memory_query(system_context)
        elif any(word in message_lower for word in ['disk', 'storage']):
            return self._handle_disk_query(system_context)
        elif any(word in message_lower for word in ['network', 'internet']):
            return self._handle_network_query(system_context)
        elif any(word in message_lower for word in ['temperature', 'temp']):
            return self._handle_temperature_query(system_context)
        
        # Problem-solving queries
        elif any(word in message_lower for word in ['slow', 'lag', 'performance']):
            return self._handle_performance_issue(system_context)
        elif any(word in message_lower for word in ['fix', 'solve', 'help']):
            return self._handle_fix_request(message, system_context)
        
        # Casual conversation
        elif any(word in message_lower for word in ['hello', 'hi', 'hey']):
            return f"👋 Hi! System status: {system_context.get('status', 'unknown')}. What can I help with?"
        
        # Use Gemini for complex queries with optimized prompt
        else:
            return self._get_gemini_response(message, system_context)

    def _handle_cpu_query(self, context: Dict) -> str:
        cpu = context.get('cpu', 0)
        if cpu > 85:
            actions = " • ".join(self.quick_actions['high_cpu'][:2])
            return f"🚨 CPU: {cpu}%\n• {actions}"
        elif cpu > 70:
            return f"⚠️ CPU: {cpu}%. Monitor for increases."
        else:
            return f"✅ CPU: {cpu}%. Running smoothly."

    def _handle_memory_query(self, context: Dict) -> str:
        memory = context.get('memory', 0)
        if memory > 85:
            actions = " • ".join(self.quick_actions['high_memory'][:2]) 
            return f"🚨 RAM: {memory}%\n• {actions}"
        elif memory > 75:
            return f"⚠️ RAM: {memory}%. Close unused apps."
        else:
            return f"✅ RAM: {memory}%. Good levels."

    def _handle_disk_query(self, context: Dict) -> str:
        disk = context.get('disk', 0)
        if disk > 90:
            actions = " • ".join(self.quick_actions['disk_full'][:2])
            return f"🚨 Disk: {disk}%\n• {actions}"
        elif disk > 80:
            return f"⚠️ Disk: {disk}%. Clean up soon."
        else:
            return f"✅ Disk: {disk}%. Space available."

    def _handle_network_query(self, context: Dict) -> str:
        net_in = context.get('network_in', 0)
        if net_in > 50:
            return f"📊 Network: {net_in:.1f} MB/s. High activity detected."
        else:
            return f"📊 Network: {net_in:.1f} MB/s. Normal usage."

    def _handle_temperature_query(self, context: Dict) -> str:
        temp = context.get('temperature', 0)
        if temp > 75:
            return f"🌡️ Temp: {temp}°C. Check cooling system."
        elif temp > 65:
            return f"🌡️ Temp: {temp}°C. Slightly warm."
        else:
            return f"❄️ Temp: {temp}°C. Cool and stable."

    def _handle_performance_issue(self, context: Dict) -> str:
        issues = []
        if context.get('cpu', 0) > 80:
            issues.append("High CPU")
        if context.get('memory', 0) > 80:
            issues.append("High RAM")
        if context.get('disk', 0) > 85:
            issues.append("Low disk space")
        
        if issues:
            return f"🔍 Found: {', '.join(issues)}. Check Task Manager."
        else:
            return "✅ All metrics normal. Try restarting specific apps."

    def _handle_fix_request(self, message: str, context: Dict) -> str:
        # Extract what needs fixing
        if 'cpu' in message.lower():
            return "🔧 CPU Fix:\n• " + "\n• ".join(self.quick_actions['high_cpu'])
        elif 'memory' in message.lower() or 'ram' in message.lower():
            return "🔧 Memory Fix:\n• " + "\n• ".join(self.quick_actions['high_memory'])
        else:
            return "🔧 General fixes:\n• Restart apps\n• Check Task Manager\n• Reboot if needed"

    def _get_gemini_response(self, message: str, context: Dict) -> str:
        """Use Gemini with optimized prompt for crisp responses"""
        try:
            prompt = f"""
You are a system admin assistant. Give CRISP, SHORT responses (max 50 words).

Current system:
- CPU: {context.get('cpu', 0)}%
- RAM: {context.get('memory', 0)}%  
- Disk: {context.get('disk', 0)}%
- Status: {context.get('status', 'unknown')}

User question: {message}

Respond with:
1. One line status/answer
2. One specific action (if needed)
3. Use emojis for clarity

Be direct and actionable.
"""

            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            return f"🤖 Processing... Current system: {context.get('status', 'unknown')}. What specific help do you need?"

    def get_autonomous_suggestion(self, context: Dict) -> Optional[Dict]:
        """Suggest autonomous actions for system issues"""
        suggestions = []
        
        cpu = context.get('cpu', 0)
        memory = context.get('memory', 0)
        disk = context.get('disk', 0)
        
        if cpu > 90:
            suggestions.append({
                'action': 'kill_high_cpu_process',
                'reason': f'CPU at {cpu}% - performance impact',
                'urgency': 'high',
                'auto_approve': False
            })
        
        if memory > 90:
            suggestions.append({
                'action': 'clear_memory_cache',
                'reason': f'Memory at {memory}% - system stability risk', 
                'urgency': 'high',
                'auto_approve': False
            })
        
        if disk > 95:
            suggestions.append({
                'action': 'clear_temp_files',
                'reason': f'Disk at {disk}% - critical space needed',
                'urgency': 'critical', 
                'auto_approve': True  # Safe action
            })
        
        return suggestions[0] if suggestions else None

# Integration with existing API
def enhanced_chat_handler(message: str, system_context: Dict) -> Dict:
    """Enhanced chat handler with crisp responses"""
    chatbot = CrispChatbot()
    
    response = chatbot.get_crisp_response(message, system_context)
    autonomous_suggestion = chatbot.get_autonomous_suggestion(system_context)
    
    return {
        'response': response,
        'timestamp': datetime.now().isoformat(),
        'source': 'crisp_ai',
        'system_context': system_context,
        'autonomous_suggestion': autonomous_suggestion
    }