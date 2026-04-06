"""
Enhanced AIOps Chatbot with Microsoft Teams Integration
Combines Google Gemini Pro, Hugging Face AI, and Teams notifications
"""

import asyncio
import json
import logging
import os
import platform
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

# System monitoring
import psutil
# AI integrations
from huggingface_ai_integration import (enhance_response_with_ai,
                                        initialize_huggingface_ai)
from teams_integration import (MessageType, MicrosoftTeamsIntegrator,
                               TeamsAlert, TeamsCredentials, send_aiops_alert,
                               send_system_status)

# Google Gemini (keep existing functionality)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Google Gemini not available. Using Hugging Face AI only.")

class TeamsEnhancedAIOpsBot:
    """
    Advanced AIOps chatbot with triple AI engines:
    - Google Gemini Pro for general conversations
    - Hugging Face models for specialized AI tasks  
    - Microsoft Teams for notifications and collaboration
    """
    
    def __init__(self):
        self.bot_name = "AIOps Assistant Pro"
        self.version = "4.0 - Teams Integrated"
        
        # Initialize AI engines
        self.gemini_model = None
        self.huggingface_ai = None
        self.teams_integrator = None
        
        # Teams configuration
        self.teams_credentials = TeamsCredentials(
            tenant_id=os.getenv('TEAMS_TENANT_ID', ''),
            client_id=os.getenv('TEAMS_CLIENT_ID', ''),
            client_secret=os.getenv('TEAMS_CLIENT_SECRET', ''),
            webhook_url=os.getenv('TEAMS_WEBHOOK_URL', '')
        )
        
        # System monitoring
        self.system_data = {}
        self.alert_thresholds = {
            'cpu_critical': 90,
            'cpu_warning': 75,
            'memory_critical': 95,
            'memory_warning': 85,
            'disk_critical': 95,
            'disk_warning': 90
        }
        
        # Chat history with AI enhancements
        self.chat_history = []
        self.teams_notifications_enabled = bool(self.teams_credentials.webhook_url)
        
        print(f"🚀 Initializing {self.bot_name} v{self.version}")
        self.initialize_ai_engines()
        self.update_system_data()
    
    def initialize_ai_engines(self):
        """Initialize all AI engines"""
        try:
            # Initialize Hugging Face AI (always available)
            print("🤗 Initializing Hugging Face AI...")
            self.huggingface_ai = initialize_huggingface_ai()
            
            # Initialize Google Gemini if available
            if GEMINI_AVAILABLE:
                print("🧠 Initializing Google Gemini Pro...")
                gemini_api_key = os.getenv('GEMINI_API_KEY')
                if gemini_api_key:
                    genai.configure(api_key=gemini_api_key)
                    self.gemini_model = genai.GenerativeModel('gemini-pro')
                    print("✅ Google Gemini Pro initialized")
                else:
                    print("⚠️ GEMINI_API_KEY not found in environment variables")
            
            # Initialize Teams integration
            if self.teams_notifications_enabled:
                print("📢 Initializing Microsoft Teams integration...")
                print("✅ Teams notifications enabled")
            else:
                print("⚠️ Teams integration disabled (no webhook URL configured)")
            
            print("✅ AI engines initialization complete!")
            
        except Exception as e:
            print(f"❌ Error initializing AI engines: {e}")
            traceback.print_exc()
    
    def update_system_data(self):
        """Update current system monitoring data"""
        try:
            # CPU Information
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory Information
            memory = psutil.virtual_memory()
            
            # Disk Information
            disk = psutil.disk_usage('/')
            
            # Network Information
            network = psutil.net_io_counters()
            
            # Process Information
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Top 5 CPU-intensive processes
            top_processes = sorted(processes, key=lambda x: x['cpu_percent'] or 0, reverse=True)[:5]
            
            self.system_data = {
                "timestamp": datetime.now().isoformat(),
                "cpu": {
                    "usage_percent": cpu_percent,
                    "count": cpu_count,
                    "frequency": cpu_freq.current if cpu_freq else "Unknown"
                },
                "memory": {
                    "total": round(memory.total / (1024**3), 2),  # GB
                    "available": round(memory.available / (1024**3), 2),  # GB
                    "percent": memory.percent,
                    "used": round(memory.used / (1024**3), 2)  # GB
                },
                "disk": {
                    "total": round(disk.total / (1024**3), 2),  # GB
                    "used": round(disk.used / (1024**3), 2),  # GB
                    "free": round(disk.free / (1024**3), 2),  # GB
                    "percent": round((disk.used / disk.total) * 100, 1)
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                },
                "top_processes": top_processes,
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine()
                }
            }
            
        except Exception as e:
            print(f"Error updating system data: {e}")
            self.system_data = {"error": "Unable to collect system data", "timestamp": datetime.now().isoformat()}
    
    async def check_and_send_alerts(self):
        """Check system metrics and send Teams alerts if needed"""
        if not self.teams_notifications_enabled:
            return
        
        try:
            cpu_usage = self.system_data.get('cpu', {}).get('usage_percent', 0)
            memory_usage = self.system_data.get('memory', {}).get('percent', 0)
            disk_usage = self.system_data.get('disk', {}).get('percent', 0)
            
            # Check for critical alerts
            if cpu_usage >= self.alert_thresholds['cpu_critical']:
                await self.send_teams_alert(
                    title="🚨 CRITICAL: High CPU Usage",
                    message=f"CPU usage is at {cpu_usage}%! Immediate attention required.",
                    alert_type=MessageType.CRITICAL
                )
            elif cpu_usage >= self.alert_thresholds['cpu_warning']:
                await self.send_teams_alert(
                    title="⚠️ WARNING: Elevated CPU Usage",
                    message=f"CPU usage is at {cpu_usage}%. Monitor closely.",
                    alert_type=MessageType.WARNING
                )
            
            if memory_usage >= self.alert_thresholds['memory_critical']:
                await self.send_teams_alert(
                    title="🚨 CRITICAL: High Memory Usage",
                    message=f"Memory usage is at {memory_usage}%! System may become unstable.",
                    alert_type=MessageType.CRITICAL
                )
            elif memory_usage >= self.alert_thresholds['memory_warning']:
                await self.send_teams_alert(
                    title="⚠️ WARNING: High Memory Usage",
                    message=f"Memory usage is at {memory_usage}%. Consider freeing up memory.",
                    alert_type=MessageType.WARNING
                )
            
            if disk_usage >= self.alert_thresholds['disk_critical']:
                await self.send_teams_alert(
                    title="🚨 CRITICAL: Low Disk Space",
                    message=f"Disk usage is at {disk_usage}%! Clean up immediately.",
                    alert_type=MessageType.CRITICAL
                )
            elif disk_usage >= self.alert_thresholds['disk_warning']:
                await self.send_teams_alert(
                    title="⚠️ WARNING: Low Disk Space",
                    message=f"Disk usage is at {disk_usage}%. Consider cleanup.",
                    alert_type=MessageType.WARNING
                )
                
        except Exception as e:
            print(f"Error checking alerts: {e}")
    
    async def send_teams_alert(self, title: str, message: str, alert_type: MessageType = MessageType.INFO):
        """Send alert to Teams"""
        if not self.teams_notifications_enabled:
            print(f"Teams notification (disabled): {title}")
            return False
        
        try:
            # Add system metrics to alert
            enhanced_system_data = {
                'cpu_usage': self.system_data.get('cpu', {}).get('usage_percent', 0),
                'memory_usage': self.system_data.get('memory', {}).get('percent', 0),
                'disk_usage': self.system_data.get('disk', {}).get('percent', 0),
                'timestamp': datetime.now().isoformat(),
                'platform': self.system_data.get('platform', {}).get('system', 'Unknown')
            }
            
            # Create alert with enhanced data
            alert = TeamsAlert(
                title=title,
                message=message,
                alert_type=alert_type,
                system_data=enhanced_system_data,
                actions=[
                    {'title': '🔍 View Dashboard', 'url': 'http://localhost:5000'},
                    {'title': '📊 System Metrics', 'url': 'http://localhost:5000/metrics'}
                ]
            )
            
            # Send via webhook
            async with MicrosoftTeamsIntegrator(self.teams_credentials) as teams:
                success = await teams.send_webhook_message(self.teams_credentials.webhook_url, alert)
                if success:
                    print(f"📢 Teams alert sent: {title}")
                return success
                
        except Exception as e:
            print(f"Teams notification failed: {e}")
            return False
    
    async def send_teams_status_update(self):
        """Send periodic status update to Teams"""
        if not self.teams_notifications_enabled:
            return
        
        try:
            cpu_usage = self.system_data.get('cpu', {}).get('usage_percent', 0)
            memory_usage = self.system_data.get('memory', {}).get('percent', 0)
            disk_usage = self.system_data.get('disk', {}).get('percent', 0)
            
            await send_system_status(
                credentials=self.teams_credentials,
                webhook_url=self.teams_credentials.webhook_url,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                disk_usage=disk_usage
            )
            print("📊 Teams status update sent")
            
        except Exception as e:
            print(f"Teams status update failed: {e}")
    
    def get_base_response_gemini(self, user_message: str) -> str:
        """Get base response from Google Gemini"""
        try:
            if not self.gemini_model:
                return self.get_fallback_response(user_message)
            
            # Create context-aware prompt
            system_context = f"""
You are an AIOps (AI for IT Operations) assistant helping with system monitoring and IT support.

Current System Status:
- CPU Usage: {self.system_data.get('cpu', {}).get('usage_percent', 'Unknown')}%
- Memory Usage: {self.system_data.get('memory', {}).get('percent', 'Unknown')}%
- Disk Usage: {self.system_data.get('disk', {}).get('percent', 'Unknown')}%

Teams Integration: {'Enabled' if self.teams_notifications_enabled else 'Disabled'}

User Message: {user_message}

Provide helpful, technical guidance for IT operations and system monitoring. 
If the user asks about Teams integration, mention that notifications can be sent to Microsoft Teams.
"""
            
            response = self.gemini_model.generate_content(system_context)
            return response.text
            
        except Exception as e:
            print(f"Error with Gemini response: {e}")
            return self.get_fallback_response(user_message)
    
    def get_fallback_response(self, user_message: str) -> str:
        """Fallback response when Gemini is not available"""
        message_lower = user_message.lower()
        
        if any(word in message_lower for word in ['teams', 'notification', 'alert']):
            teams_status = "enabled" if self.teams_notifications_enabled else "disabled"
            return f"Teams integration is currently {teams_status}. I can send system alerts and notifications to Microsoft Teams channels."
        
        elif any(word in message_lower for word in ['cpu', 'processor', 'performance']):
            cpu_usage = self.system_data.get('cpu', {}).get('usage_percent', 'Unknown')
            response = f"Your CPU usage is currently at {cpu_usage}%. I can help you analyze performance issues."
            if self.teams_notifications_enabled:
                response += " I can also send Teams alerts if CPU usage gets too high."
            return response
        
        elif any(word in message_lower for word in ['memory', 'ram']):
            memory_usage = self.system_data.get('memory', {}).get('percent', 'Unknown')
            memory_used = self.system_data.get('memory', {}).get('used', 'Unknown')
            memory_total = self.system_data.get('memory', {}).get('total', 'Unknown')
            response = f"Memory usage: {memory_usage}% ({memory_used}GB / {memory_total}GB). I can help optimize memory usage."
            if self.teams_notifications_enabled:
                response += " Teams alerts are enabled for high memory usage."
            return response
        
        elif any(word in message_lower for word in ['disk', 'storage', 'space']):
            disk_usage = self.system_data.get('disk', {}).get('percent', 'Unknown')
            disk_free = self.system_data.get('disk', {}).get('free', 'Unknown')
            response = f"Disk usage: {disk_usage}% with {disk_free}GB free space. I can help with storage management."
            if self.teams_notifications_enabled:
                response += " You'll get Teams notifications if disk space gets low."
            return response
        
        else:
            base_response = "I'm your AIOps assistant. I can help you monitor system performance, analyze issues, and provide IT support guidance."
            if self.teams_notifications_enabled:
                base_response += " I'm also connected to Microsoft Teams for real-time notifications!"
            return base_response
    
    async def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Main message processing with AI enhancement and Teams integration
        """
        try:
            # Update system data
            self.update_system_data()
            
            # Check for alerts first
            await self.check_and_send_alerts()
            
            # Get base response from Gemini or fallback
            base_response = self.get_base_response_gemini(user_message)
            
            # Enhance with Hugging Face AI
            if self.huggingface_ai:
                print("🤗 Enhancing response with Hugging Face AI...")
                ai_enhancement = enhance_response_with_ai(
                    user_message, 
                    base_response, 
                    self.system_data
                )
                
                # Combine responses
                final_response = ai_enhancement.get('enhanced_response', base_response)
                
                # Add Teams integration info if relevant
                if 'teams' in user_message.lower() or 'notification' in user_message.lower():
                    teams_status = "✅ enabled" if self.teams_notifications_enabled else "❌ disabled"
                    final_response += f"\n\n📢 <strong>Teams Integration:</strong> {teams_status}"
                    if self.teams_notifications_enabled:
                        final_response += "\n   • Real-time system alerts\n   • Performance notifications\n   • Interactive dashboard cards"
                
                # Send Teams notification for critical issues
                sentiment = ai_enhancement.get('sentiment', {})
                issue_classification = ai_enhancement.get('issue_classification', {})
                
                if (sentiment.get('emotion') == 'frustrated' and 
                    issue_classification.get('primary_category') in ['performance problems', 'memory issues']):
                    await self.send_teams_alert(
                        title=f"User Issue: {issue_classification.get('primary_category', 'System Problem')}",
                        message=f"User reported: {user_message[:100]}...",
                        alert_type=MessageType.WARNING
                    )
                
                # Add chat entry with AI analysis
                chat_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user_message": user_message,
                    "base_response": base_response,
                    "enhanced_response": final_response,
                    "ai_analysis": {
                        "sentiment": ai_enhancement.get('sentiment', {}),
                        "issue_classification": ai_enhancement.get('issue_classification', {}),
                        "suggested_actions": ai_enhancement.get('suggested_actions', [])
                    },
                    "system_snapshot": self.system_data,
                    "teams_notification_sent": self.teams_notifications_enabled
                }
                
                self.chat_history.append(chat_entry)
                
                return {
                    "response": final_response,
                    "ai_analysis": chat_entry["ai_analysis"],
                    "system_data": self.system_data,
                    "teams_enabled": self.teams_notifications_enabled,
                    "ai_powered": True
                }
            
            else:
                # Fallback without Hugging Face enhancement
                chat_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user_message": user_message,
                    "response": base_response,
                    "system_snapshot": self.system_data,
                    "teams_enabled": self.teams_notifications_enabled,
                    "ai_powered": False
                }
                
                self.chat_history.append(chat_entry)
                
                return {
                    "response": base_response,
                    "system_data": self.system_data,
                    "teams_enabled": self.teams_notifications_enabled,
                    "ai_powered": False
                }
        
        except Exception as e:
            error_msg = f"I encountered an error while processing your request: {str(e)}"
            print(f"Error in process_message: {e}")
            traceback.print_exc()
            
            return {
                "response": error_msg,
                "error": True,
                "system_data": self.system_data,
                "teams_enabled": self.teams_notifications_enabled
            }
    
    def get_system_summary(self) -> str:
        """Get a comprehensive system summary with AI analysis"""
        try:
            # Basic system summary
            cpu_usage = self.system_data.get('cpu', {}).get('usage_percent', 'Unknown')
            memory_usage = self.system_data.get('memory', {}).get('percent', 'Unknown')
            disk_usage = self.system_data.get('disk', {}).get('percent', 'Unknown')
            
            summary = f"""
