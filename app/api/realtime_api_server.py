from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import threading
import time
from datetime import datetime, timedelta
import platform
import sys
import os
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
from crisp_chatbot import enhanced_chat_handler
from autonomous_operations_system import AutonomousBot

# Load environment variables
load_dotenv()

app = Flask(__name__)
_RT_ORIGINS = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', '').split(',') if o.strip()]
CORS(app, resources={r"/*": {
    "origins": _RT_ORIGINS,
    "supports_credentials": True,
}})

# Configure Gemini API
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Initialize autonomous bot
autonomous_bot = AutonomousBot()

# Global variables for storing system data
system_data = {}
ai_insights = []
recent_alerts = []
system_start_time = datetime.now()

def get_real_system_data():
    """Get actual system metrics using psutil"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        
        # Network I/O
        network = psutil.net_io_counters()
        
        # Calculate network speed (bytes per second)
        current_time = time.time()
        if hasattr(get_real_system_data, 'last_network_time'):
            time_diff = current_time - get_real_system_data.last_network_time
            bytes_sent_diff = network.bytes_sent - get_real_system_data.last_bytes_sent
            bytes_recv_diff = network.bytes_recv - get_real_system_data.last_bytes_recv
            
            network_out_speed = (bytes_sent_diff / time_diff) / 1024 / 1024  # MB/s
            network_in_speed = (bytes_recv_diff / time_diff) / 1024 / 1024   # MB/s
        else:
            network_out_speed = 0
            network_in_speed = 0
        
        # Store for next calculation
        get_real_system_data.last_network_time = current_time
        get_real_system_data.last_bytes_sent = network.bytes_sent
        get_real_system_data.last_bytes_recv = network.bytes_recv
        
        # Boot time and uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
        
        # Process count
        process_count = len(psutil.pids())
        
        # Temperature (if available)
        temperature = 0
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        for entry in entries:
                            if entry.current:
                                temperature = max(temperature, entry.current)
        except:
            temperature = 45 + cpu_percent * 0.3  # Estimate based on CPU
        
        # Determine system status
        status = "healthy"
        if cpu_percent > 90 or memory_percent > 90 or disk_percent > 95:
            status = "critical"
        elif cpu_percent > 75 or memory_percent > 80 or disk_percent > 85:
            status = "warning"
        
        return {
            "cpu": round(cpu_percent, 1),
            "memory": round(memory_percent, 1),
            "disk": round(disk_percent, 1),
            "network_in": round(network_in_speed, 2),
            "network_out": round(network_out_speed, 2),
            "temperature": round(temperature, 1),
            "status": status,
            "uptime": uptime_str,
            "active_processes": process_count,
            "last_updated": datetime.now().isoformat(),
            "total_memory_gb": round(memory.total / (1024**3), 1),
            "available_memory_gb": round(memory.available / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1),
            "cpu_cores": psutil.cpu_count(),
            "cpu_threads": psutil.cpu_count(logical=True)
        }
    except Exception as e:
        print(f"Error getting system data: {e}")
        return {
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "network_in": 0,
            "network_out": 0,
            "temperature": 0,
            "status": "error",
            "uptime": "N/A",
            "active_processes": 0,
            "last_updated": datetime.now().isoformat(),
            "error": str(e)
        }

def generate_ai_insights():
    """Generate AI insights based on current system data"""
    global ai_insights
    current_data = get_real_system_data()
    
    insights = []
    insight_id = 1
    
    # CPU Analysis
    if current_data["cpu"] > 80:
        insights.append({
            "id": insight_id,
            "category": "performance",
            "message": f"High CPU usage detected ({current_data['cpu']}%). Consider closing unnecessary applications or checking for background processes.",
            "confidence": 92,
            "timestamp": datetime.now().isoformat(),
            "priority": "high"
        })
        insight_id += 1
    elif current_data["cpu"] < 10:
        insights.append({
            "id": insight_id,
            "category": "performance",
            "message": f"System is running efficiently with low CPU usage ({current_data['cpu']}%). Great performance!",
            "confidence": 88,
            "timestamp": datetime.now().isoformat(),
            "priority": "info"
        })
        insight_id += 1
    
    # Memory Analysis
    if current_data["memory"] > 85:
        insights.append({
            "id": insight_id,
            "category": "memory",
            "message": f"Memory usage is high ({current_data['memory']}%). Consider closing browser tabs or memory-intensive applications.",
            "confidence": 90,
            "timestamp": datetime.now().isoformat(),
            "priority": "high"
        })
        insight_id += 1
    
    # Disk Analysis
    if current_data["disk"] > 90:
        insights.append({
            "id": insight_id,
            "category": "storage",
            "message": f"Disk space is critically low ({current_data['disk']}%). Clean up temporary files or move data to external storage.",
            "confidence": 95,
            "timestamp": datetime.now().isoformat(),
            "priority": "critical"
        })
        insight_id += 1
    
    # Temperature Analysis
    if current_data["temperature"] > 70:
        insights.append({
            "id": insight_id,
            "category": "thermal",
            "message": f"System temperature is elevated ({current_data['temperature']}°C). Ensure proper ventilation and check cooling systems.",
            "confidence": 87,
            "timestamp": datetime.now().isoformat(),
            "priority": "medium"
        })
        insight_id += 1
    
    # Network Analysis
    if current_data["network_in"] > 10:
        insights.append({
            "id": insight_id,
            "category": "network",
            "message": f"High network activity detected ({current_data['network_in']:.1f} MB/s incoming). Monitor for unexpected data usage.",
            "confidence": 75,
            "timestamp": datetime.now().isoformat(),
            "priority": "info"
        })
        insight_id += 1
    
    if not insights:
        insights.append({
            "id": 1,
            "category": "system",
            "message": "All system metrics are within normal ranges. Your system is performing optimally!",
            "confidence": 95,
            "timestamp": datetime.now().isoformat(),
            "priority": "info"
        })
    
    ai_insights = insights

def chat_with_gemini(message, system_context):
    """Enhanced chat using Gemini API with system context"""
    try:
        model = genai.GenerativeModel('gemini-pro')
        
        # Create a comprehensive context for the AI
        context = f"""You are an intelligent AIOps assistant monitoring a computer system. 
        
