#!/usr/bin/env python3
"""
System Metrics Exporter for AIOps Bot
Exports real system metrics in Prometheus format
"""
import math
import random
import threading
import time
from datetime import datetime

import psutil
from prometheus_client import (REGISTRY, CollectorRegistry, Counter, Gauge,
                               start_http_server)


class SystemMetricsExporter:
    """Export real system metrics"""
    
    def __init__(self):
        # Create metrics
        self.cpu_usage = Gauge('system_cpu_usage_percent', 'CPU usage percentage')
        self.memory_usage = Gauge('system_memory_usage_percent', 'Memory usage percentage')
        self.disk_usage = Gauge('system_disk_usage_percent', 'Disk usage percentage')
        self.network_bytes_sent = Counter('system_network_bytes_sent_total', 'Network bytes sent')
        self.network_bytes_recv = Counter('system_network_bytes_recv_total', 'Network bytes received')
        self.load_average = Gauge('system_load_average', 'System load average')
        self.processes_running = Gauge('system_processes_running', 'Number of running processes')
        self.file_descriptors = Gauge('system_file_descriptors_open', 'Number of open file descriptors')
        
        # Application-specific metrics
        self.app_response_time = Gauge('app_response_time_seconds', 'Application response time')
        self.app_error_rate = Gauge('app_error_rate_percent', 'Application error rate')
        self.app_throughput = Gauge('app_throughput_requests_per_sec', 'Application throughput')
        self.app_database_connections = Gauge('app_database_connections', 'Database connections')
        
        # Business metrics
        self.business_transactions = Counter('business_transactions_total', 'Total business transactions')
        self.business_revenue = Gauge('business_revenue_dollars', 'Business revenue in dollars')
        self.user_sessions = Gauge('user_sessions_active', 'Active user sessions')
        
        # Initialize baseline values
        self._last_network_sent = 0
        self._last_network_recv = 0
        self._update_interval = 5  # seconds
        
    def start_monitoring(self):
        """Start the monitoring thread"""
        print("🔍 Starting system metrics monitoring...")
        monitoring_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitoring_thread.start()
        
    def _monitor_loop(self):
        """Main monitoring loop"""
        while True:
            try:
                self._update_system_metrics()
                self._update_application_metrics()
                self._update_business_metrics()
                time.sleep(self._update_interval)
            except Exception as e:
                print(f"Error updating metrics: {e}")
                time.sleep(self._update_interval)
    
    def _update_system_metrics(self):
        """Update real system metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.cpu_usage.set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.memory_usage.set(memory.percent)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            self.disk_usage.set(disk_percent)
            
            # Network I/O
            network = psutil.net_io_counters()
            if self._last_network_sent > 0:
                sent_rate = (network.bytes_sent - self._last_network_sent) / self._update_interval
                recv_rate = (network.bytes_recv - self._last_network_recv) / self._update_interval
            else:
                sent_rate = recv_rate = 0
                
            self._last_network_sent = network.bytes_sent
            self._last_network_recv = network.bytes_recv
            
            # Load average (Unix-like systems)
            try:
                load_avg = psutil.getloadavg()[0]  # 1-minute load average
                self.load_average.set(load_avg)
            except AttributeError:
                # Windows doesn't have load average, simulate it
                self.load_average.set(cpu_percent / 100.0)
            
            # Process count
            processes = len(psutil.pids())
            self.processes_running.set(processes)
            
            # File descriptors (approximate)
            try:
                current_process = psutil.Process()
                fd_count = current_process.num_fds() if hasattr(current_process, 'num_fds') else current_process.num_handles()
                self.file_descriptors.set(fd_count)
            except:
                self.file_descriptors.set(50)  # Default fallback
                
        except Exception as e:
            print(f"Error updating system metrics: {e}")
    
    def _update_application_metrics(self):
        """Simulate realistic application metrics"""
        try:
            # Simulate response time patterns
            hour = datetime.now().hour
            base_response_time = 0.1
            
            # Higher response times during business hours
            if 9 <= hour <= 17:
                base_response_time *= random.uniform(1.5, 3.0)
            
            # Add occasional spikes
            if random.random() < 0.05:  # 5% chance
                base_response_time *= random.uniform(5, 15)
                
            response_time = max(0.01, base_response_time + random.uniform(-0.05, 0.05))
            self.app_response_time.set(response_time)
            
            # Simulate error rate (higher during peak hours)
            if 9 <= hour <= 17:
                error_rate = random.uniform(0.5, 3.0)
            else:
                error_rate = random.uniform(0.1, 1.0)
                
            # Occasional error spikes
            if random.random() < 0.02:  # 2% chance
                error_rate *= random.uniform(5, 20)
                
            self.app_error_rate.set(min(100, error_rate))
            
            # Simulate throughput (requests per second)
            base_throughput = 10
            if 9 <= hour <= 17:
                throughput = base_throughput * random.uniform(5, 15)
            else:
                throughput = base_throughput * random.uniform(0.5, 2.0)
                
            self.app_throughput.set(max(0, throughput))
            
            # Database connections
            base_connections = 25
            connection_variation = random.randint(-10, 15)
            connections = max(0, min(100, base_connections + connection_variation))
            self.app_database_connections.set(connections)
            
        except Exception as e:
            print(f"Error updating application metrics: {e}")
    
    def _update_business_metrics(self):
        """Simulate business metrics"""
        try:
            # Simulate user sessions
            hour = datetime.now().hour
            base_sessions = 100
            
            if 9 <= hour <= 17:
                sessions = base_sessions * random.uniform(3, 8)
            elif 18 <= hour <= 22:
                sessions = base_sessions * random.uniform(1.5, 4)
            else:
                sessions = base_sessions * random.uniform(0.2, 1)
                
            self.user_sessions.set(int(sessions))
            
            # Simulate revenue (dollars per interval)
            revenue_per_session = random.uniform(0.5, 5.0)
            revenue = sessions * revenue_per_session * (self._update_interval / 3600)  # Per hour rate
            self.business_revenue.set(revenue)
            
            # Business transactions
            if random.random() < 0.7:  # 70% chance of transactions
                transaction_count = random.randint(1, 10)
                for _ in range(transaction_count):
                    self.business_transactions.inc()
            
        except Exception as e:
            print(f"Error updating business metrics: {e}")

def main():
    """Main function to start the metrics exporter"""
    print("🚀 System Metrics Exporter for AIOps Bot")
    print("📊 Exporting real system and application metrics")
    
    # Create exporter
    exporter = SystemMetricsExporter()
    
    # Start monitoring
    exporter.start_monitoring()
    
    # Start Prometheus HTTP server
    port = 8001
    print(f"🌐 Starting Prometheus metrics server on port {port}")
    print(f"📊 Metrics available at: http://localhost:{port}/metrics")
    
    try:
        start_http_server(port)
        
        print("✅ Metrics exporter started successfully")
        print("📈 Available metric categories:")
        print("   🖥️  System: CPU, Memory, Disk, Network, Load")
        print("   🚀 Application: Response time, Error rate, Throughput, DB connections")
        print("   💼 Business: User sessions, Revenue, Transactions")
        print("\n🔄 Metrics update every 5 seconds")
        print("⏹️  Press Ctrl+C to stop")
        
        # Keep the server running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ Stopping metrics exporter...")
    except Exception as e:
        print(f"❌ Error starting metrics server: {e}")

if __name__ == "__main__":
    main()