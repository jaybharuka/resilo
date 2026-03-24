from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import threading
import time
from datetime import datetime
import random
import sys
import os

import psutil
import platform
from datetime import datetime, timedelta

# Try to import Gemini AI integration
try:
    from gemini_integration import get_gemini_assistant
    GEMINI_AVAILABLE = True
    print("✅ Gemini AI integration loaded successfully")
except ImportError as e:
    print(f"⚠️ Gemini AI not available: {e}")
    GEMINI_AVAILABLE = False

app = Flask(__name__)
CORS(app)  # Enable CORS for all domains

# Boot time for uptime calculation
BOOT_TIME = datetime.fromtimestamp(psutil.boot_time())

def get_real_system_data():
    """Get actual system metrics using psutil"""
    try:
        # CPU Usage - Non-blocking approach like Task Manager
        # First call returns average since last call, subsequent calls are more accurate
        cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking
        if cpu_percent == 0.0:  # If first call, do a quick sample
            cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory Usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Disk Usage (for primary drive - Windows compatible)
        try:
            if platform.system() == "Windows":
                disk = psutil.disk_usage('C:')
            else:
                disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
        except:
            disk_percent = 0
            disk = type('obj', (object,), {'total': 0, 'free': 0})
        
        # Network I/O
        network = psutil.net_io_counters()
        
        # System temperature (if available)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Get the first available temperature sensor
                temp_values = list(temps.values())[0]
                if temp_values:
                    temperature = temp_values[0].current
                else:
                    temperature = 45.0  # Default if no temp sensors
            else:
                temperature = 45.0  # Default if no temp sensors
        except (AttributeError, KeyError):
            temperature = 45.0  # Default if temperature not available
        
        # System uptime
        uptime_delta = datetime.now() - BOOT_TIME
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        uptime = f"{days}d {hours}h {minutes}m"
        
        # Active processes
        active_processes = len(psutil.pids())
        
        # Determine status based on metrics
        if cpu_percent > 90 or memory_percent > 90 or temperature > 75:
            status = "critical"
        elif cpu_percent > 75 or memory_percent > 80 or temperature > 65:
            status = "warning"
        else:
            status = "healthy"
        
        return {
            "cpu": round(cpu_percent, 1),
            "memory": round(memory_percent, 1),
            "disk": round(disk_percent, 1),
            "network_in": round(network.bytes_recv / (1024*1024), 2),  # MB
            "network_out": round(network.bytes_sent / (1024*1024), 2),  # MB
            "temperature": round(temperature, 1),
            "status": status,
            "uptime": uptime,
            "active_processes": active_processes,
            "last_updated": datetime.now().isoformat(),
            # Additional detailed info
            "cpu_cores": psutil.cpu_count(logical=False),
            "cpu_threads": psutil.cpu_count(logical=True),
            "total_memory_gb": round(memory.total / (1024**3), 1),
            "available_memory_gb": round(memory.available / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1)
        }
    except Exception as e:
        print(f"Error getting real system data: {e}")
        # Return fallback data if real data fails
        return {
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "network_in": 0,
            "network_out": 0,
            "temperature": 0,
            "status": "error",
            "uptime": "Unknown",
            "active_processes": 0,
            "last_updated": datetime.now().isoformat()
        }

# Initialize with real system data
system_data = get_real_system_data()

recent_alerts = [
    {
        "id": 1,
        "severity": "warning",
        "message": "Memory usage approaching 80% threshold",
        "source": "System Monitor",
        "timestamp": datetime.now().isoformat(),
        "status": "active"
    },
    {
        "id": 2,
        "severity": "info",
        "message": "Backup completed successfully",
        "source": "Backup Service",
        "timestamp": datetime.now().isoformat(),
        "status": "resolved"
    }
]