Current System Status:
- CPU: {system_context.get('cpu', 0)}%
- Memory: {system_context.get('memory', 0)}%
- Disk: {system_context.get('disk', 0)}%
- Temperature: {system_context.get('temperature', 0)}°C
- Network In: {system_context.get('network_in', 0)} MB/s
- Network Out: {system_context.get('network_out', 0)} MB/s
- Active Processes: {system_context.get('active_processes', 0)}
- System Status: {system_context.get('status', 'unknown')}
- Uptime: {system_context.get('uptime', 'unknown')}

You should:
1. Have natural conversations about system monitoring and performance
2. Provide specific insights based on the current system metrics
3. Give actionable recommendations for system optimization
4. Answer technical questions about system performance
5. Be conversational and helpful, not just technical
6. Use emojis occasionally to make responses engaging

User message: {message}"""

        response = model.generate_content(context)
        return response.text
    except Exception as e:
        print(f"Gemini API error: {e}")
        # Fallback to rule-based responses
        return generate_fallback_response(message, system_context)

def generate_fallback_response(message, system_context):
    """Fallback response system when Gemini API is not available"""
    message_lower = message.lower()
    
    if any(word in message_lower for word in ['cpu', 'processor', 'performance']):
        cpu = system_context.get('cpu', 0)
        if cpu > 80:
            return f"🔥 Your CPU is running hot at {cpu}%! I'd recommend checking Task Manager to see which processes are using the most CPU. You might want to close some applications or restart if it stays this high."
        elif cpu < 20:
            return f"✨ Your CPU is chilling at {cpu}% - nice and efficient! This is great for battery life and system longevity."
        else:
            return f"📊 CPU usage is at {cpu}%, which is pretty normal for regular use. Looking good!"
    
    elif any(word in message_lower for word in ['memory', 'ram']):
        memory = system_context.get('memory', 0)
        total_gb = system_context.get('total_memory_gb', 0)
        if memory > 85:
            return f"⚠️ Memory usage is quite high at {memory}%! With {total_gb}GB total, you might want to close some browser tabs or applications to free up RAM."
        else:
            return f"💾 Memory usage looks healthy at {memory}% of your {total_gb}GB RAM. You've got plenty of headroom!"
    
    elif any(word in message_lower for word in ['temperature', 'temp', 'heat']):
        temp = system_context.get('temperature', 0)
        if temp > 70:
            return f"🌡️ System temperature is {temp}°C - that's getting warm! Make sure your vents aren't blocked and consider cleaning dust from fans."
        else:
            return f"❄️ Temperature is nice and cool at {temp}°C. Your cooling system is doing its job well!"
    
    elif any(word in message_lower for word in ['hello', 'hi', 'hey']):
        status = system_context.get('status', 'unknown')
        return f"👋 Hey there! I'm monitoring your system and everything looks {status}. What would you like to know about your computer's performance?"
    
    elif any(word in message_lower for word in ['help', 'what can you do']):
        return "🤖 I'm your AIOps assistant! I can help you with:\n• Real-time system monitoring\n• Performance analysis and optimization tips\n• Explaining what your CPU, memory, and disk usage means\n• Troubleshooting performance issues\n• Just having a normal conversation about tech!\n\nWhat would you like to explore?"
    
    else:
        return f"🤔 Interesting question! Based on your current system stats (CPU: {system_context.get('cpu', 0)}%, Memory: {system_context.get('memory', 0)}%), is there something specific about your computer's performance you'd like to discuss?"

def update_system_data():
    """Continuously update system data in real-time"""
    global system_data
    while True:
        try:
            system_data = get_real_system_data()
            generate_ai_insights()
            time.sleep(1)  # Update every second for real-time data
        except Exception as e:
            print(f"Error in system data update: {e}")
            time.sleep(5)

# Start the real-time system monitoring
monitoring_thread = threading.Thread(target=update_system_data, daemon=True)
monitoring_thread.start()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api_server": "running",
            "system_monitor": "active",
            "ai_insights": "enabled",
            "gemini_api": "configured" if os.getenv('GEMINI_API_KEY') else "not_configured"
        }
    })

@app.route('/api/system', methods=['GET'])
def get_system_data():
    """Get current real-time system metrics"""
    return jsonify(system_data)

@app.route('/api/insights', methods=['GET'])
def get_ai_insights():
    """Get AI-generated insights based on current system state"""
    return jsonify(ai_insights)

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get recent system alerts"""
    return jsonify(recent_alerts)