🖥️ <strong>System Health Report</strong>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 CPU Usage: {cpu_usage}%
💾 Memory Usage: {memory_usage}%
💿 Disk Usage: {disk_usage}%
📢 Teams Integration: {'✅ Enabled' if self.teams_notifications_enabled else '❌ Disabled'}

"""
            
            # Add AI-powered analysis if available
            if self.huggingface_ai:
                # Analyze overall system health
                system_status = "System performance is good"
                if cpu_usage != 'Unknown' and float(cpu_usage) > 80:
                    system_status = "High CPU usage detected - performance may be impacted"
                elif memory_usage != 'Unknown' and float(memory_usage) > 85:
                    system_status = "High memory usage detected - system may slow down"
                elif disk_usage != 'Unknown' and float(disk_usage) > 90:
                    system_status = "Low disk space - cleanup recommended"
                
                # Use Hugging Face to classify the system state
                ai_analysis = enhance_response_with_ai(
                    system_status,
                    "System analysis complete",
                    self.system_data
                )
                
                summary += f"🤖 <strong>AI Analysis:</strong> {ai_analysis.get('enhanced_response', system_status)}\n\n"
                
                if ai_analysis.get('suggested_actions'):
                    summary += "💡 <strong>Suggested Actions:</strong>\n"
                    for action in ai_analysis['suggested_actions'][:3]:
                        summary += f"   • {action}\n"
            
            if self.teams_notifications_enabled:
                summary += "\n📢 <strong>Teams Features:</strong>\n"
                summary += "   • Real-time system alerts\n"
                summary += "   • Performance threshold notifications\n"
                summary += "   • Interactive dashboard cards\n"
            
            return summary
            
        except Exception as e:
            return f"Error generating system summary: {e}"
    
    def start_interactive_chat(self):
        """Start interactive chat session with Teams integration"""
        print(f"\n{'='*60}")
        print(f"🤖 {self.bot_name} v{self.version}")
        print(f"{'='*60}")
        print("🤗 Enhanced with Hugging Face AI models")
        print("🧠 Powered by Google Gemini Pro")
        if self.teams_notifications_enabled:
            print("📢 Connected to Microsoft Teams")
        else:
            print("⚠️ Teams integration available (configure webhook URL)")
        print("💬 Type 'quit' to exit, 'system' for system summary")
        print("💬 Type 'teams test' to send test notification")
        print(f"{'='*60}\n")
        
        # Show initial system summary
        print(self.get_system_summary())
        
        while True:
            try:
                user_input = input("\n💬 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    # Send goodbye notification to Teams
                    if self.teams_notifications_enabled:
                        asyncio.run(self.send_teams_alert(
                            title="AIOps Bot Session Ended",
                            message="User has ended the AIOps bot session",
                            alert_type=MessageType.INFO
                        ))
                    print("👋 Goodbye! Thanks for using AIOps Assistant!")
                    break
                
                elif user_input.lower() in ['system', 'status', 'summary']:
                    print(self.get_system_summary())
                    continue
                
                elif user_input.lower() == 'teams test':
                    if self.teams_notifications_enabled:
                        print("📢 Sending test notification to Teams...")
                        asyncio.run(self.send_teams_alert(
                            title="Test Notification",
                            message="This is a test message from your AIOps bot!",
                            alert_type=MessageType.SUCCESS
                        ))
                    else:
                        print("❌ Teams integration not configured. Set TEAMS_WEBHOOK_URL environment variable.")
                    continue
                
                elif not user_input:
                    continue
                
                # Process message with AI enhancement and Teams integration
                print("🤖 Analyzing... ", end="", flush=True)
                result = asyncio.run(self.process_message(user_input))
                print("✅")
                
                # Display response
                print(f"\n🤖 AIOps Assistant: {result['response']}")
                
                # Show AI analysis if available
                if result.get('ai_analysis'):
                    ai_analysis = result['ai_analysis']
                    sentiment = ai_analysis.get('sentiment', {})
                    classification = ai_analysis.get('issue_classification', {})
                    
                    print(f"\n📊 <strong>AI Analysis:</strong>")
                    print(f"   🎭 Sentiment: {sentiment.get('sentiment', 'neutral')} ({sentiment.get('emotion', 'calm')})")
                    print(f"   📝 Issue Type: {classification.get('primary_category', 'general')}")
                    
                    if classification.get('suggested_actions'):
                        print(f"   💡 Suggestions: {', '.join(classification['suggested_actions'][:2])}")
                
                # Show Teams status
                if result.get('teams_enabled'):
                    print(f"📢 Teams: Monitoring for alerts")
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye! Thanks for using AIOps Assistant!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                continue

def main():
    """Main function to start the Teams-enhanced chatbot"""
    try:
        # Create and start the Teams-enhanced AIOps bot
        bot = TeamsEnhancedAIOpsBot()
        bot.start_interactive_chat()
        
    except Exception as e:
        print(f"Failed to start AIOps bot: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()