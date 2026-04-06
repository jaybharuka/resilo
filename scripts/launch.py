#!/usr/bin/env python3
"""
AIOps Bot - Quick Launch Script
Choose what you want to run!
"""

import os
import sys
from pathlib import Path


def print_menu():
    """Print the main menu"""
    print("""
🤖 AIOps Bot - Quick Launcher
================================

Choose what you want to run:

🔧 SETUP & CONFIGURATION:
   1. Setup Teams Integration (First time setup)
   2. Check System Requirements

💬 CHATBOTS:
   3. Basic AIOps Chatbot (Gemini Pro)
   4. Enhanced AIOps Chatbot (Gemini + Hugging Face)
   5. Teams-Enabled Chatbot (All AI engines + Teams alerts)

🧪 TESTING & DEMOS:
   6. Test Teams Integration
   7. Full Hackathon Demo (All features showcase)
   8. Send Test Alert to Teams

📊 MONITORING:
   9. Real-time System Monitor
   10. Check Import Status (Troubleshooting)

❌ EXIT:
   0. Exit

================================
""")

def run_script(script_name, description):
    """Run a Python script with error handling"""
    print(f"\n🚀 {description}")
    print("-" * len(description))
    
    try:
        if not Path(script_name).exists():
            print(f"❌ {script_name} not found!")
            return False
        
        exit_code = os.system(f'python "{script_name}"')
        
        if exit_code == 0:
            print(f"✅ {description} completed successfully!")
        else:
            print(f"⚠️ {description} ended with exit code {exit_code}")
        
        return True
        
    except KeyboardInterrupt:
        print(f"\n⏹️ {description} stopped by user")
        return True
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return False

def check_requirements():
    """Check if required files exist"""
    print("\n🔍 Checking System Requirements")
    print("-" * 35)
    
    required_files = [
        ('teams_integration.py', 'Teams Integration Module'),
        ('teams_enhanced_chatbot.py', 'Teams-Enhanced Chatbot'),
        ('enhanced_chatbot.py', 'Enhanced AI Chatbot'),
        ('requirements.txt', 'Requirements File'),
        ('.venv/Scripts/python.exe', 'Virtual Environment (Windows)'),
        ('.venv/bin/python', 'Virtual Environment (Unix)')
    ]
    
    all_good = True
    
    for file_path, description in required_files:
        if Path(file_path).exists():
            print(f"✅ {description}")
        else:
            if file_path.endswith(('python.exe', 'python')):
                continue  # Skip platform-specific venv checks
            print(f"❌ {description} - Missing: {file_path}")
            all_good = False
    
    # Check Python packages
    print("\n📦 Checking Key Packages:")
    packages = ['google-generativeai', 'transformers', 'aiohttp', 'psutil']
    
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package}")
        except ImportError:
            print(f"⚠️ {package} - Not installed (optional)")
    
    if all_good:
        print("\n🎉 All core files found! System ready.")
    else:
        print("\n⚠️ Some files missing. Run individual scripts to create them.")
    
    print("\n💡 To install packages: pip install -r requirements.txt")

def main():
    """Main launcher function"""
    while True:
        print_menu()
        
        try:
            choice = input("Enter your choice (0-10): ").strip()
            
            if choice == "0":
                print("\n👋 Goodbye! Your AIOps Bot is ready when you are!")
                break
                
            elif choice == "1":
                run_script("teams_setup.py", "Teams Integration Setup")
                
            elif choice == "2":
                check_requirements()
                
            elif choice == "3":
                print("\n🤖 Starting Basic AIOps Chatbot...")
                print("💡 This chatbot uses Gemini Pro for natural language processing")
                run_script("chatbot.py", "Basic AIOps Chatbot")
                
            elif choice == "4":
                print("\n🧠 Starting Enhanced AIOps Chatbot...")
                print("💡 This chatbot combines Gemini Pro + Hugging Face AI")
                run_script("enhanced_chatbot.py", "Enhanced AIOps Chatbot")
                
            elif choice == "5":
                print("\n📱 Starting Teams-Enabled Chatbot...")
                print("💡 Triple AI engine + automatic Teams notifications!")
                run_script("teams_enhanced_chatbot.py", "Teams-Enabled AIOps Chatbot")
                
            elif choice == "6":
                print("\n🧪 Testing Teams Integration...")
                run_script("teams_integration.py", "Teams Integration Test")
                
            elif choice == "7":
                print("\n🎭 Starting Full Hackathon Demo...")
                print("💡 Perfect for showcasing all your AIOps Bot features!")
                run_script("hackathon_demo.py", "Full Hackathon Demo")
                
            elif choice == "8":
                print("\n📤 Sending Test Alert...")
                # Quick test without full demo
                try:
                    import asyncio

                    from teams_integration import send_quick_test
                    
                    async def quick_test():
                        import os

                        from teams_integration import (MessageType,
                                                       TeamsCredentials,
                                                       send_aiops_alert)
                        
                        webhook_url = os.getenv('TEAMS_WEBHOOK_URL')
                        if not webhook_url:
                            print("❌ No Teams webhook configured")
                            print("💡 Run option 1 to setup Teams integration")
                            return
                        
                        credentials = TeamsCredentials(webhook_url=webhook_url)
                        success = await send_aiops_alert(
                            credentials=credentials,
                            webhook_url=webhook_url,
                            title="🎯 Quick Test Alert",
                            message="AIOps Bot test message sent successfully!",
                            alert_type=MessageType.SUCCESS
                        )
                        
                        if success:
                            print("✅ Test alert sent to Teams!")
                        else:
                            print("❌ Failed to send test alert")
                    
                    asyncio.run(quick_test())
                except Exception as e:
                    print(f"❌ Test failed: {e}")
                
            elif choice == "9":
                print("\n📊 Starting Real-time System Monitor...")
                print("💡 Monitor your system with AI-powered insights")
                # This would be a simple monitoring script
                try:
                    import time

                    import psutil
                    
                    print("🔄 Monitoring system (Press Ctrl+C to stop)...")
                    while True:
                        cpu = psutil.cpu_percent(interval=1)
                        memory = psutil.virtual_memory().percent
                        print(f"CPU: {cpu:5.1f}% | Memory: {memory:5.1f}% | {time.strftime('%H:%M:%S')}")
                        time.sleep(5)
                        
                except KeyboardInterrupt:
                    print("\n⏹️ Monitoring stopped")
                except Exception as e:
                    print(f"❌ Monitoring error: {e}")
                
            elif choice == "10":
                run_script("check_imports.py", "Import Status Check")
                
            else:
                print("❌ Invalid choice. Please enter a number from 0-10.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Launcher stopped. See you next time!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("💡 Please try again or check your setup.")
        
        # Pause before showing menu again
        if choice != "0":
            input("\nPress Enter to return to main menu...")

if __name__ == "__main__":
    print("🤖 AIOps Bot Launcher Starting...")
    main()