@app.route('/api/chat', methods=['POST'])
def chat_with_ai():
    """Enhanced chat with crisp, actionable responses"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        if not message:
            return jsonify({"error": "Message is required"}), 400
        
        # Get current system context for AI
        current_system = get_real_system_data()
        
        # Use enhanced crisp chatbot
        response_data = enhanced_chat_handler(message, current_system)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/autonomous/suggestions', methods=['GET'])
def get_autonomous_suggestions():
    """Get current autonomous action suggestions"""
    try:
        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        suggestions = loop.run_until_complete(
            autonomous_bot.analyze_system_and_suggest_actions()
        )
        loop.close()
        
        return jsonify({
            'suggestions': suggestions,
            'pending_actions': autonomous_bot.get_pending_actions(),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/autonomous/permission', methods=['POST'])
def handle_autonomous_permission():
    """Handle user response to autonomous action permission request"""
    try:
        data = request.get_json()
        suggestion_id = data.get('suggestion_id')
        response = data.get('response')  # 'approve', 'deny', 'delay'
        
        if not suggestion_id or not response:
            return jsonify({"error": "suggestion_id and response are required"}), 400
        
        # Handle response asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            autonomous_bot.handle_user_response(suggestion_id, response)
        )
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/autonomous/history', methods=['GET'])
def get_autonomous_history():
    """Get history of autonomous actions"""
    try:
        history = autonomous_bot.get_action_history()
        return jsonify({
            'actions': history,
            'total_count': len(history),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/performance', methods=['GET'])
def get_performance_data():
    """Get current performance metrics for charts"""
    current_data = get_real_system_data()
    performance_data = [{
        "timestamp": datetime.now().timestamp(),
        "cpu": current_data["cpu"],
        "memory": current_data["memory"],
        "disk": current_data["disk"],
        "network_in": current_data["network_in"],
        "network_out": current_data["network_out"],
        "temperature": current_data["temperature"]
    }]
    
    return jsonify(performance_data)

if __name__ == '__main__':
    print("🚀 Starting Real-Time AIOps Dashboard API Server...")
    print("📊 Dashboard will be available at: http://localhost:3000")
    print("🔌 API Server running on: http://localhost:5000")
    print("\n📋 Available endpoints:")
    print("  • GET  /api/health     - Health check")
    print("  • GET  /api/system     - Real-time system metrics")
    print("  • GET  /api/insights   - AI-generated insights")
    print("  • GET  /api/alerts     - System alerts")
    print("  • POST /api/chat       - Chat with Gemini AI")
    print("  • GET  /api/performance - Performance data")
    print("\n🤖 Gemini AI Integration:", "✅ Enabled" if os.getenv('GEMINI_API_KEY') else "❌ Set GEMINI_API_KEY environment variable")
    print("\n✨ Real-time monitoring active - updates every second!")
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)