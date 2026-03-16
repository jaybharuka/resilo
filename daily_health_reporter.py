"""
Daily Health Report Generator
24-hour system analysis with risk period identification and performance insights
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import statistics
import psutil

@dataclass
class HealthMetric:
    timestamp: str
    cpu: float
    memory: float
    disk: float
    temperature: float
    network_in: float
    network_out: float
    status: str

@dataclass
class RiskPeriod:
    start_time: str
    end_time: str
    duration_minutes: int
    risk_level: str
    primary_cause: str
    max_cpu: float
    max_memory: float
    max_temperature: float
    
@dataclass
class DailyHealthReport:
    date: str
    overall_score: float
    uptime_hours: float
    peak_risk_periods: List[RiskPeriod]
    cpu_analysis: Dict
    memory_analysis: Dict
    disk_analysis: Dict
    temperature_analysis: Dict
    network_analysis: Dict
    recommendations: List[str]
    performance_trends: Dict

class HealthReportGenerator:
    def __init__(self, db_path: str = "health_metrics.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for storing metrics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu REAL NOT NULL,
                memory REAL NOT NULL,
                disk REAL NOT NULL,
                temperature REAL NOT NULL,
                network_in REAL NOT NULL,
                network_out REAL NOT NULL,
                status TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON health_metrics(timestamp)
        ''')
        
        conn.commit()
        conn.close()
    
    def store_metric(self, metric: HealthMetric):
        """Store a health metric in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO health_metrics 
            (timestamp, cpu, memory, disk, temperature, network_in, network_out, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            metric.timestamp, metric.cpu, metric.memory, metric.disk,
            metric.temperature, metric.network_in, metric.network_out, metric.status
        ))
        
        conn.commit()
        conn.close()
    
    def get_metrics_for_period(self, start_time: datetime, end_time: datetime) -> List[HealthMetric]:
        """Retrieve metrics for a specific time period"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, cpu, memory, disk, temperature, network_in, network_out, status
            FROM health_metrics
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp
        ''', (start_time.isoformat(), end_time.isoformat()))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            HealthMetric(
                timestamp=row[0], cpu=row[1], memory=row[2], disk=row[3],
                temperature=row[4], network_in=row[5], network_out=row[6], status=row[7]
            )
            for row in rows
        ]
    
    def generate_daily_report(self, target_date: Optional[datetime] = None) -> DailyHealthReport:
        """Generate comprehensive daily health report"""
        if target_date is None:
            target_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        start_time = target_date
        end_time = start_time + timedelta(days=1)
        
        # Get metrics for the day
        metrics = self.get_metrics_for_period(start_time, end_time)
        
        if not metrics:
            return self._generate_empty_report(target_date.strftime('%Y-%m-%d'))
        
        # Analyze various aspects
        risk_periods = self._identify_risk_periods(metrics)
        cpu_analysis = self._analyze_cpu_performance(metrics)
        memory_analysis = self._analyze_memory_usage(metrics)
        disk_analysis = self._analyze_disk_usage(metrics)
        temperature_analysis = self._analyze_temperature(metrics)
        network_analysis = self._analyze_network_activity(metrics)
        
        # Calculate overall health score
        overall_score = self._calculate_health_score(metrics)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            metrics, risk_periods, cpu_analysis, memory_analysis, disk_analysis
        )
        
        # Analyze performance trends
        performance_trends = self._analyze_performance_trends(metrics)
        
        return DailyHealthReport(
            date=target_date.strftime('%Y-%m-%d'),
            overall_score=overall_score,
            uptime_hours=len(metrics) / 60,  # Assuming 1-minute intervals
            peak_risk_periods=risk_periods,
            cpu_analysis=cpu_analysis,
            memory_analysis=memory_analysis,
            disk_analysis=disk_analysis,
            temperature_analysis=temperature_analysis,
            network_analysis=network_analysis,
            recommendations=recommendations,
            performance_trends=performance_trends
        )
    
    def _identify_risk_periods(self, metrics: List[HealthMetric]) -> List[RiskPeriod]:
        """Identify periods of high system risk"""
        risk_periods = []
        current_risk_start = None
        risk_threshold_cpu = 80
        risk_threshold_memory = 85
        risk_threshold_temp = 75
        
        for i, metric in enumerate(metrics):
            is_risky = (
                metric.cpu > risk_threshold_cpu or 
                metric.memory > risk_threshold_memory or 
                metric.temperature > risk_threshold_temp
            )
            
            if is_risky and current_risk_start is None:
                current_risk_start = i
            elif not is_risky and current_risk_start is not None:
                # End of risk period
                risk_period = self._create_risk_period(
                    metrics, current_risk_start, i - 1
                )
                if risk_period.duration_minutes >= 5:  # Only include periods >= 5 minutes
                    risk_periods.append(risk_period)
                current_risk_start = None
        
        # Handle ongoing risk period at end of day
        if current_risk_start is not None:
            risk_period = self._create_risk_period(
                metrics, current_risk_start, len(metrics) - 1
            )
            risk_periods.append(risk_period)
        
        return sorted(risk_periods, key=lambda x: x.duration_minutes, reverse=True)[:10]
    
    def _create_risk_period(self, metrics: List[HealthMetric], start_idx: int, end_idx: int) -> RiskPeriod:
        """Create a risk period from metric indices"""
        period_metrics = metrics[start_idx:end_idx + 1]
        
        max_cpu = max(m.cpu for m in period_metrics)
        max_memory = max(m.memory for m in period_metrics)
        max_temp = max(m.temperature for m in period_metrics)
        
        # Determine primary cause
        primary_cause = "CPU Usage"
        if max_memory > max_cpu and max_memory > 85:
            primary_cause = "Memory Usage"
        elif max_temp > 75:
            primary_cause = "High Temperature"
        
        # Determine risk level
        risk_level = "Medium"
        if max_cpu > 95 or max_memory > 95 or max_temp > 80:
            risk_level = "Critical"
        elif max_cpu > 90 or max_memory > 90 or max_temp > 75:
            risk_level = "High"
        
        return RiskPeriod(
            start_time=period_metrics[0].timestamp,
            end_time=period_metrics[-1].timestamp,
            duration_minutes=len(period_metrics),
            risk_level=risk_level,
            primary_cause=primary_cause,
            max_cpu=max_cpu,
            max_memory=max_memory,
            max_temperature=max_temp
        )
    
    def _analyze_cpu_performance(self, metrics: List[HealthMetric]) -> Dict:
        """Analyze CPU performance patterns"""
        cpu_values = [m.cpu for m in metrics]
        
        return {
            'average': statistics.mean(cpu_values),
            'peak': max(cpu_values),
            'minimum': min(cpu_values),
            'median': statistics.median(cpu_values),
            'std_deviation': statistics.stdev(cpu_values) if len(cpu_values) > 1 else 0,
            'time_above_80': sum(1 for cpu in cpu_values if cpu > 80),
            'time_above_90': sum(1 for cpu in cpu_values if cpu > 90),
            'peak_time': metrics[cpu_values.index(max(cpu_values))].timestamp,
            'efficiency_score': max(0, 100 - statistics.mean(cpu_values))
        }
    
    def _analyze_memory_usage(self, metrics: List[HealthMetric]) -> Dict:
        """Analyze memory usage patterns"""
        memory_values = [m.memory for m in metrics]
        
        return {
            'average': statistics.mean(memory_values),
            'peak': max(memory_values),
            'minimum': min(memory_values),
            'median': statistics.median(memory_values),
            'std_deviation': statistics.stdev(memory_values) if len(memory_values) > 1 else 0,
            'time_above_80': sum(1 for mem in memory_values if mem > 80),
            'time_above_90': sum(1 for mem in memory_values if mem > 90),
            'peak_time': metrics[memory_values.index(max(memory_values))].timestamp,
            'stability_score': max(0, 100 - statistics.stdev(memory_values) * 10) if len(memory_values) > 1 else 100
        }
    
    def _analyze_disk_usage(self, metrics: List[HealthMetric]) -> Dict:
        """Analyze disk usage patterns"""
        disk_values = [m.disk for m in metrics]
        
        return {
            'average': statistics.mean(disk_values),
            'peak': max(disk_values),
            'minimum': min(disk_values),
            'growth_rate': (max(disk_values) - min(disk_values)) / len(disk_values) if len(disk_values) > 1 else 0,
            'space_concern': max(disk_values) > 90,
            'cleanup_needed': max(disk_values) > 85
        }
    
    def _analyze_temperature(self, metrics: List[HealthMetric]) -> Dict:
        """Analyze temperature patterns"""
        temp_values = [m.temperature for m in metrics]
        
        return {
            'average': statistics.mean(temp_values),
            'peak': max(temp_values),
            'minimum': min(temp_values),
            'time_above_70': sum(1 for temp in temp_values if temp > 70),
            'time_above_80': sum(1 for temp in temp_values if temp > 80),
            'thermal_throttling_risk': max(temp_values) > 85,
            'cooling_efficiency': max(0, 100 - (statistics.mean(temp_values) - 40))
        }
    
    def _analyze_network_activity(self, metrics: List[HealthMetric]) -> Dict:
        """Analyze network activity patterns"""
        net_in_values = [m.network_in for m in metrics]
        net_out_values = [m.network_out for m in metrics]
        
        return {
            'avg_download': statistics.mean(net_in_values),
            'avg_upload': statistics.mean(net_out_values),
            'peak_download': max(net_in_values),
            'peak_upload': max(net_out_values),
            'total_data_in_gb': sum(net_in_values) / 1024,
            'total_data_out_gb': sum(net_out_values) / 1024,
            'high_activity_periods': sum(1 for net in net_in_values if net > 50)
        }
    
    def _calculate_health_score(self, metrics: List[HealthMetric]) -> float:
        """Calculate overall system health score (0-100)"""
        cpu_score = max(0, 100 - statistics.mean([m.cpu for m in metrics]))
        memory_score = max(0, 100 - statistics.mean([m.memory for m in metrics]))
        disk_score = max(0, 100 - statistics.mean([m.disk for m in metrics]))
        temp_score = max(0, 100 - (statistics.mean([m.temperature for m in metrics]) - 30))
        
        # Weight the scores
        overall_score = (
            cpu_score * 0.3 +
            memory_score * 0.3 + 
            disk_score * 0.2 +
            temp_score * 0.2
        )
        
        return round(min(100, max(0, overall_score)), 1)
    
    def _generate_recommendations(self, metrics: List[HealthMetric], risk_periods: List[RiskPeriod], 
                                 cpu_analysis: Dict, memory_analysis: Dict, disk_analysis: Dict) -> List[str]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []
        
        # CPU recommendations
        if cpu_analysis['average'] > 70:
            recommendations.append("Consider closing unnecessary applications to reduce CPU load")
        if cpu_analysis['time_above_90'] > 60:  # More than 1 hour above 90%
            recommendations.append("Investigate processes causing high CPU usage in Task Manager")
        
        # Memory recommendations
        if memory_analysis['average'] > 80:
            recommendations.append("Close browser tabs and unused applications to free memory")
        if memory_analysis['peak'] > 95:
            recommendations.append("Consider upgrading RAM or optimizing memory-intensive applications")
        
        # Disk recommendations
        if disk_analysis['peak'] > 90:
            recommendations.append("Clean up temporary files and consider disk space optimization")
        if disk_analysis['growth_rate'] > 0.1:
            recommendations.append("Monitor disk space growth and plan for storage expansion")
        
        # Risk period recommendations
        if len(risk_periods) > 5:
            recommendations.append("Schedule system maintenance during identified peak usage periods")
        
        # General recommendations
        if not recommendations:
            recommendations.append("System performance is optimal - continue current usage patterns")
        
        return recommendations[:5]  # Limit to top 5 recommendations
    
    def _analyze_performance_trends(self, metrics: List[HealthMetric]) -> Dict:
        """Analyze performance trends throughout the day"""
        hours = {}
        
        for metric in metrics:
            hour = datetime.fromisoformat(metric.timestamp).hour
            if hour not in hours:
                hours[hour] = {'cpu': [], 'memory': [], 'disk': []}
            
            hours[hour]['cpu'].append(metric.cpu)
            hours[hour]['memory'].append(metric.memory)
            hours[hour]['disk'].append(metric.disk)
        
        hourly_averages = {}
        for hour, values in hours.items():
            hourly_averages[hour] = {
                'cpu': statistics.mean(values['cpu']),
                'memory': statistics.mean(values['memory']),
                'disk': statistics.mean(values['disk'])
            }
        
        # Find peak hours
        peak_cpu_hour = max(hourly_averages.keys(), key=lambda h: hourly_averages[h]['cpu'], default=0)
        peak_memory_hour = max(hourly_averages.keys(), key=lambda h: hourly_averages[h]['memory'], default=0)
        
        return {
            'hourly_averages': hourly_averages,
            'peak_cpu_hour': peak_cpu_hour,
            'peak_memory_hour': peak_memory_hour,
            'most_active_hours': [h for h, v in hourly_averages.items() if v['cpu'] > 50]
        }
    
    def _generate_empty_report(self, date: str) -> DailyHealthReport:
        """Generate empty report when no data is available"""
        return DailyHealthReport(
            date=date,
            overall_score=0.0,
            uptime_hours=0.0,
            peak_risk_periods=[],
            cpu_analysis={},
            memory_analysis={},
            disk_analysis={},
            temperature_analysis={},
            network_analysis={},
            recommendations=["No data available for this period"],
            performance_trends={}
        )
    
    def export_report_json(self, report: DailyHealthReport, filename: Optional[str] = None) -> str:
        """Export report to JSON file"""
        if filename is None:
            filename = f"health_report_{report.date}.json"
        
        with open(filename, 'w') as f:
            json.dump(asdict(report), f, indent=2)
        
        return filename

# Example usage and integration
def start_metric_collection():
    """Start collecting metrics every minute"""
    generator = HealthReportGenerator()
    
    def collect_metric():
        metric = HealthMetric(
            timestamp=datetime.now().isoformat(),
            cpu=psutil.cpu_percent(interval=1),
            memory=psutil.virtual_memory().percent,
            disk=psutil.disk_usage('/').percent if hasattr(psutil, 'disk_usage') else 50.0,
            temperature=45.0 + psutil.cpu_percent() * 0.3,  # Estimated
            network_in=0.0,  # Would be calculated from psutil.net_io_counters()
            network_out=0.0,
            status="healthy"
        )
        
        generator.store_metric(metric)
        print(f"📊 Stored metric: CPU {metric.cpu:.1f}%, Memory {metric.memory:.1f}%")
    
    # Collect metrics every minute
    import threading
    
    def metric_loop():
        while True:
            collect_metric()
            time.sleep(60)  # Wait 1 minute
    
    thread = threading.Thread(target=metric_loop, daemon=True)
    thread.start()
    
    return generator

if __name__ == "__main__":
    # Demo usage
    generator = HealthReportGenerator()
    
    # Generate report for today
    report = generator.generate_daily_report()
    
    print(f"📋 Daily Health Report for {report.date}")
    print(f"Overall Score: {report.overall_score}/100")
    print(f"Risk Periods: {len(report.peak_risk_periods)}")
    print(f"Recommendations: {len(report.recommendations)}")
    
    # Export to JSON
    filename = generator.export_report_json(report)
    print(f"📄 Report exported to: {filename}")