def update_system_data():
    """Update system data with real-time metrics"""
    global system_data
    update_count = 0
    while True:
        try:
            # Get fresh real system data
            system_data = get_real_system_data()
            update_count += 1
            
            # Only log every 10 updates to reduce noise (every 10 seconds)
            if update_count % 10 == 0:
                print(f"📊 System Update #{update_count} - CPU: {system_data['cpu']}%, Memory: {system_data['memory']}%, Status: {system_data['status']}")
                
        except Exception as e:
            print(f"Error updating system data: {e}")
        
        time.sleep(1)  # Update every 1 second like Task Manager

# Start the real system data updates in a background thread
update_thread = threading.Thread(target=update_system_data, daemon=True)
update_thread.start()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api_server": "running",
            "system_monitor": "active"
        }
    })

@app.route('/api/system', methods=['GET'])
def get_system_data():
    """Get current system metrics"""
    return jsonify(system_data)

@app.route('/api/insights', methods=['GET'])
def get_ai_insights():
    """Get AI-generated insights based on real-time system data"""
    global system_data
    insights = []
    current_time = datetime.now().isoformat()
    
    # Dynamic CPU insights
    if system_data['cpu'] > 90:
        insights.append({
            "id": 1,
            "category": "performance",
            "message": f"🔥 Critical CPU usage at {system_data['cpu']:.1f}% - Immediate action required!",
            "confidence": 98,
            "timestamp": current_time,
            "priority": "critical",
            "action": "Open Task Manager to identify resource-heavy processes",
            "actionUrl": "taskmgr"
        })
    elif system_data['cpu'] > 70:
        insights.append({
            "id": 1,
            "category": "performance", 
            "message": f"⚠️ High CPU usage detected at {system_data['cpu']:.1f}% - Monitor closely",
            "confidence": 92,
            "timestamp": current_time,
            "priority": "high",
            "action": "Check background processes and consider closing unused applications",
            "actionUrl": "optimization"
        })
    elif system_data['cpu'] < 20:
        insights.append({
            "id": 1,
            "category": "performance",
            "message": f"✅ Excellent CPU performance at {system_data['cpu']:.1f}% - System running efficiently", 
            "confidence": 95,
            "timestamp": current_time,
            "priority": "info",
            "action": "Great time to run system maintenance or updates",
            "actionUrl": "maintenance"
        })
    else:
        insights.append({
            "id": 1,
            "category": "performance",
            "message": f"📊 CPU usage at {system_data['cpu']:.1f}% - Within normal parameters",
            "confidence": 88,
            "timestamp": current_time,
            "priority": "low",
            "action": "Continue monitoring for trends",
            "actionUrl": "monitor"
        })
    
    # Dynamic Memory insights
    if system_data['memory'] > 85:
        insights.append({
            "id": 2,
            "category": "memory",
            "message": f"🧠 Critical memory usage at {system_data['memory']:.1f}% - Close applications immediately!",
            "confidence": 96,
            "timestamp": current_time,
            "priority": "critical",
            "action": "Close unused applications and browser tabs",
            "actionUrl": "memory_cleanup"
        })
    elif system_data['memory'] > 70:
        insights.append({
            "id": 2,
            "category": "memory",
            "message": f"⚠️ High memory usage at {system_data['memory']:.1f}% - Consider optimization",
            "confidence": 89,
            "timestamp": current_time,
            "priority": "medium",
            "action": "Review running applications and close unnecessary ones",
            "actionUrl": "app_review"
        })
    else:
        insights.append({
            "id": 2,
            "category": "memory",
            "message": f"✅ Memory usage at {system_data['memory']:.1f}% - Healthy levels maintained",
            "confidence": 94,
            "timestamp": current_time,
            "priority": "info",
            "action": "Memory management is optimal",
            "actionUrl": "status_good"
        })
    
    # Dynamic Disk insights
    if system_data['disk'] > 90:
        insights.append({
            "id": 3,
            "category": "storage",
            "message": f"💾 Critical disk space - Only {100 - system_data['disk']:.1f}% free! Cleanup required",
            "confidence": 99,
            "timestamp": current_time,
            "priority": "critical",
            "action": "Run disk cleanup and remove large files",
            "actionUrl": "disk_cleanup"
        })
    elif system_data['disk'] > 80:
        insights.append({
            "id": 3,
            "category": "storage",
            "message": f"⚠️ Disk space running low at {system_data['disk']:.1f}% - Plan cleanup soon",
            "confidence": 91,
            "timestamp": current_time,
            "priority": "medium",
            "action": "Review and delete unnecessary files",
            "actionUrl": "file_review"
        })
    else:
        insights.append({
            "id": 3,
            "category": "storage",
            "message": f"✅ Disk usage at {system_data['disk']:.1f}% - Plenty of space available",
            "confidence": 90,
            "timestamp": current_time,
            "priority": "info",
            "action": "Storage levels are healthy",
            "actionUrl": "status_good"
        })
    
    # System Status insight
    if system_data['status'] == 'critical':
        insights.append({
            "id": 4,
            "category": "system",
            "message": "🚨 System in CRITICAL state - Multiple metrics need immediate attention!",
            "confidence": 97,
            "timestamp": current_time,
            "priority": "critical",
            "action": "Review all system metrics and take corrective action",
            "actionUrl": "system_check"
        })
    elif system_data['status'] == 'warning':
        insights.append({
            "id": 4,
            "category": "system",
            "message": "🟡 System showing warning indicators - Monitor and optimize as needed",
            "confidence": 85,
            "timestamp": current_time,
            "priority": "medium",
            "action": "Check individual metrics for optimization opportunities",
            "actionUrl": "metric_review"
        })
    else:
        insights.append({
            "id": 4,
            "category": "system",
            "message": "🟢 System operating normally - All metrics within healthy ranges",
            "confidence": 92,
            "timestamp": current_time,
            "priority": "info",
            "action": "Continue routine monitoring",
            "actionUrl": "continue_monitoring"
        })
    
    # Temperature insight (if elevated)
    if system_data['temperature'] > 80:
        insights.append({
            "id": 5,
            "category": "thermal",
            "message": f"🌡️ High temperature warning: {system_data['temperature']:.1f}°C - Check cooling system!",
            "confidence": 93,
            "timestamp": current_time,
            "priority": "high",
            "action": "Verify fans are working and vents are clear",
            "actionUrl": "cooling_check"
        })
    elif system_data['temperature'] > 70:
        insights.append({
            "id": 5,
            "category": "thermal",
            "message": f"🌡️ Temperature elevated at {system_data['temperature']:.1f}°C - Monitor cooling",
            "confidence": 87,
            "timestamp": current_time,
            "priority": "medium",
            "action": "Consider improving system ventilation",
            "actionUrl": "thermal_optimization"
        })
    
    return jsonify(insights)

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts"""
    return jsonify(recent_alerts)

@app.route('/api/chat', methods=['POST'])
def chat_with_ai():
    """Chat with the AI assistant using Gemini AI when available"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        if not message:
            return jsonify({"error": "Message is required"}), 400
        
        # Try to use Gemini AI first
        if GEMINI_AVAILABLE:
            try:
                gemini_assistant = get_gemini_assistant()
                if gemini_assistant:
                    # Use asyncio to run the async method
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    # Get conversation history from request if available
                    conversation_history = data.get('conversation_history', [])
                    
                    # Get AI response
                    ai_result = loop.run_until_complete(
                        gemini_assistant.chat(
                            message=message,
                            system_data=system_data,
                            conversation_history=conversation_history
                        )
                    )
                    
                    # Add timestamp
                    ai_result['timestamp'] = datetime.now().isoformat()
                    
                    return jsonify(ai_result)
            except Exception as e:
                print(f"Gemini AI error: {e}")
                # Fall back to rule-based responses
        
        # Enhanced fallback to intelligent responses when Gemini is not available
        message_lower = message.lower()
        
        # System status queries
        if any(word in message_lower for word in ['hello', 'hi', 'hey']):
            response = f"👋 Hello! I'm your AIOps assistant monitoring your system in real-time. Currently your CPU is at {system_data['cpu']:.1f}% and memory at {system_data['memory']:.1f}%. How can I help you optimize your system today?"
        elif any(word in message_lower for word in ['cpu', 'processor', 'performance']):
            cpu_status = "excellent" if system_data['cpu'] < 30 else "good" if system_data['cpu'] < 60 else "elevated" if system_data['cpu'] < 85 else "critical"
            response = f"🔥 Your CPU is currently at {system_data['cpu']:.1f}% - that's {cpu_status} performance. {system_data['active_processes']} processes are running. {'Consider checking which processes are consuming resources.' if system_data['cpu'] > 70 else 'Looking good!'} 📊"
        elif any(word in message_lower for word in ['memory', 'ram']):
            memory_status = "excellent" if system_data['memory'] < 50 else "good" if system_data['memory'] < 70 else "high" if system_data['memory'] < 85 else "critical"
            response = f"🧠 Memory usage is at {system_data['memory']:.1f}% - {memory_status} level. You have {system_data.get('available_memory_gb', 'N/A')}GB available of {system_data.get('total_memory_gb', 'N/A')}GB total. {'Consider closing unused applications.' if system_data['memory'] > 80 else 'Memory usage looks healthy!'} 💾"
        elif any(word in message_lower for word in ['disk', 'storage', 'space']):
            disk_status = "plenty of space" if system_data['disk'] < 50 else "getting full" if system_data['disk'] < 80 else "critically low" if system_data['disk'] > 90 else "limited space"
            response = f"💾 Disk usage is at {system_data['disk']:.1f}% - {disk_status}. You have {system_data.get('disk_free_gb', 'N/A')}GB free of {system_data.get('disk_total_gb', 'N/A')}GB total. {'⚠️ Consider cleaning up files!' if system_data['disk'] > 85 else '✅ Storage looks good!'}"
        elif any(word in message_lower for word in ['network', 'internet', 'connection']):
            response = f"🌐 Network activity: {system_data['network_in']:.1f}MB received, {system_data['network_out']:.1f}MB sent. {'High network activity detected!' if system_data['network_in'] > 100 or system_data['network_out'] > 100 else 'Network traffic is normal.'} Connection looks stable! 📡"
        elif any(word in message_lower for word in ['temperature', 'temp', 'heat', 'cooling']):
            temp_status = "excellent" if system_data['temperature'] < 50 else "normal" if system_data['temperature'] < 65 else "warm" if system_data['temperature'] < 75 else "HOT - check cooling!"
            response = f"🌡️ System temperature: {system_data['temperature']:.1f}°C - {temp_status}. {'❄️ Great cooling!' if system_data['temperature'] < 50 else '🔥 Monitor temperature closely!' if system_data['temperature'] > 70 else 'Temperature is within normal range.'}"
        elif any(word in message_lower for word in ['status', 'health', 'overall', 'system']):
            response = f"🏥 System Health Report:\n• Status: {system_data['status'].upper()} {'🟢' if system_data['status'] == 'healthy' else '🟡' if system_data['status'] == 'warning' else '🔴'}\n• Uptime: {system_data['uptime']}\n• Processes: {system_data['active_processes']} running\n• Last check: just now\n\n{'All systems operational!' if system_data['status'] == 'healthy' else 'Some metrics need attention.' if system_data['status'] == 'warning' else 'URGENT: Critical issues detected!'}"
        elif any(word in message_lower for word in ['help', 'what', 'how', 'can you']):
            response = f"🤖 I'm your intelligent AIOps assistant! I can help you with:\n\n🔍 **Real-time monitoring** - CPU, memory, disk, network\n📊 **Performance analysis** - Identify bottlenecks\n🛠️ **Optimization tips** - Improve system efficiency\n⚠️ **Alert management** - Track system issues\n🌡️ **Health checks** - Temperature & status monitoring\n\nCurrent system: {system_data['status']} | {system_data['cpu']:.1f}% CPU | {system_data['memory']:.1f}% RAM\n\nJust ask me anything about your system!"
        elif any(word in message_lower for word in ['optimize', 'improve', 'faster', 'speed']):
            suggestions = []
            if system_data['cpu'] > 70: suggestions.append("🔥 High CPU - check background processes")
            if system_data['memory'] > 80: suggestions.append("🧠 High memory - close unused apps") 
            if system_data['disk'] > 85: suggestions.append("💾 Low disk space - clean temporary files")
            if system_data['temperature'] > 70: suggestions.append("🌡️ High temp - check cooling system")
            
            if suggestions:
                response = f"🚀 **Optimization Recommendations:**\n\n" + "\n".join(suggestions) + f"\n\n📈 Current performance: CPU {system_data['cpu']:.1f}% | RAM {system_data['memory']:.1f}% | Temp {system_data['temperature']:.1f}°C"
            else:
                response = f"✨ Your system is running well! CPU: {system_data['cpu']:.1f}%, Memory: {system_data['memory']:.1f}%, Temperature: {system_data['temperature']:.1f}°C. Consider regular maintenance like disk cleanup and software updates for optimal performance! 🎯"
        elif any(word in message_lower for word in ['alert', 'warning', 'problem', 'issue']):
            active_alerts = len([a for a in recent_alerts if a['status'] == 'active'])
            if active_alerts > 0:
                response = f"🚨 **{active_alerts} Active Alerts:**\n• {recent_alerts[0]['message']}\n• Severity: {recent_alerts[0]['severity']}\n• Source: {recent_alerts[0]['source']}\n\nSystem status: {system_data['status']} - {'Immediate attention needed!' if system_data['status'] == 'critical' else 'Monitoring closely.'}"
            else:
                response = f"✅ **No active alerts!** Your system is running smoothly.\n\nCurrent status: {system_data['status']} | Last check: {system_data['last_updated'][:19]}\n\nI'm continuously monitoring for any issues. 🛡️"
        elif any(word in message_lower for word in ['processes', 'apps', 'programs']):
            response = f"⚙️ **Process Information:**\n• Active processes: {system_data['active_processes']}\n• CPU cores: {system_data.get('cpu_cores', 'N/A')} cores, {system_data.get('cpu_threads', 'N/A')} threads\n• System load: {'Light' if system_data['cpu'] < 30 else 'Moderate' if system_data['cpu'] < 70 else 'Heavy'}\n\n{'💡 Tip: Check Task Manager for detailed process info!' if system_data['cpu'] > 50 else '✅ Process load is normal.'}"
        else:
            # Dynamic responses based on current system state
            if system_data['status'] == 'critical':
                response = f"🔴 **CRITICAL ALERT:** Your system needs immediate attention! CPU: {system_data['cpu']:.1f}% | Memory: {system_data['memory']:.1f}% | Status: {system_data['status']}. I'm here to help troubleshoot any issues you're experiencing! �"
            elif system_data['status'] == 'warning':
                response = f"🟡 I'm monitoring your system and noticed some elevated metrics. CPU: {system_data['cpu']:.1f}%, Memory: {system_data['memory']:.1f}%. How can I help optimize performance? Ask me about specific components! ⚡"
            else:
                responses = [
                    f"✅ Your system is healthy! CPU: {system_data['cpu']:.1f}%, Memory: {system_data['memory']:.1f}%. What would you like to monitor or optimize? 📊",
                    f"🔍 Real-time monitoring active! Current stats: {system_data['cpu']:.1f}% CPU, {system_data['memory']:.1f}% RAM, {system_data['temperature']:.1f}°C. Ask me anything about your system! 🖥️",
                    f"🤖 AIOps Assistant ready! Your system uptime: {system_data['uptime']} | Status: {system_data['status']} | How can I help you today? 💚",
                    f"📈 System performance tracking enabled! Current load: {system_data['active_processes']} processes running. What metrics interest you most? 🎯"
                ]
                response = random.choice(responses)
        
        return jsonify({
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "source": "aiops_assistant_fallback",
            "system_analysis": None,
            "suggestions": [],
            "personalized": False
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/performance', methods=['GET'])
def get_performance_data():
    """Get historical performance data for charts"""
    # Generate mock historical data
    performance_data = []
    current_time = datetime.now()
    
    for i in range(24):  # Last 24 data points
        timestamp = current_time.timestamp() - (i * 60)  # Every minute
        performance_data.append({
            "timestamp": timestamp,
            "cpu": random.uniform(30, 70),
            "memory": random.uniform(50, 80),
            "disk": random.uniform(40, 60),
            "network_in": random.uniform(20, 120),
            "network_out": random.uniform(10, 60),
            "temperature": random.uniform(45, 65)
        })
    
    return jsonify(sorted(performance_data, key=lambda x: x['timestamp']))

@app.route('/api/ai-health', methods=['GET'])
def get_ai_health_analysis():
    """Get real-time AI health analysis data"""
    global system_data
    
    # Calculate health score based on real system metrics
    cpu_score = max(0, 100 - system_data['cpu'])  # Lower CPU usage = higher score
    memory_score = max(0, 100 - system_data['memory'])  # Lower memory usage = higher score
    disk_score = max(0, 100 - system_data['disk'])  # Lower disk usage = higher score
    temp_score = max(0, 100 - (system_data['temperature'] * 1.5))  # Lower temp = higher score
    
    # Overall health score (weighted average)
    health_score = int((cpu_score * 0.3 + memory_score * 0.3 + disk_score * 0.2 + temp_score * 0.2))
    health_score = max(0, min(100, health_score))  # Clamp between 0-100
    
    # Calculate confidence based on data stability
    confidence = random.randint(88, 98)  # Simulate confidence based on data quality
    
    # Performance, Security, Stability metrics based on real data
    performance = max(10, 100 - system_data['cpu'] - (system_data['memory'] * 0.5))
    security = random.randint(85, 95)  # Simulated security score
    stability = max(20, 100 - (system_data['temperature'] - 45) * 2)  # Temperature affects stability
    
    return jsonify({
        "health_score": health_score,
        "confidence": confidence,
        "performance": min(100, max(0, int(performance))),
        "security": security,
        "stability": min(100, max(0, int(stability))),
        "description": f"System health calculated from real-time metrics. CPU: {system_data['cpu']:.1f}%, Memory: {system_data['memory']:.1f}%, Temperature: {system_data['temperature']:.1f}°C",
        "last_updated": datetime.now().isoformat()
    })

@app.route('/api/anomalies', methods=['GET'])
def get_anomaly_detection():
    """Get real-time anomaly detection data"""
    global system_data
    anomalies = []
    current_time = datetime.now()
    
    # CPU Anomaly Detection
    if system_data['cpu'] > 85:
        anomalies.append({
            "id": 1,
            "name": "Critical CPU Spike",
            "description": f"Extremely high CPU usage detected at {system_data['cpu']:.1f}%",
            "time": "Just now",
            "severity": "critical",
            "icon": "🔴"
        })
    elif system_data['cpu'] > 70:
        anomalies.append({
            "id": 1,
            "name": "CPU Spike",
            "description": f"Unusual CPU activity detected at {system_data['cpu']:.1f}%",
            "time": random.choice(["2 min ago", "5 min ago", "8 min ago"]),
            "severity": "warning",
            "icon": "⚠️"
        })
    
    # Memory Anomaly Detection
    if system_data['memory'] > 85:
        anomalies.append({
            "id": 2,
            "name": "Memory Leak",
            "description": f"Critical memory usage detected at {system_data['memory']:.1f}%",
            "time": "3 min ago",
            "severity": "critical",
            "icon": "🔴"
        })
    elif system_data['memory'] > 75:
        anomalies.append({
            "id": 2,
            "name": "Memory Pressure",
            "description": f"Elevated memory usage in background processes at {system_data['memory']:.1f}%",
            "time": random.choice(["10 min ago", "15 min ago", "18 min ago"]),
            "severity": "warning",
            "icon": "⚠️"
        })
    
    # Temperature Anomaly Detection
    if system_data['temperature'] > 75:
        anomalies.append({
            "id": 3,
            "name": "Thermal Warning",
            "description": f"High system temperature detected at {system_data['temperature']:.1f}°C",
            "time": "7 min ago",
            "severity": "warning",
            "icon": "🌡️"
        })
    
    # Disk Anomaly Detection
    if system_data['disk'] > 90:
        anomalies.append({
            "id": 4,
            "name": "Low Disk Space",
            "description": f"Critical disk space remaining: {100 - system_data['disk']:.1f}%",
            "time": "12 min ago",
            "severity": "critical",
            "icon": "💾"
        })
    elif system_data['disk'] > 85:
        anomalies.append({
            "id": 4,
            "name": "Disk Space Warning",
            "description": f"Disk space running low at {system_data['disk']:.1f}% usage",
            "time": random.choice(["20 min ago", "25 min ago", "30 min ago"]),
            "severity": "warning",
            "icon": "💾"
        })
    
    # Network Anomaly Detection (if high traffic)
    if system_data['network_in'] > 100 or system_data['network_out'] > 100:
        anomalies.append({
            "id": 5,
            "name": "Network Activity Spike",
            "description": f"Unusual network traffic: {system_data['network_in']:.1f}MB in, {system_data['network_out']:.1f}MB out",
            "time": "6 min ago",
            "severity": "info",
            "icon": "🌐"
        })
    
    # Process Anomaly Detection
    if system_data['active_processes'] > 200:
        anomalies.append({
            "id": 6,
            "name": "High Process Count",
            "description": f"Unusually high number of processes: {system_data['active_processes']}",
            "time": "14 min ago",
            "severity": "warning",
            "icon": "⚙️"
        })
    
    # If no anomalies, add a positive status
    if not anomalies:
        anomalies.append({
            "id": 0,
            "name": "System Healthy",
            "description": "All metrics within normal parameters",
            "time": "Now",
            "severity": "info",
            "icon": "✅"
        })
    
    return jsonify({
        "status": "ACTIVE" if anomalies and anomalies[0]["id"] != 0 else "MONITORING",
        "anomalies": anomalies[:5],  # Limit to 5 most recent
        "total_detected": len([a for a in anomalies if a["id"] != 0]),
        "last_scan": current_time.isoformat()
    })

@app.route('/api/predictive', methods=['GET'])
def get_predictive_analytics():
    """Get real-time predictive analytics data"""
    global system_data
    
    # Get timeframe parameter (default to 1 hour)
    timeframe = request.args.get('timeframe', '1hour')
    
    # Base predictions on current trends
    current_cpu = system_data['cpu']
    current_memory = system_data['memory']
    current_disk = system_data['disk']
    
    # Simulate trend analysis
    cpu_trend = random.uniform(-5, 15)  # CPU tends to increase over time
    memory_trend = random.uniform(-2, 10)  # Memory slowly increases
    disk_trend = random.uniform(0, 2)  # Disk usage slowly increases
    
    # Calculate predictions based on timeframe
    if timeframe == '1hour':
        multiplier = 1
        timeframe_label = "Next Hour"
    elif timeframe == '6hours':
        multiplier = 3
        timeframe_label = "Next 6 Hours"
    elif timeframe == '24hours':
        multiplier = 8
        timeframe_label = "Next 24 Hours"
    else:
        multiplier = 1
        timeframe_label = "Next Hour"
    
    # Calculate predicted values
    predicted_cpu = min(100, max(0, current_cpu + (cpu_trend * multiplier)))
    predicted_memory = min(100, max(0, current_memory + (memory_trend * multiplier)))
    predicted_disk = min(100, max(0, current_disk + (disk_trend * multiplier)))
    
    # Calculate confidence based on system stability
    base_confidence = 85
    if system_data['status'] == 'healthy':
        confidence_modifier = random.randint(5, 15)
    elif system_data['status'] == 'warning':
        confidence_modifier = random.randint(-5, 5)
    else:
        confidence_modifier = random.randint(-15, -5)
    
    return jsonify({
        "timeframe": timeframe,
        "timeframe_label": timeframe_label,
        "metrics": [
            {
                "name": "CPU Usage",
                "current": round(current_cpu, 1),
                "predicted": round(predicted_cpu, 1),
                "trend": f"+{cpu_trend:.1f}%" if cpu_trend > 0 else f"{cpu_trend:.1f}%",
                "trend_direction": "up" if cpu_trend > 0 else "down" if cpu_trend < 0 else "stable",
                "confidence": min(98, max(70, base_confidence + confidence_modifier + random.randint(-3, 3))),
                "type": "cpu"
            },
            {
                "name": "Memory Usage",
                "current": round(current_memory, 1),
                "predicted": round(predicted_memory, 1),
                "trend": f"+{memory_trend:.1f}%" if memory_trend > 0 else f"{memory_trend:.1f}%",
                "trend_direction": "up" if memory_trend > 0 else "down" if memory_trend < 0 else "stable",
                "confidence": min(98, max(70, base_confidence + confidence_modifier + random.randint(-3, 3))),
                "type": "memory"
            },
            {
                "name": "Storage Usage",
                "current": round(current_disk, 1),
                "predicted": round(predicted_disk, 1),
                "trend": f"+{disk_trend:.1f}%" if disk_trend > 0 else f"{disk_trend:.1f}%",
                "trend_direction": "up" if disk_trend > 0 else "down" if disk_trend < 0 else "stable",
                "confidence": min(98, max(70, base_confidence + confidence_modifier + random.randint(-3, 3))),
                "type": "storage"
            }
        ],
        "analysis": f"Predictions based on current system state ({system_data['status']}) and recent performance trends.",
        "last_updated": datetime.now().isoformat()
    })

@app.route('/api/processes', methods=['GET'])
def get_real_processes():
    """Get real-time process information"""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'create_time']):
            try:
                pinfo = proc.info
                if pinfo['cpu_percent'] is not None and pinfo['memory_percent'] is not None:
                    # Calculate runtime
                    create_time = datetime.fromtimestamp(pinfo['create_time'])
                    runtime = datetime.now() - create_time
                    runtime_str = f"{runtime.days}d {runtime.seconds//3600}h {(runtime.seconds//60)%60}m"
                    
                    processes.append({
                        "pid": pinfo['pid'],
                        "name": pinfo['name'][:20],  # Truncate long names
                        "cpu": round(pinfo['cpu_percent'], 1),
                        "memory": round(pinfo['memory_percent'], 1),
                        "status": pinfo['status'],
                        "runtime": runtime_str,
                        "priority": "Normal"  # Simplified priority
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sort by CPU usage and return top 20
        processes.sort(key=lambda x: x['cpu'], reverse=True)
        return jsonify(processes[:20])
        
    except Exception as e:
        print(f"Error getting processes: {e}")
        return jsonify([])

if __name__ == '__main__':
    print("🚀 Starting AIOps Dashboard API Server...")
    print("📊 Dashboard will be available at: http://localhost:3000")
    print("🔌 API Server running on: http://localhost:5000")
    print("\n📋 Available endpoints:")
    print("  • GET  /api/health     - Health check")
    print("  • GET  /api/system     - System metrics")
    print("  • GET  /api/insights   - AI insights")
    print("  • GET  /api/alerts     - Recent alerts")
    print("  • POST /api/chat       - Chat with AI")
    print("  • GET  /api/performance - Performance data")
    print("  • GET  /api/ai-health  - AI health analysis")
    print("  • GET  /api/anomalies  - Anomaly detection")
    print("  • GET  /api/predictive - Predictive analytics")
    print("  • GET  /api/processes  - Real-time processes")
    print("\n✨ Ready to serve your AIOps dashboard!")
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)