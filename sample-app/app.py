import math
import random
import threading
import time
from datetime import datetime

import psutil
from flask import Flask, Response, jsonify
from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Gauge, Histogram,
                               generate_latest)

app = Flask(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('sample_app_requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('sample_app_request_duration_seconds', 'Request duration')
CPU_USAGE = Gauge('sample_app_cpu_usage_percent', 'CPU usage percentage')
MEMORY_USAGE = Gauge('sample_app_memory_usage_percent', 'Memory usage percentage')
RESPONSE_TIME = Gauge('sample_app_response_time_seconds', 'Response time in seconds')
ERROR_COUNT = Counter('sample_app_errors_total', 'Total errors', ['type'])
ACTIVE_CONNECTIONS = Gauge('sample_app_active_connections', 'Active connections')

# Simulate varying load patterns
load_multiplier = 1.0
connection_count = 0

def simulate_system_metrics():
    """Background thread to simulate realistic system metrics"""
    global load_multiplier, connection_count
    
    while True:
        try:
            # Get real system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            # Add some realistic variations
            hour = datetime.now().hour
            
            # Business hours simulation (9 AM - 6 PM = higher load)
            if 9 <= hour <= 18:
                load_multiplier = random.uniform(1.2, 2.5)
            else:
                load_multiplier = random.uniform(0.3, 1.0)
            
            # Add some noise and spikes
            cpu_variation = random.uniform(-10, 15)
            memory_variation = random.uniform(-5, 10)
            
            # Simulate occasional spikes (5% chance)
            if random.random() < 0.05:
                cpu_variation += random.uniform(20, 40)
                memory_variation += random.uniform(10, 25)
            
            # Update metrics with realistic bounds
            CPU_USAGE.set(max(0, min(100, cpu_percent + cpu_variation)))
            MEMORY_USAGE.set(max(0, min(100, memory_percent + memory_variation)))
            
            # Simulate varying connection count
            if random.random() < 0.3:  # 30% chance to change connections
                connection_count += random.randint(-5, 10)
                connection_count = max(0, min(500, connection_count))
            ACTIVE_CONNECTIONS.set(connection_count)
            
        except Exception as e:
            print(f"Error updating system metrics: {e}")
        
        time.sleep(5)  # Update every 5 seconds

# Start background metrics thread
metrics_thread = threading.Thread(target=simulate_system_metrics, daemon=True)
metrics_thread.start()

@app.route('/')
def index():
    global connection_count
    start_time = time.time()
    
    REQUEST_COUNT.labels(method='GET', endpoint='/').inc()
    connection_count += 1
    ACTIVE_CONNECTIONS.set(connection_count)
    
    # Simulate varying response times based on load
    base_work = int(100000 * load_multiplier)
    work_variation = random.randint(0, base_work // 2)
    
    # Simulate CPU work with realistic patterns
    work_iterations = base_work + work_variation
    [random.random() ** 2 for _ in range(work_iterations)]
    
    # Occasionally simulate slow responses (2% chance)
    if random.random() < 0.02:
        time.sleep(random.uniform(1, 3))
    
    duration = time.time() - start_time
    REQUEST_DURATION.observe(duration)
    RESPONSE_TIME.set(duration)
    
    connection_count = max(0, connection_count - 1)
    
    return f'Hello, World! (Load: {load_multiplier:.1f}x, Duration: {duration:.3f}s)'

@app.route('/api/data')
def api_data():
    start_time = time.time()
    
    REQUEST_COUNT.labels(method='GET', endpoint='/api/data').inc()
    
    # Simulate database query time
    query_time = random.uniform(0.01, 0.2)
    time.sleep(query_time)
    
    # Simulate occasional API errors (1% chance)
    if random.random() < 0.01:
        ERROR_COUNT.labels(type='database_timeout').inc()
        return jsonify({"error": "Database timeout"}), 500
    
    # Simulate processing work
    [math.sqrt(random.random()) for _ in range(int(50000 * load_multiplier))]
    
    duration = time.time() - start_time
    REQUEST_DURATION.observe(duration)
    RESPONSE_TIME.set(duration)
    
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "data": [random.randint(1, 100) for _ in range(10)],
        "query_time": query_time,
        "load_factor": load_multiplier
    })

@app.route('/health')
def health():
    REQUEST_COUNT.labels(method='GET', endpoint='/health').inc()
    
    # Simulate health check logic
    cpu_ok = CPU_USAGE._value.get() < 90
    memory_ok = MEMORY_USAGE._value.get() < 85
    
    status = "healthy" if cpu_ok and memory_ok else "degraded"
    
    return jsonify({
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "cpu_usage": CPU_USAGE._value.get(),
        "memory_usage": MEMORY_USAGE._value.get(),
        "active_connections": ACTIVE_CONNECTIONS._value.get()
    })

@app.route('/load/<factor>')
def set_load(factor):
    """Endpoint to manually adjust load for testing"""
    global load_multiplier
    try:
        load_multiplier = float(factor)
        return f'Load multiplier set to {load_multiplier}x'
    except ValueError:
        return 'Invalid load factor', 400

@app.route('/error')
def trigger_error():
    """Endpoint to trigger errors for testing"""
    REQUEST_COUNT.labels(method='GET', endpoint='/error').inc()
    ERROR_COUNT.labels(type='intentional').inc()
    return 'Error triggered', 500

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    print("🚀 Enhanced Sample App with Realistic Metrics")
    print("📊 Available endpoints:")
    print("   / - Main endpoint with load simulation")
    print("   /api/data - API endpoint with database simulation")
    print("   /health - Health check endpoint")
    print("   /load/<factor> - Set load multiplier (e.g. /load/2.5)")
    print("   /error - Trigger error for testing")
    print("   /metrics - Prometheus metrics")
    print("🔧 Generating realistic CPU, memory, and response time patterns")
    app.run(host='0.0.0.0', port=5000)
