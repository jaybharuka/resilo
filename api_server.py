from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import json
import threading
import time
from datetime import datetime
import random
import sys
import os

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from enhanced_aiops_chatbot import EnhancedAIOpsBot
    from huggingface_ai_integration import HuggingFaceAIEngine
except ImportError as e:
    print(f"Warning: Could not import AIOps components: {e}")
    EnhancedAIOpsBot = None
    HuggingFaceAIEngine = None

app = Flask(__name__)
CORS(app)  # Enable CORS for all domains

# Global variables for storing system data
system_data = {
    "cpu": 45.2,
    "memory": 67.8,
    "disk": 52.3,
    "network_in": 125.6,
    "network_out": 89.2,
    "temperature": 58.5,
    "status": "healthy",
    "uptime": "2d 14h 32m",
    "active_processes": 156,
    "last_updated": datetime.now().isoformat()
}

ai_insights = [
    {
        "id": 1,
        "category": "performance",
        "message": "CPU usage is stable within normal parameters",
        "confidence": 95,
        "timestamp": datetime.now().isoformat(),
        "priority": "low"
    },
    {
        "id": 2,
        "category": "security",
        "message": "No suspicious network activity detected",
        "confidence": 98,
        "timestamp": datetime.now().isoformat(),
        "priority": "info"
    },
    {
        "id": 3,
        "category": "optimization",
        "message": "Memory allocation could be optimized for better performance",
        "confidence": 87,
        "timestamp": datetime.now().isoformat(),
        "priority": "medium"
    }
]

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

# Initialize AI components if available
aiops_bot = None
hf_engine = None

try:
    if EnhancedAIOpsBot:
        aiops_bot = EnhancedAIOpsBot()
        print("✅ Enhanced AIOps Bot initialized successfully")
    if HuggingFaceAIEngine:
        hf_engine = HuggingFaceAIEngine()
        print("✅ Hugging Face AI Engine initialized successfully")
except Exception as e:
    print(f"⚠️ Warning: Could not initialize AI components: {e}")

def simulate_system_data():
    """Simulate real-time system data updates"""
    global system_data
    while True:
        try:
            # Simulate realistic system metrics with some variation
            system_data.update({
                "cpu": max(0, min(100, system_data["cpu"] + random.uniform(-5, 5))),
                "memory": max(0, min(100, system_data["memory"] + random.uniform(-3, 3))),
                "disk": max(0, min(100, system_data["disk"] + random.uniform(-1, 1))),
                "network_in": max(0, system_data["network_in"] + random.uniform(-20, 20)),
                "network_out": max(0, system_data["network_out"] + random.uniform(-15, 15)),
                "temperature": max(30, min(80, system_data["temperature"] + random.uniform(-2, 2))),
                "last_updated": datetime.now().isoformat()
            })
            
            # Update status based on metrics
            if system_data["cpu"] > 90 or system_data["memory"] > 90 or system_data["temperature"] > 75:
                system_data["status"] = "critical"
            elif system_data["cpu"] > 75 or system_data["memory"] > 80 or system_data["temperature"] > 65:
                system_data["status"] = "warning"
            else:
                system_data["status"] = "healthy"
                
        except Exception as e:
            print(f"Error in system data simulation: {e}")
        
        time.sleep(10)  # Update every 10 seconds

# Start the system data simulation in a background thread
simulation_thread = threading.Thread(target=simulate_system_data, daemon=True)
simulation_thread.start()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api_server": "running",
            "aiops_bot": "running" if aiops_bot else "unavailable",
            "hf_engine": "running" if hf_engine else "unavailable"
        }
    })

@app.route('/api/system', methods=['GET'])
def get_system_data():
    """Get current system metrics"""
    return jsonify(system_data)

@app.route('/api/insights', methods=['GET'])
def get_ai_insights():
    """Get AI-generated insights"""
    return jsonify(ai_insights)

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts"""
    return jsonify(recent_alerts)

@app.route('/api/chat', methods=['POST'])
def chat_with_ai():
    """Chat with the AI assistant"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        if not message:
            return jsonify({"error": "Message is required"}), 400
        
        # Try to use the actual AI bot if available
        if aiops_bot:
            try:
                response = aiops_bot.process_message(message)
                return jsonify({
                    "response": response,
                    "timestamp": datetime.now().isoformat(),
                    "source": "enhanced_aiops_bot"
                })
            except Exception as e:
                print(f"Error with AIOps bot: {e}")
        
        # Fallback responses
        fallback_responses = [
            "I'm monitoring your systems and everything looks good! 📊",
            "Your system performance is within normal parameters. How can I help you optimize further? 🔧",
            "I've analyzed the current metrics - no issues detected. What would you like to know? 🤖",
            "System health is excellent! I'm here to help with any AIOps questions you have. 💡",
            "All services are running smoothly. Feel free to ask about performance optimization or monitoring! 📈"
        ]
        
        response = random.choice(fallback_responses)
        
        return jsonify({
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "source": "fallback_bot"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Mirror plain routes for proxy compatibility
@app.route('/chat', methods=['POST'])
def chat_plain():
    return chat_with_ai()

@app.route('/chat/stream', methods=['POST'])
def chat_stream_plain():
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', '')
        if not message:
            return jsonify({"error": "Message is required"}), 400

        # Generate the same response as chat_with_ai (could be replaced with true model stream)
        resp = chat_with_ai().get_json()
        text = str(resp.get('response', ''))

        def generate():
            import re
            parts = re.split(r'(\s+)', text)
            for part in parts:
                if not part:
                    continue
                yield f"data: {part}\n\n"
                time.sleep(0.01)
            yield "event: done\n"
            yield "data: [DONE]\n\n"

        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'text/event-stream',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
        return Response(generate(), headers=headers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_with_ai():
    """Analyze text with Hugging Face AI"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        analysis_type = data.get('type', 'sentiment')
        
        if not text:
            return jsonify({"error": "Text is required"}), 400
        
        if hf_engine:
            try:
                if analysis_type == 'sentiment':
                    result = hf_engine.analyze_sentiment(text)
                elif analysis_type == 'classification':
                    result = hf_engine.classify_issue(text)
                elif analysis_type == 'summarization':
                    result = hf_engine.summarize_logs(text)
                else:
                    result = {"error": "Unsupported analysis type"}
                
                return jsonify({
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                    "analysis_type": analysis_type
                })
            except Exception as e:
                return jsonify({"error": f"AI analysis failed: {str(e)}"}), 500
        else:
            return jsonify({"error": "Hugging Face AI engine not available"}), 503
            
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
    print("  • POST /api/analyze    - AI text analysis")
    print("  • GET  /api/performance - Performance data")
    print("\n✨ Ready to serve your AIOps dashboard!")
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)