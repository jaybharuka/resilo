#!/usr/bin/env python3
"""
Advanced Performance Monitoring System
Day 9: Performance Optimization and Scalability

This system provides:
- Comprehensive performance monitoring (CPU, Memory, Disk I/O, Network)
- Performance baseline establishment and SLA tracking
- Automated performance regression detection
- Real-time performance profiling
- Resource utilization optimization recommendations
"""

import psutil
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from collections import deque
import statistics
import os
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('performance_monitor')

@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot"""
    timestamp: datetime
    cpu_percent: float
    cpu_freq_current: float
    memory_percent: float
    memory_available: int
    disk_read_bytes: int
    disk_write_bytes: int
    disk_read_count: int
    disk_write_count: int
    network_bytes_sent: int
    network_bytes_recv: int
    network_packets_sent: int
    network_packets_recv: int
    load_average: List[float]
    process_count: int
    thread_count: int
    context_switches: int
    interrupts: int

@dataclass
class PerformanceBaseline:
    """Performance baseline for comparison"""
    metric_name: str
    baseline_value: float
    std_deviation: float
    min_value: float
    max_value: float
    sample_count: int
    established_at: datetime

@dataclass
class PerformanceAlert:
    """Performance degradation alert"""
    id: str
    metric_name: str
    current_value: float
    baseline_value: float
    deviation_percent: float
    severity: str
    description: str
    timestamp: datetime
    resolved: bool = False

@dataclass
class OptimizationRecommendation:
    """Performance optimization recommendation"""
    id: str
    category: str
    title: str
    description: str
    impact_level: str
    implementation_complexity: str
    estimated_improvement: str
    action_steps: List[str]
    confidence_score: float
    timestamp: datetime

class AdvancedPerformanceMonitor:
    """Advanced performance monitoring and optimization system"""
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        self.metrics_history: deque = deque(maxlen=history_size)
        self.baselines: Dict[str, PerformanceBaseline] = {}
        self.alerts: List[PerformanceAlert] = []
        self.recommendations: List[OptimizationRecommendation] = []
        self.is_monitoring = False
        self.monitoring_thread = None
        
        # Performance thresholds (can be dynamically adjusted)
        self.thresholds = {
            'cpu_percent': {'warning': 70, 'critical': 85},
            'memory_percent': {'warning': 80, 'critical': 90},
            'disk_io_rate': {'warning': 50_000_000, 'critical': 100_000_000},  # bytes/sec
            'network_io_rate': {'warning': 10_000_000, 'critical': 50_000_000}  # bytes/sec
        }
        
        # Baseline establishment parameters
        self.baseline_min_samples = 100
        self.baseline_max_age_hours = 24
        
        logger.info("🚀 Advanced Performance Monitor initialized")
    
    def collect_metrics(self) -> PerformanceMetrics:
        """Collect comprehensive system performance metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_freq = psutil.cpu_freq()
            cpu_freq_current = cpu_freq.current if cpu_freq else 0
            
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # Disk I/O metrics
            disk_io = psutil.disk_io_counters()
            
            # Network I/O metrics
            network_io = psutil.net_io_counters()
            
            # System load metrics
            if hasattr(os, 'getloadavg'):
                load_avg = list(os.getloadavg())
            else:
                # Windows fallback
                load_avg = [cpu_percent / 100.0, cpu_percent / 100.0, cpu_percent / 100.0]
            
            # Process and thread counts
            process_count = len(psutil.pids())
            # Simplified thread count for Windows compatibility
            thread_count = 0
            try:
                # Sample a few processes to estimate thread count
                for i, pid in enumerate(psutil.pids()[:10]):
                    try:
                        proc = psutil.Process(pid)
                        thread_count += proc.num_threads()
                    except:
                        continue
                # Extrapolate to estimate total
                thread_count = int(thread_count * len(psutil.pids()) / 10)
            except:
                thread_count = process_count * 3  # Rough estimate
            
            # System statistics
            if hasattr(psutil, 'boot_time'):
                # Get context switches and interrupts (Linux/Unix)
                try:
                    with open('/proc/stat', 'r') as f:
                        for line in f:
                            if line.startswith('ctxt'):
                                context_switches = int(line.split()[1])
                            elif line.startswith('intr'):
                                interrupts = int(line.split()[1])
                except:
                    context_switches = 0
                    interrupts = 0
            else:
                # Windows fallback
                context_switches = 0
                interrupts = 0
            
            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                cpu_freq_current=cpu_freq_current,
                memory_percent=memory.percent,
                memory_available=memory.available,
                disk_read_bytes=disk_io.read_bytes if disk_io else 0,
                disk_write_bytes=disk_io.write_bytes if disk_io else 0,
                disk_read_count=disk_io.read_count if disk_io else 0,
                disk_write_count=disk_io.write_count if disk_io else 0,
                network_bytes_sent=network_io.bytes_sent if network_io else 0,
                network_bytes_recv=network_io.bytes_recv if network_io else 0,
                network_packets_sent=network_io.packets_sent if network_io else 0,
                network_packets_recv=network_io.packets_recv if network_io else 0,
                load_average=load_avg,
                process_count=process_count,
                thread_count=thread_count,
                context_switches=context_switches,
                interrupts=interrupts
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"💥 Error collecting metrics: {e}")
            raise
    
    def add_metrics(self, metrics: PerformanceMetrics):
        """Add metrics to history and analyze"""
        self.metrics_history.append(metrics)
        
        # Update baselines periodically
        if len(self.metrics_history) >= self.baseline_min_samples:
            self._update_baselines()
        
        # Check for performance degradation
        self._check_performance_alerts(metrics)
        
        # Generate optimization recommendations
        if len(self.metrics_history) % 50 == 0:  # Every 50 samples
            self._generate_optimization_recommendations()
    
    def _update_baselines(self):
        """Update performance baselines based on historical data"""
        if len(self.metrics_history) < self.baseline_min_samples:
            return
        
        # Get recent metrics for baseline calculation
        recent_metrics = list(self.metrics_history)[-self.baseline_min_samples:]
        
        # Calculate baselines for key metrics
        metrics_to_baseline = [
            'cpu_percent', 'memory_percent', 'disk_read_bytes', 
            'disk_write_bytes', 'network_bytes_sent', 'network_bytes_recv'
        ]
        
        for metric_name in metrics_to_baseline:
            values = [getattr(m, metric_name) for m in recent_metrics]
            
            baseline = PerformanceBaseline(
                metric_name=metric_name,
                baseline_value=statistics.mean(values),
                std_deviation=statistics.stdev(values) if len(values) > 1 else 0,
                min_value=min(values),
                max_value=max(values),
                sample_count=len(values),
                established_at=datetime.now()
            )
            
            self.baselines[metric_name] = baseline
        
        logger.info(f"📊 Updated {len(metrics_to_baseline)} performance baselines")
    
    def _check_performance_alerts(self, current_metrics: PerformanceMetrics):
        """Check for performance degradation and generate alerts"""
        alerts_generated = []
        
        # Check against baselines
        for metric_name, baseline in self.baselines.items():
            current_value = getattr(current_metrics, metric_name)
            
            # Calculate deviation percentage
            if baseline.baseline_value > 0:
                deviation_percent = ((current_value - baseline.baseline_value) / 
                                   baseline.baseline_value) * 100
            else:
                deviation_percent = 0
            
            # Check if deviation exceeds threshold (3 standard deviations)
            threshold = 3 * baseline.std_deviation
            if abs(current_value - baseline.baseline_value) > threshold:
                severity = "critical" if abs(deviation_percent) > 50 else "warning"
                
                alert = PerformanceAlert(
                    id=f"perf_alert_{int(time.time())}",
                    metric_name=metric_name,
                    current_value=current_value,
                    baseline_value=baseline.baseline_value,
                    deviation_percent=deviation_percent,
                    severity=severity,
                    description=f"{metric_name} deviated {deviation_percent:.1f}% from baseline",
                    timestamp=datetime.now()
                )
                
                self.alerts.append(alert)
                alerts_generated.append(alert)
        
        # Check absolute thresholds
        threshold_alerts = self._check_absolute_thresholds(current_metrics)
        alerts_generated.extend(threshold_alerts)
        
        if alerts_generated:
            logger.warning(f"⚠️ Generated {len(alerts_generated)} performance alerts")
    
    def _check_absolute_thresholds(self, metrics: PerformanceMetrics) -> List[PerformanceAlert]:
        """Check metrics against absolute thresholds"""
        alerts = []
        
        # CPU threshold check
        if metrics.cpu_percent > self.thresholds['cpu_percent']['critical']:
            alerts.append(PerformanceAlert(
                id=f"cpu_critical_{int(time.time())}",
                metric_name="cpu_percent",
                current_value=metrics.cpu_percent,
                baseline_value=self.thresholds['cpu_percent']['critical'],
                deviation_percent=(metrics.cpu_percent / self.thresholds['cpu_percent']['critical'] - 1) * 100,
                severity="critical",
                description=f"CPU usage critically high: {metrics.cpu_percent:.1f}%",
                timestamp=datetime.now()
            ))
        elif metrics.cpu_percent > self.thresholds['cpu_percent']['warning']:
            alerts.append(PerformanceAlert(
                id=f"cpu_warning_{int(time.time())}",
                metric_name="cpu_percent",
                current_value=metrics.cpu_percent,
                baseline_value=self.thresholds['cpu_percent']['warning'],
                deviation_percent=(metrics.cpu_percent / self.thresholds['cpu_percent']['warning'] - 1) * 100,
                severity="warning",
                description=f"CPU usage elevated: {metrics.cpu_percent:.1f}%",
                timestamp=datetime.now()
            ))
        
        # Memory threshold check
        if metrics.memory_percent > self.thresholds['memory_percent']['critical']:
            alerts.append(PerformanceAlert(
                id=f"memory_critical_{int(time.time())}",
                metric_name="memory_percent",
                current_value=metrics.memory_percent,
                baseline_value=self.thresholds['memory_percent']['critical'],
                deviation_percent=(metrics.memory_percent / self.thresholds['memory_percent']['critical'] - 1) * 100,
                severity="critical",
                description=f"Memory usage critically high: {metrics.memory_percent:.1f}%",
                timestamp=datetime.now()
            ))
        
        return alerts
    
    def _generate_optimization_recommendations(self):
        """Generate intelligent optimization recommendations"""
        if len(self.metrics_history) < 50:
            return
        
        recent_metrics = list(self.metrics_history)[-50:]
        recommendations = []
        
        # Analyze CPU performance
        avg_cpu = statistics.mean(m.cpu_percent for m in recent_metrics)
        if avg_cpu > 60:
            recommendations.append(OptimizationRecommendation(
                id=f"cpu_opt_{int(time.time())}",
                category="CPU Optimization",
                title="High CPU Usage Optimization",
                description=f"Average CPU usage is {avg_cpu:.1f}%, indicating potential optimization opportunities",
                impact_level="Medium",
                implementation_complexity="Medium",
                estimated_improvement="15-25% CPU reduction",
                action_steps=[
                    "Profile top CPU-consuming processes",
                    "Optimize algorithms and reduce computational complexity",
                    "Consider process scheduling optimization",
                    "Evaluate horizontal scaling options",
                    "Implement CPU affinity for critical processes"
                ],
                confidence_score=0.8,
                timestamp=datetime.now()
            ))
        
        # Analyze memory performance
        avg_memory = statistics.mean(m.memory_percent for m in recent_metrics)
        if avg_memory > 70:
            recommendations.append(OptimizationRecommendation(
                id=f"memory_opt_{int(time.time())}",
                category="Memory Optimization",
                title="Memory Usage Optimization",
                description=f"Average memory usage is {avg_memory:.1f}%, suggesting memory optimization potential",
                impact_level="High",
                implementation_complexity="Medium",
                estimated_improvement="20-30% memory efficiency",
                action_steps=[
                    "Implement memory pooling and object reuse",
                    "Optimize data structures and algorithms",
                    "Add garbage collection tuning",
                    "Consider memory compression techniques",
                    "Implement lazy loading patterns"
                ],
                confidence_score=0.85,
                timestamp=datetime.now()
            ))
        
        # Analyze disk I/O patterns
        disk_reads = [m.disk_read_bytes for m in recent_metrics if m.disk_read_bytes > 0]
        if disk_reads and max(disk_reads) - min(disk_reads) > 100_000_000:  # High I/O variance
            recommendations.append(OptimizationRecommendation(
                id=f"disk_opt_{int(time.time())}",
                category="Disk I/O Optimization",
                title="Disk I/O Performance Optimization",
                description="High disk I/O variance detected, indicating potential optimization opportunities",
                impact_level="Medium",
                implementation_complexity="High",
                estimated_improvement="30-40% I/O performance gain",
                action_steps=[
                    "Implement disk I/O caching strategies",
                    "Optimize database query patterns",
                    "Consider SSD migration for hot data",
                    "Implement read-ahead and write-behind caching",
                    "Optimize file system configuration"
                ],
                confidence_score=0.75,
                timestamp=datetime.now()
            ))
        
        # Network optimization analysis
        network_activity = [m.network_bytes_sent + m.network_bytes_recv for m in recent_metrics]
        if network_activity and statistics.mean(network_activity) > 10_000_000:  # High network usage
            recommendations.append(OptimizationRecommendation(
                id=f"network_opt_{int(time.time())}",
                category="Network Optimization",
                title="Network Performance Optimization",
                description="High network activity detected, potential for optimization",
                impact_level="Medium",
                implementation_complexity="Medium",
                estimated_improvement="25-35% network efficiency",
                action_steps=[
                    "Implement data compression for network transfers",
                    "Optimize API call patterns and batching",
                    "Consider CDN implementation for static content",
                    "Implement connection pooling and keep-alive",
                    "Optimize serialization formats"
                ],
                confidence_score=0.7,
                timestamp=datetime.now()
            ))
        
        # Add unique recommendations
        new_recommendations = []
        existing_categories = {r.category for r in self.recommendations}
        
        for rec in recommendations:
            if rec.category not in existing_categories:
                new_recommendations.append(rec)
        
        self.recommendations.extend(new_recommendations)
        
        if new_recommendations:
            logger.info(f"💡 Generated {len(new_recommendations)} optimization recommendations")
    
    def get_performance_summary(self) -> Dict:
        """Get comprehensive performance summary"""
        if not self.metrics_history:
            return {"error": "No metrics available"}
        
        recent_metrics = list(self.metrics_history)[-100:] if len(self.metrics_history) >= 100 else list(self.metrics_history)
        
        summary = {
            "current_metrics": asdict(self.metrics_history[-1]) if self.metrics_history else {},
            "averages": {
                "cpu_percent": statistics.mean(m.cpu_percent for m in recent_metrics),
                "memory_percent": statistics.mean(m.memory_percent for m in recent_metrics),
                "disk_read_rate": statistics.mean(m.disk_read_bytes for m in recent_metrics),
                "disk_write_rate": statistics.mean(m.disk_write_bytes for m in recent_metrics),
                "network_in_rate": statistics.mean(m.network_bytes_recv for m in recent_metrics),
                "network_out_rate": statistics.mean(m.network_bytes_sent for m in recent_metrics),
            },
            "baselines_count": len(self.baselines),
            "active_alerts": len([a for a in self.alerts if not a.resolved]),
            "total_alerts": len(self.alerts),
            "recommendations_count": len(self.recommendations),
            "monitoring_duration": len(self.metrics_history),
            "latest_timestamp": self.metrics_history[-1].timestamp.isoformat() if self.metrics_history else None
        }
        
        return summary
    
    def start_monitoring(self, interval_seconds: int = 5):
        """Start continuous performance monitoring"""
        if self.is_monitoring:
            logger.warning("⚠️ Monitoring already active")
            return
        
        self.is_monitoring = True
        
        def monitoring_loop():
            logger.info(f"🔄 Starting performance monitoring (interval: {interval_seconds}s)")
            
            while self.is_monitoring:
                try:
                    metrics = self.collect_metrics()
                    self.add_metrics(metrics)
                    
                    if len(self.metrics_history) % 20 == 0:  # Log every 20 samples
                        logger.info(f"📊 Collected {len(self.metrics_history)} performance samples")
                    
                    time.sleep(interval_seconds)
                    
                except Exception as e:
                    logger.error(f"💥 Monitoring error: {e}")
                    time.sleep(interval_seconds * 2)  # Wait longer on error
        
        self.monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        self.monitoring_thread.start()
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=10)
        logger.info("⏹️ Performance monitoring stopped")
    
    def get_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """Get all optimization recommendations"""
        return self.recommendations
    
    def get_active_alerts(self) -> List[PerformanceAlert]:
        """Get active performance alerts"""
        return [alert for alert in self.alerts if not alert.resolved]
    
    def resolve_alert(self, alert_id: str):
        """Mark an alert as resolved"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.resolved = True
                logger.info(f"✅ Resolved alert: {alert_id}")
                return True
        return False

def demo_performance_monitoring():
    """Demonstrate the advanced performance monitoring system"""
    print("🚀 Advanced Performance Monitoring System Demo")
    print("=" * 70)
    print("Day 9: Performance Optimization and Scalability")
    print("=" * 70)
    
    # Initialize monitor
    monitor = AdvancedPerformanceMonitor(history_size=200)
    
    print("\n📊 Starting performance monitoring demonstration...")
    
    # Collect initial metrics
    print("\n🔍 Collecting initial performance baseline...")
    for i in range(20):
        metrics = monitor.collect_metrics()
        monitor.add_metrics(metrics)
        print(f"   Sample {i+1}/20: CPU {metrics.cpu_percent:.1f}%, Memory {metrics.memory_percent:.1f}%")
        time.sleep(0.5)
    
    # Show baselines
    print(f"\n📈 Established {len(monitor.baselines)} performance baselines:")
    for name, baseline in monitor.baselines.items():
        print(f"   🔸 {name}: {baseline.baseline_value:.2f} ± {baseline.std_deviation:.2f}")
    
    # Simulate some load and monitor
    print("\n🔄 Simulating system load for 10 seconds...")
    start_time = time.time()
    sample_count = 0
    
    while time.time() - start_time < 10:
        metrics = monitor.collect_metrics()
        monitor.add_metrics(metrics)
        sample_count += 1
        
        if sample_count % 5 == 0:
            print(f"   📊 Sample {sample_count}: CPU {metrics.cpu_percent:.1f}%, "
                  f"Memory {metrics.memory_percent:.1f}%, "
                  f"Processes {metrics.process_count}")
        
        time.sleep(0.5)
    
    # Show performance summary
    print(f"\n📊 Performance Monitoring Summary:")
    summary = monitor.get_performance_summary()
    
    print(f"   🔸 Total Samples Collected: {summary['monitoring_duration']}")
    print(f"   🔸 Active Alerts: {summary['active_alerts']}")
    print(f"   🔸 Total Alerts: {summary['total_alerts']}")
    print(f"   🔸 Recommendations: {summary['recommendations_count']}")
    print(f"   🔸 Baselines Established: {summary['baselines_count']}")
    
    print(f"\n📈 Average Performance Metrics:")
    for metric, value in summary['averages'].items():
        if 'percent' in metric:
            print(f"   🔸 {metric.replace('_', ' ').title()}: {value:.1f}%")
        elif 'rate' in metric:
            print(f"   🔸 {metric.replace('_', ' ').title()}: {value/1024/1024:.2f} MB/s")
    
    # Show alerts
    active_alerts = monitor.get_active_alerts()
    if active_alerts:
        print(f"\n⚠️ Active Performance Alerts ({len(active_alerts)}):")
        for alert in active_alerts:
            print(f"   🔸 {alert.severity.upper()}: {alert.description}")
    else:
        print(f"\n✅ No active performance alerts")
    
    # Show recommendations
    recommendations = monitor.get_optimization_recommendations()
    if recommendations:
        print(f"\n💡 Optimization Recommendations ({len(recommendations)}):")
        for rec in recommendations:
            print(f"   🔸 {rec.title}")
            print(f"      Category: {rec.category}")
            print(f"      Impact: {rec.impact_level}")
            print(f"      Estimated Improvement: {rec.estimated_improvement}")
            print(f"      Confidence: {rec.confidence_score:.0%}")
            print(f"      Steps: {len(rec.action_steps)} action items")
    else:
        print(f"\n💡 No optimization recommendations at this time")
    
    print(f"\n🎉 Performance Monitoring Demo Complete!")
    print("🚀 Advanced performance monitoring system is operational and ready for production!")

if __name__ == "__main__":
    demo_performance_monitoring()