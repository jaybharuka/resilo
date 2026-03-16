"""
Enhanced AIOps Chatbot with Hugging Face AI Integration
Combines Google Gemini Pro with free Hugging Face models for superior performance
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any
import traceback

# System monitoring
import psutil
import platform

# Hugging Face integration
from huggingface_ai_integration import enhance_response_with_ai, initialize_huggingface_ai

# Google Gemini (keep existing functionality)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Google Gemini not available. Using Hugging Face AI only.")

class EnhancedAIOpsBot:
    """
    Advanced AIOps chatbot with dual AI engines:
    - Google Gemini Pro for general conversations
    - Hugging Face models for specialized AI tasks
    """
    
    def __init__(self):
        self.bot_name = "AIOps Assistant"
        self.version = "3.0 - Hugging Face Enhanced"
        
        # Initialize AI engines
        self.gemini_model = None
        self.huggingface_ai = None
        
        # System monitoring
        self.system_data = {}
        
        # Chat history with AI enhancements
        self.chat_history = []
        
        print(f"🚀 Initializing {self.bot_name} v{self.version}")
        self.initialize_ai_engines()
        self.update_system_data()
    
    def initialize_ai_engines(self):
        """Initialize both AI engines"""
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

User Message: {user_message}

Provide helpful, technical guidance for IT operations and system monitoring.
"""
            
            response = self.gemini_model.generate_content(system_context)
            return response.text
            
        except Exception as e:
            print(f"Error with Gemini response: {e}")
            return self.get_fallback_response(user_message)
    
    def get_fallback_response(self, user_message: str) -> str:
        """Fallback response when Gemini is not available"""
        message_lower = user_message.lower()
        
        if any(word in message_lower for word in ['cpu', 'processor', 'performance']):
            cpu_usage = self.system_data.get('cpu', {}).get('usage_percent', 'Unknown')
            return f"Your CPU usage is currently at {cpu_usage}%. I can help you analyze performance issues."
        
        elif any(word in message_lower for word in ['memory', 'ram']):
            memory_usage = self.system_data.get('memory', {}).get('percent', 'Unknown')
            memory_used = self.system_data.get('memory', {}).get('used', 'Unknown')
            memory_total = self.system_data.get('memory', {}).get('total', 'Unknown')
            return f"Memory usage: {memory_usage}% ({memory_used}GB / {memory_total}GB). I can help optimize memory usage."
        
        elif any(word in message_lower for word in ['disk', 'storage', 'space']):
            disk_usage = self.system_data.get('disk', {}).get('percent', 'Unknown')
            disk_free = self.system_data.get('disk', {}).get('free', 'Unknown')
            return f"Disk usage: {disk_usage}% with {disk_free}GB free space. I can help with storage management."
        
        elif any(word in message_lower for word in ['process', 'processes']):
            top_proc = self.system_data.get('top_processes', [])
            if top_proc:
                return f"Top CPU process: {top_proc[0]['name']} ({top_proc[0]['cpu_percent']}% CPU). I can help analyze process performance."
            return "I can help you analyze running processes and their resource usage."
        
        else:
            return "I'm your AIOps assistant. I can help you monitor system performance, analyze issues, and provide IT support guidance."
    
    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Main message processing with dual AI enhancement
        """
        try:
            # Update system data
            self.update_system_data()
            
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
                    "system_snapshot": self.system_data
                }
                
                self.chat_history.append(chat_entry)
                
                return {
                    "response": final_response,
                    "ai_analysis": chat_entry["ai_analysis"],
                    "system_data": self.system_data,
                    "ai_powered": True
                }
            
            else:
                # Fallback without Hugging Face enhancement
                chat_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user_message": user_message,
                    "response": base_response,
                    "system_snapshot": self.system_data,
                    "ai_powered": False
                }
                
                self.chat_history.append(chat_entry)
                
                return {
                    "response": base_response,
                    "system_data": self.system_data,
                    "ai_powered": False
                }
        
        except Exception as e:
            error_msg = f"I encountered an error while processing your request: {str(e)}"
            print(f"Error in process_message: {e}")
            traceback.print_exc()
            
            return {
                "response": error_msg,
                "error": True,
                "system_data": self.system_data
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
            
            return summary
            
        except Exception as e:
            return f"Error generating system summary: {e}"
    
    def start_interactive_chat(self):
        """Start interactive chat session"""
        print(f"\n{'='*60}")
        print(f"🤖 {self.bot_name} v{self.version}")
        print(f"{'='*60}")
        print("🤗 Enhanced with Hugging Face AI models")
        print("🧠 Powered by Google Gemini Pro")
        print("💬 Type 'quit' to exit, 'system' for system summary")
        print(f"{'='*60}\n")
        
        # Show initial system summary
        print(self.get_system_summary())
        
        while True:
            try:
                user_input = input("\n💬 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye! Thanks for using AIOps Assistant!")
                    break
                
                elif user_input.lower() in ['system', 'status', 'summary']:
                    print(self.get_system_summary())
                    continue
                
                elif not user_input:
                    continue
                
                # Process message with AI enhancement
                print("🤖 Analyzing... ", end="", flush=True)
                result = self.process_message(user_input)
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
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye! Thanks for using AIOps Assistant!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                continue

def main():
    """Main function to start the enhanced chatbot"""
    try:
        # Create and start the enhanced AIOps bot
        bot = EnhancedAIOpsBot()
        bot.start_interactive_chat()
        
    except Exception as e:
        print(f"Failed to start AIOps bot: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()