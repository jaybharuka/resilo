#!/usr/bin/env python3
"""
Live Computer Monitor - Real-time system monitoring with spike detection
Monitors your actual computer stats and sends alerts for unusual activity
"""

import json
import os
import statistics
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta

import psutil

# Add project paths
sys.path.append('.')
sys.path.append('./bot')

class LiveComputerMonitor:
    """Real-time computer monitoring with intelligent spike detection"""
    
    def __init__(self, check_interval: int = 5):
        self.check_interval = check_interval  # seconds
        self.monitoring = False
        self.monitor_thread = None
        
        # Store recent values for trend analysis (last 5 minutes)
        self.history_size = 60  # 5 minutes at 5-second intervals
        self.cpu_history = deque(maxlen=self.history_size)
        self.memory_history = deque(maxlen=self.history_size)
        self.disk_history = deque(maxlen=self.history_size)
        self.network_sent_history = deque(maxlen=self.history_size)
        self.network_recv_history = deque(maxlen=self.history_size)
        
        # Previous network stats for rate calculation
        self.prev_network_stats = None
        
        # Alert thresholds (will be dynamic)
        self.thresholds = {
            'cpu': {'warning': 70, 'critical': 85, 'spike': 20},  # spike = sudden increase
            'memory': {'warning': 80, 'critical': 90, 'spike': 15},
            'disk': {'warning': 85, 'critical': 95, 'spike': 10},
            'network_sent': {'spike': 5000000},  # 5 MB/s spike
            'network_recv': {'spike': 10000000}  # 10 MB/s spike
        }
        
        # Load analytics service if available
        try:
            from bot.analytics_service import get_analytics_service
            self.analytics = get_analytics_service()
            print("🧠 Analytics service loaded - using adaptive thresholds")
        except Exception as e:
            print(f"⚠️ Analytics service not available: {e}")
            self.analytics = None
        
        print("🖥️ Live Computer Monitor initialized")
        print(f"📊 Monitoring interval: {check_interval} seconds")
    
    def get_current_stats(self) -> dict:
        """Get current system statistics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk usage (C: drive)
            disk = psutil.disk_usage('C:')
            disk_percent = disk.percent
            
            # Network usage
            network = psutil.net_io_counters()
            
            # Calculate network rates if we have previous data
            network_sent_rate = 0
            network_recv_rate = 0
            
            if self.prev_network_stats:
                time_diff = self.check_interval
                sent_diff = network.bytes_sent - self.prev_network_stats.bytes_sent
                recv_diff = network.bytes_recv - self.prev_network_stats.bytes_recv
                
                network_sent_rate = sent_diff / time_diff  # bytes per second
                network_recv_rate = recv_diff / time_diff
            
            self.prev_network_stats = network
            
            # Process information
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    if proc.info['cpu_percent'] > 5 or proc.info['memory_percent'] > 5:
                        processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Sort by CPU usage
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            
            return {
                'timestamp': datetime.now(),
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'memory_available_gb': memory.available / (1024**3),
                'memory_total_gb': memory.total / (1024**3),
                'disk_percent': disk_percent,
                'disk_free_gb': disk.free / (1024**3),
                'disk_total_gb': disk.total / (1024**3),
                'network_sent_rate': network_sent_rate,
                'network_recv_rate': network_recv_rate,
                'network_sent_total': network.bytes_sent,
                'network_recv_total': network.bytes_recv,
                'top_processes': processes[:5]  # Top 5 resource-consuming processes
            }
            
        except Exception as e:
            print(f"❌ Error getting system stats: {e}")
            return None
    
    def update_dynamic_thresholds(self):
        """Update thresholds based on historical data and ML if available"""
        try:
            if len(self.cpu_history) < 10:  # Need some history
                return
            
            # Calculate dynamic thresholds based on recent history
            cpu_values = list(self.cpu_history)
            memory_values = list(self.memory_history)
            
            cpu_mean = statistics.mean(cpu_values)
            cpu_stdev = statistics.stdev(cpu_values) if len(cpu_values) > 1 else 5
            
            memory_mean = statistics.mean(memory_values)
            memory_stdev = statistics.stdev(memory_values) if len(memory_values) > 1 else 5
            
            # Dynamic thresholds: mean + 2*stdev for warning, mean + 3*stdev for critical
            self.thresholds['cpu']['warning'] = min(85, max(50, cpu_mean + 2 * cpu_stdev))
            self.thresholds['cpu']['critical'] = min(95, max(70, cpu_mean + 3 * cpu_stdev))
            self.thresholds['cpu']['spike'] = max(10, cpu_stdev * 2)
            
            self.thresholds['memory']['warning'] = min(90, max(60, memory_mean + 2 * memory_stdev))
            self.thresholds['memory']['critical'] = min(95, max(80, memory_mean + 3 * memory_stdev))
            self.thresholds['memory']['spike'] = max(5, memory_stdev * 2)
            
            print(f"🎯 Dynamic thresholds updated:")
            print(f"   CPU: Warning={self.thresholds['cpu']['warning']:.1f}%, Critical={self.thresholds['cpu']['critical']:.1f}%, Spike={self.thresholds['cpu']['spike']:.1f}%")
            print(f"   Memory: Warning={self.thresholds['memory']['warning']:.1f}%, Critical={self.thresholds['memory']['critical']:.1f}%, Spike={self.thresholds['memory']['spike']:.1f}%")
            
        except Exception as e:
            print(f"❌ Error updating dynamic thresholds: {e}")
    
    def detect_spikes_and_alerts(self, current_stats: dict) -> list:
        """Detect spikes and generate alerts"""
        alerts = []
        
        try:
            cpu = current_stats['cpu_percent']
            memory = current_stats['memory_percent']
            disk = current_stats['disk_percent']
            
            # Add to history
            self.cpu_history.append(cpu)
            self.memory_history.append(memory)
            self.disk_history.append(disk)
            
            # Check for threshold violations
            alerts.extend(self._check_threshold_alerts(current_stats))
            
            # Check for spikes (sudden increases)
            alerts.extend(self._check_spike_alerts(current_stats))
            
            # Check for anomalies using ML if available
            if self.analytics and len(self.cpu_history) >= 20:
                alerts.extend(self._check_ml_anomalies(current_stats))
            
            return alerts
            
        except Exception as e:
            print(f"❌ Error detecting alerts: {e}")
            return []
    
    def _check_threshold_alerts(self, stats: dict) -> list:
        """Check for threshold-based alerts"""
        alerts = []
        
        # CPU alerts
        cpu = stats['cpu_percent']
        if cpu >= self.thresholds['cpu']['critical']:
            alerts.append({
                'type': 'threshold',
                'severity': 'critical',
                'metric': 'CPU',
                'value': cpu,
                'threshold': self.thresholds['cpu']['critical'],
                'message': f"🔥 CRITICAL: CPU usage at {cpu:.1f}% (threshold: {self.thresholds['cpu']['critical']:.1f}%)",
                'timestamp': stats['timestamp']
            })
        elif cpu >= self.thresholds['cpu']['warning']:
            alerts.append({
                'type': 'threshold',
                'severity': 'warning',
                'metric': 'CPU',
                'value': cpu,
                'threshold': self.thresholds['cpu']['warning'],
                'message': f"⚠️ WARNING: CPU usage at {cpu:.1f}% (threshold: {self.thresholds['cpu']['warning']:.1f}%)",
                'timestamp': stats['timestamp']
            })
        
        # Memory alerts
        memory = stats['memory_percent']
        if memory >= self.thresholds['memory']['critical']:
            alerts.append({
                'type': 'threshold',
                'severity': 'critical',
                'metric': 'Memory',
                'value': memory,
                'threshold': self.thresholds['memory']['critical'],
                'message': f"🔥 CRITICAL: Memory usage at {memory:.1f}% (threshold: {self.thresholds['memory']['critical']:.1f}%)",
                'timestamp': stats['timestamp']
            })
        elif memory >= self.thresholds['memory']['warning']:
            alerts.append({
                'type': 'threshold',
                'severity': 'warning',
                'metric': 'Memory',
                'value': memory,
                'threshold': self.thresholds['memory']['warning'],
                'message': f"⚠️ WARNING: Memory usage at {memory:.1f}% (threshold: {self.thresholds['memory']['warning']:.1f}%)",
                'timestamp': stats['timestamp']
            })
        
        # Disk alerts
        disk = stats['disk_percent']
        if disk >= self.thresholds['disk']['critical']:
            alerts.append({
                'type': 'threshold',
                'severity': 'critical',
                'metric': 'Disk',
                'value': disk,
                'threshold': self.thresholds['disk']['critical'],
                'message': f"🔥 CRITICAL: Disk usage at {disk:.1f}% (threshold: {self.thresholds['disk']['critical']:.1f}%)",
                'timestamp': stats['timestamp']
            })
        elif disk >= self.thresholds['disk']['warning']:
            alerts.append({
                'type': 'threshold',
                'severity': 'warning',
                'metric': 'Disk',
                'value': disk,
                'threshold': self.thresholds['disk']['warning'],
                'message': f"⚠️ WARNING: Disk usage at {disk:.1f}% (threshold: {self.thresholds['disk']['warning']:.1f}%)",
                'timestamp': stats['timestamp']
            })
        
        return alerts
    
    def _check_spike_alerts(self, stats: dict) -> list:
        """Check for spike alerts (sudden increases)"""
        alerts = []
        
        if len(self.cpu_history) < 3:  # Need some history for comparison
            return alerts
        
        try:
            # Check CPU spike
            recent_cpu_avg = statistics.mean(list(self.cpu_history)[-3:])  # Last 3 readings
            older_cpu_avg = statistics.mean(list(self.cpu_history)[-6:-3]) if len(self.cpu_history) >= 6 else recent_cpu_avg
            
            cpu_increase = recent_cpu_avg - older_cpu_avg
            if cpu_increase >= self.thresholds['cpu']['spike']:
                alerts.append({
                    'type': 'spike',
                    'severity': 'warning',
                    'metric': 'CPU',
                    'value': stats['cpu_percent'],
                    'spike_amount': cpu_increase,
                    'message': f"📈 SPIKE: CPU usage increased by {cpu_increase:.1f}% (current: {stats['cpu_percent']:.1f}%)",
                    'timestamp': stats['timestamp']
                })
            
            # Check Memory spike
            recent_memory_avg = statistics.mean(list(self.memory_history)[-3:])
            older_memory_avg = statistics.mean(list(self.memory_history)[-6:-3]) if len(self.memory_history) >= 6 else recent_memory_avg
            
            memory_increase = recent_memory_avg - older_memory_avg
            if memory_increase >= self.thresholds['memory']['spike']:
                alerts.append({
                    'type': 'spike',
                    'severity': 'warning',
                    'metric': 'Memory',
                    'value': stats['memory_percent'],
                    'spike_amount': memory_increase,
                    'message': f"📈 SPIKE: Memory usage increased by {memory_increase:.1f}% (current: {stats['memory_percent']:.1f}%)",
                    'timestamp': stats['timestamp']
                })
            
            # Check Network spikes
            if stats['network_sent_rate'] > self.thresholds['network_sent']['spike']:
                alerts.append({
                    'type': 'spike',
                    'severity': 'info',
                    'metric': 'Network Upload',
                    'value': stats['network_sent_rate'] / (1024*1024),  # Convert to MB/s
                    'message': f"📡 SPIKE: High network upload {stats['network_sent_rate']/(1024*1024):.1f} MB/s",
                    'timestamp': stats['timestamp']
                })
            
            if stats['network_recv_rate'] > self.thresholds['network_recv']['spike']:
                alerts.append({
                    'type': 'spike',
                    'severity': 'info',
                    'metric': 'Network Download',
                    'value': stats['network_recv_rate'] / (1024*1024),  # Convert to MB/s
                    'message': f"📡 SPIKE: High network download {stats['network_recv_rate']/(1024*1024):.1f} MB/s",
                    'timestamp': stats['timestamp']
                })
            
        except Exception as e:
            print(f"❌ Error checking spikes: {e}")
        
        return alerts
    
    def _check_ml_anomalies(self, stats: dict) -> list:
        """Check for ML-detected anomalies"""
        alerts = []
        
        try:
            if not self.analytics:
                return alerts
            
            # Create data for ML analysis
            import pandas as pd

            # CPU anomaly detection
            cpu_data = pd.DataFrame({
                'timestamp': [stats['timestamp']],
                'value': [stats['cpu_percent']]
            })
            
            cpu_result = self.analytics.detect_anomalies('cpu_percent', cpu_data)
            if cpu_result.get('anomaly_detected') and cpu_result.get('confidence', 0) > 0.7:
                alerts.append({
                    'type': 'ml_anomaly',
                    'severity': 'warning',
                    'metric': 'CPU',
                    'value': stats['cpu_percent'],
                    'confidence': cpu_result.get('confidence', 0),
                    'message': f"🤖 ML ANOMALY: CPU behavior unusual (confidence: {cpu_result.get('confidence', 0):.1%})",
                    'timestamp': stats['timestamp']
                })
            
            # Memory anomaly detection
            memory_data = pd.DataFrame({
                'timestamp': [stats['timestamp']],
                'value': [stats['memory_percent']]
            })
            
            memory_result = self.analytics.detect_anomalies('memory_percent', memory_data)
            if memory_result.get('anomaly_detected') and memory_result.get('confidence', 0) > 0.7:
                alerts.append({
                    'type': 'ml_anomaly',
                    'severity': 'warning',
                    'metric': 'Memory',
                    'value': stats['memory_percent'],
                    'confidence': memory_result.get('confidence', 0),
                    'message': f"🤖 ML ANOMALY: Memory behavior unusual (confidence: {memory_result.get('confidence', 0):.1%})",
                    'timestamp': stats['timestamp']
                })
            
        except Exception as e:
            print(f"❌ Error in ML anomaly detection: {e}")
        
        return alerts
    
    def print_current_status(self, stats: dict, alerts: list):
        """Print current system status"""
        timestamp = stats['timestamp'].strftime("%H:%M:%S")
        
        print(f"\n📊 [{timestamp}] System Status:")
        print(f"   🖥️ CPU: {stats['cpu_percent']:5.1f}%")
        print(f"   💾 Memory: {stats['memory_percent']:5.1f}% ({stats['memory_available_gb']:.1f}GB free)")
        print(f"   💿 Disk: {stats['disk_percent']:5.1f}% ({stats['disk_free_gb']:.1f}GB free)")
        print(f"   📡 Network: ↑{stats['network_sent_rate']/(1024*1024):5.1f}MB/s ↓{stats['network_recv_rate']/(1024*1024):5.1f}MB/s")
        
        # Show top processes if CPU > 10%
        if stats['cpu_percent'] > 10 and stats['top_processes']:
            print(f"   🔥 Top processes:")
            for proc in stats['top_processes'][:3]:
                print(f"      {proc['name'][:20]:20} CPU:{proc['cpu_percent']:5.1f}% MEM:{proc['memory_percent']:5.1f}%")
        
        # Show alerts
        if alerts:
            print(f"   🚨 ALERTS ({len(alerts)}):")
            for alert in alerts:
                print(f"      {alert['message']}")
        else:
            print(f"   ✅ No alerts")
    
    def monitoring_loop(self):
        """Main monitoring loop"""
        print(f"🔄 Starting live monitoring (interval: {self.check_interval}s)")
        print("⏹️ Press Ctrl+C to stop")
        
        loop_count = 0
        
        while self.monitoring:
            try:
                # Get current stats
                stats = self.get_current_stats()
                if not stats:
                    time.sleep(self.check_interval)
                    continue
                
                # Detect alerts
                alerts = self.detect_spikes_and_alerts(stats)
                
                # Print status
                self.print_current_status(stats, alerts)
                
                # Update dynamic thresholds every 20 loops (about 2 minutes)
                loop_count += 1
                if loop_count % 20 == 0:
                    self.update_dynamic_thresholds()
                
                # Sleep until next check
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                print("\n⏹️ Monitoring stopped by user")
                self.monitoring = False
                break
            except Exception as e:
                print(f"❌ Error in monitoring loop: {e}")
                time.sleep(self.check_interval)
    
    def start_monitoring(self):
        """Start monitoring in background thread"""
        if self.monitoring:
            print("⚠️ Monitoring already running")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitor_thread.start()
        print("🚀 Live monitoring started in background")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        print("⏹️ Live monitoring stopped")

def main():
    """Main function for live monitoring"""
    print("🖥️ Live Computer Monitor - Real-time System Monitoring")
    print("=" * 60)
    
    # Create monitor
    monitor = LiveComputerMonitor(check_interval=5)
    
    try:
        # Start monitoring
        monitor.monitoring_loop()
        
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()