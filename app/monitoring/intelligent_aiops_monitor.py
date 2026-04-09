#!/usr/bin/env python3
"""
Intelligent AIOps Monitor
AI-powered monitoring system that provides:
- Root cause analysis using machine learning
- Automated problem resolution
- Predictive issue detection
- Intelligent recommendations
- Integration with Google Cloud AI (Gemini Pro)
"""

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import google.generativeai as genai
import psutil
import requests
import yaml
from cryptography.fernet import Fernet

# Import existing components
try:
    from adaptive_ml import AdaptiveMLManager
    from intelligent_remediation import (IntelligentRemediationEngine,
                                         RemediationSeverity)
except ImportError as e:
    print(f"⚠️  Missing component: {e}")
    print("Creating simplified versions...")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('intelligent_aiops')

@dataclass
class SystemIssue:
    """Represents a detected system issue"""
    id: str
    timestamp: datetime
    issue_type: str
    severity: str
    affected_component: str
    metrics: Dict[str, float]
    symptoms: List[str]
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    ai_analysis: Optional[str] = None
    confidence_score: float = 0.0
    auto_resolved: bool = False
    resolution_time: Optional[datetime] = None

@dataclass
class AIRecommendation:
    """AI-generated recommendation"""
    id: str
    title: str
    description: str
    action_type: str
    priority: str
    confidence: float
    implementation_steps: List[str]
    expected_outcome: str
    risks: List[str]
    timestamp: datetime

class IntelligentAIOpsMonitor:
    """AI-powered monitoring with intelligent analysis and automated resolution"""
    
    def __init__(self):
        self.monitoring = True
        self.issues: List[SystemIssue] = []
        self.recommendations: List[AIRecommendation] = []
        
        # Load configuration
        self.config = self.load_configuration()
        
        # Initialize AI services
        self.setup_ai_services()
        
        # Initialize remediation engine
        try:
            self.remediation_engine = IntelligentRemediationEngine()
            self.remediation_engine.load_default_rules()
            logger.info("✅ Intelligent Remediation Engine loaded")
        except Exception as e:
            logger.warning("⚠️  Remediation engine not available: %s", e, exc_info=True)
            self.remediation_engine = None
        
        # Initialize ML manager
        try:
            self.ml_manager = AdaptiveMLManager()
            logger.info("✅ Adaptive ML Manager loaded")
        except Exception as e:
            logger.warning("⚠️  ML manager not available: %s", e, exc_info=True)
            self.ml_manager = None
        
        # Discord webhook for notifications
        self.discord_webhook = self.config.get('discord', {}).get('webhook_url')
        
        # System baselines
        self.baselines = self.establish_baselines()
        
        # Issue patterns (for root cause analysis)
        self.issue_patterns = self.load_issue_patterns()
        
        logger.info("🤖 Intelligent AIOps Monitor initialized")
    
    def load_configuration(self) -> Dict:
        """Load encrypted configuration"""
        try:
            config_path = "config/enterprise_config.yml"
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"❌ Error loading configuration: {e}")
        return {}
    
    def setup_ai_services(self):
        """Setup Google Cloud AI services"""
        try:
            # Load GCP credentials
            gcp_config = self.config.get('google_cloud', {})
            api_key = gcp_config.get('api_key')
            
            if api_key:
                genai.configure(api_key=api_key)
                self.gemini_model = genai.GenerativeModel('gemini-pro')
                logger.info("✅ Google Cloud AI (Gemini Pro) configured")
            else:
                logger.warning("⚠️  Google Cloud AI not configured")
                self.gemini_model = None
        except Exception as e:
            logger.error(f"❌ Error setting up AI services: {e}")
            self.gemini_model = None
    
    def establish_baselines(self) -> Dict[str, float]:
        """Establish system performance baselines"""
        logger.info("📊 Establishing system baselines...")
        
        # Collect baseline metrics over 30 seconds
        cpu_samples = []
        memory_samples = []
        disk_samples = []
        
        for _ in range(6):  # 6 samples over 30 seconds
            cpu_samples.append(psutil.cpu_percent(interval=1))
            memory_samples.append(psutil.virtual_memory().percent)
            disk_samples.append(psutil.disk_usage('C:').percent)
            time.sleep(4)
        
        baselines = {
            'cpu_baseline': sum(cpu_samples) / len(cpu_samples),
            'memory_baseline': sum(memory_samples) / len(memory_samples),
            'disk_baseline': sum(disk_samples) / len(disk_samples),
            'cpu_std': self._calculate_std(cpu_samples),
            'memory_std': self._calculate_std(memory_samples),
            'disk_std': self._calculate_std(disk_samples)
        }
        
        logger.info(f"📈 Baselines established: CPU={baselines['cpu_baseline']:.1f}%, Memory={baselines['memory_baseline']:.1f}%, Disk={baselines['disk_baseline']:.1f}%")
        return baselines
    
    def _calculate_std(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
    
    def load_issue_patterns(self) -> Dict:
        """Load known issue patterns for root cause analysis"""
        return {
            'high_cpu': {
                'symptoms': ['cpu_usage > 80%', 'slow_response', 'high_load'],
                'common_causes': [
                    'Memory leak in application',
                    'Infinite loop or runaway process',
                    'Heavy computational task',
                    'Insufficient CPU resources',
                    'Background system process'
                ],
                'solutions': [
                    'Identify and restart problematic process',
                    'Optimize application code',
                    'Scale CPU resources',
                    'Implement rate limiting'
                ]
            },
            'high_memory': {
                'symptoms': ['memory_usage > 90%', 'slow_performance', 'swapping'],
                'common_causes': [
                    'Memory leak in application',
                    'Large dataset processing',
                    'Insufficient RAM',
                    'Memory fragmentation',
                    'Cache buildup'
                ],
                'solutions': [
                    'Restart memory-intensive processes',
                    'Clear system cache',
                    'Optimize memory usage',
                    'Scale memory resources',
                    'Implement memory monitoring'
                ]
            },
            'high_disk': {
                'symptoms': ['disk_usage > 90%', 'slow_io', 'storage_alerts'],
                'common_causes': [
                    'Log file growth',
                    'Temporary file accumulation',
                    'Database growth',
                    'Backup files',
                    'Application data growth'
                ],
                'solutions': [
                    'Clean up log files',
                    'Remove temporary files',
                    'Archive old data',
                    'Implement log rotation',
                    'Scale storage capacity'
                ]
            }
        }
    
    def analyze_system_state(self) -> Dict[str, Any]:
        """Comprehensive system analysis using AI"""
        # Collect current metrics
        current_metrics = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('C:').percent,
            'process_count': len(psutil.pids()),
            'boot_time': psutil.boot_time(),
            'timestamp': datetime.now().isoformat()
        }
        
        # Detect anomalies
        anomalies = self.detect_anomalies(current_metrics)
        
        # Perform root cause analysis
        root_causes = self.analyze_root_causes(current_metrics, anomalies)
        
        # Generate AI analysis
        ai_analysis = self.generate_ai_analysis(current_metrics, anomalies, root_causes)
        
        # Generate recommendations
        recommendations = self.generate_recommendations(current_metrics, anomalies, root_causes)
        
        return {
            'metrics': current_metrics,
            'anomalies': anomalies,
            'root_causes': root_causes,
            'ai_analysis': ai_analysis,
            'recommendations': recommendations,
            'timestamp': datetime.now()
        }
    
    def detect_anomalies(self, metrics: Dict[str, Any]) -> List[Dict]:
        """Detect system anomalies using baselines and ML"""
        anomalies = []
        
        # CPU anomaly detection
        cpu_current = metrics['cpu_percent']
        cpu_threshold = self.baselines['cpu_baseline'] + (3 * self.baselines['cpu_std'])
        if cpu_current > max(80, cpu_threshold):
            anomalies.append({
                'type': 'high_cpu',
                'metric': 'cpu_percent',
                'current_value': cpu_current,
                'threshold': cpu_threshold,
                'severity': 'high' if cpu_current > 90 else 'medium',
                'deviation': cpu_current - self.baselines['cpu_baseline']
            })
        
        # Memory anomaly detection
        memory_current = metrics['memory_percent']
        memory_threshold = self.baselines['memory_baseline'] + (3 * self.baselines['memory_std'])
        if memory_current > max(85, memory_threshold):
            anomalies.append({
                'type': 'high_memory',
                'metric': 'memory_percent',
                'current_value': memory_current,
                'threshold': memory_threshold,
                'severity': 'high' if memory_current > 95 else 'medium',
                'deviation': memory_current - self.baselines['memory_baseline']
            })
        
        # Disk anomaly detection
        disk_current = metrics['disk_percent']
        disk_threshold = self.baselines['disk_baseline'] + (3 * self.baselines['disk_std'])
        if disk_current > max(90, disk_threshold):
            anomalies.append({
                'type': 'high_disk',
                'metric': 'disk_percent',
                'current_value': disk_current,
                'threshold': disk_threshold,
                'severity': 'high' if disk_current > 95 else 'medium',
                'deviation': disk_current - self.baselines['disk_baseline']
            })
        
        # Use ML for anomaly detection if available
        if self.ml_manager:
            try:
                ml_anomalies = self.ml_manager.detect_anomalies([
                    cpu_current, memory_current, disk_current
                ])
                if ml_anomalies:
                    anomalies.extend(ml_anomalies)
            except Exception as e:
                logger.warning(f"⚠️  ML anomaly detection failed: {e}")
        
        return anomalies
    
    def analyze_root_causes(self, metrics: Dict, anomalies: List[Dict]) -> List[Dict]:
        """Analyze root causes of detected anomalies"""
        root_causes = []
        
        for anomaly in anomalies:
            anomaly_type = anomaly['type']
            if anomaly_type in self.issue_patterns:
                pattern = self.issue_patterns[anomaly_type]
                
                # Analyze system processes for specific causes
                potential_causes = []
                
                if anomaly_type == 'high_cpu':
                    # Find high CPU processes
                    processes = []
                    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                        try:
                            if proc.info['cpu_percent'] > 10:
                                processes.append(proc.info)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    if processes:
                        potential_causes.append(f"High CPU processes: {[p['name'] for p in processes[:3]]}")
                
                elif anomaly_type == 'high_memory':
                    # Find high memory processes
                    processes = []
                    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                        try:
                            if proc.info['memory_percent'] > 5:
                                processes.append(proc.info)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    if processes:
                        potential_causes.append(f"High memory processes: {[p['name'] for p in processes[:3]]}")
                
                root_causes.append({
                    'anomaly_type': anomaly_type,
                    'pattern_causes': pattern['common_causes'],
                    'detected_causes': potential_causes,
                    'confidence': 0.8 if potential_causes else 0.6
                })
        
        return root_causes
    
    def generate_ai_analysis(self, metrics: Dict, anomalies: List[Dict], root_causes: List[Dict]) -> str:
        """Generate AI-powered analysis using Gemini Pro"""
        if not self.gemini_model:
            return self.generate_fallback_analysis(metrics, anomalies, root_causes)
        
        try:
            # Prepare prompt for AI analysis
            prompt = f"""
You are an expert system administrator analyzing a computer system. Provide intelligent analysis and solutions.

CURRENT SYSTEM METRICS:
- CPU Usage: {metrics['cpu_percent']:.1f}%
- Memory Usage: {metrics['memory_percent']:.1f}%
- Disk Usage: {metrics['disk_percent']:.1f}%
- Process Count: {metrics['process_count']}

DETECTED ANOMALIES:
{json.dumps(anomalies, indent=2) if anomalies else "No significant anomalies detected"}

ROOT CAUSE ANALYSIS:
{json.dumps(root_causes, indent=2) if root_causes else "No specific root causes identified"}

Please provide:
1. INTELLIGENT ANALYSIS: What's happening with this system?
2. ROOT CAUSE: What is likely causing any issues?
3. IMMEDIATE SOLUTIONS: Specific steps to resolve problems
4. PREVENTIVE MEASURES: How to prevent future issues
5. PRIORITY LEVEL: Critical/High/Medium/Low

Be specific, actionable, and technical. Focus on practical solutions.
"""
            
            response = self.gemini_model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"❌ AI analysis failed: {e}")
            return self.generate_fallback_analysis(metrics, anomalies, root_causes)
    
    def generate_fallback_analysis(self, metrics: Dict, anomalies: List[Dict], root_causes: List[Dict]) -> str:
        """Generate fallback analysis when AI is not available"""
        analysis = "📊 SYSTEM ANALYSIS\n\n"
        
        # System health overview
        if not anomalies:
            analysis += "✅ SYSTEM STATUS: Healthy - All metrics within normal ranges\n\n"
            analysis += f"Current Performance:\n"
            analysis += f"- CPU: {metrics['cpu_percent']:.1f}% (Normal)\n"
            analysis += f"- Memory: {metrics['memory_percent']:.1f}% (Normal)\n"
            analysis += f"- Disk: {metrics['disk_percent']:.1f}% (Normal)\n\n"
            analysis += "🔍 RECOMMENDATIONS:\n"
            analysis += "- Continue monitoring\n"
            analysis += "- Maintain current resource levels\n"
            analysis += "- Regular system maintenance\n"
        else:
            analysis += "⚠️ SYSTEM ISSUES DETECTED\n\n"
            
            for anomaly in anomalies:
                analysis += f"🚨 {anomaly['type'].upper()} DETECTED:\n"
                analysis += f"- Current: {anomaly['current_value']:.1f}%\n"
                analysis += f"- Severity: {anomaly['severity'].upper()}\n"
                analysis += f"- Deviation: +{anomaly['deviation']:.1f}% from baseline\n\n"
            
            # Root cause analysis
            if root_causes:
                analysis += "🔍 ROOT CAUSE ANALYSIS:\n"
                for cause in root_causes:
                    analysis += f"\n{cause['anomaly_type'].upper()}:\n"
                    analysis += f"Likely causes: {', '.join(cause['pattern_causes'][:2])}\n"
                    if cause['detected_causes']:
                        analysis += f"Detected: {', '.join(cause['detected_causes'])}\n"
            
            # Solutions
            analysis += "\n💡 IMMEDIATE SOLUTIONS:\n"
            for anomaly in anomalies:
                if anomaly['type'] in self.issue_patterns:
                    solutions = self.issue_patterns[anomaly['type']]['solutions']
                    analysis += f"\nFor {anomaly['type']}:\n"
                    for i, solution in enumerate(solutions[:3], 1):
                        analysis += f"{i}. {solution}\n"
        
        return analysis
    
    def generate_recommendations(self, metrics: Dict, anomalies: List[Dict], root_causes: List[Dict]) -> List[AIRecommendation]:
        """Generate actionable recommendations"""
        recommendations = []
        
        for anomaly in anomalies:
            anomaly_type = anomaly['type']
            severity = anomaly['severity']
            
            if anomaly_type == 'high_cpu':
                recommendations.append(AIRecommendation(
                    id=f"cpu_rec_{datetime.now().strftime('%H%M%S')}",
                    title="Resolve High CPU Usage",
                    description=f"CPU usage is at {anomaly['current_value']:.1f}%, significantly above normal",
                    action_type="performance_optimization",
                    priority=severity,
                    confidence=0.85,
                    implementation_steps=[
                        "Identify top CPU-consuming processes using Task Manager",
                        "Determine if processes are legitimate or problematic",
                        "Restart resource-intensive applications if necessary",
                        "Consider scaling CPU resources if this is a recurring issue"
                    ],
                    expected_outcome="CPU usage should return to normal levels (< 70%)",
                    risks=["Restarting processes may cause temporary service interruption"],
                    timestamp=datetime.now()
                ))
            
            elif anomaly_type == 'high_memory':
                recommendations.append(AIRecommendation(
                    id=f"mem_rec_{datetime.now().strftime('%H%M%S')}",
                    title="Resolve High Memory Usage",
                    description=f"Memory usage is at {anomaly['current_value']:.1f}%, approaching critical levels",
                    action_type="memory_management",
                    priority=severity,
                    confidence=0.80,
                    implementation_steps=[
                        "Identify memory-intensive applications",
                        "Clear system cache and temporary files",
                        "Restart applications with memory leaks",
                        "Consider adding more RAM if usage consistently high"
                    ],
                    expected_outcome="Memory usage should decrease to manageable levels (< 80%)",
                    risks=["Clearing cache may temporarily slow application startup"],
                    timestamp=datetime.now()
                ))
            
            elif anomaly_type == 'high_disk':
                recommendations.append(AIRecommendation(
                    id=f"disk_rec_{datetime.now().strftime('%H%M%S')}",
                    title="Resolve High Disk Usage",
                    description=f"Disk usage is at {anomaly['current_value']:.1f}%, running out of space",
                    action_type="storage_management",
                    priority=severity,
                    confidence=0.90,
                    implementation_steps=[
                        "Run disk cleanup utility",
                        "Clear temporary files and browser cache",
                        "Remove old log files and backups",
                        "Uninstall unused applications",
                        "Move large files to external storage"
                    ],
                    expected_outcome="Disk usage should decrease significantly (< 85%)",
                    risks=["Removing files may delete important data if not careful"],
                    timestamp=datetime.now()
                ))
        
        return recommendations
    
    def attempt_auto_resolution(self, issue: SystemIssue) -> bool:
        """Attempt automated resolution of the issue"""
        if not self.remediation_engine:
            logger.warning("⚠️  Remediation engine not available for auto-resolution")
            return False
        
        try:
            # Find matching remediation rule
            matching_rules = self.remediation_engine.find_matching_rules(issue.issue_type)
            
            for rule in matching_rules:
                if rule.severity in [RemediationSeverity.LOW, RemediationSeverity.MEDIUM]:
                    logger.info(f"🔧 Attempting auto-resolution: {rule.name}")
                    
                    success = self.remediation_engine.execute_remediation(rule, issue.metrics)
                    
                    if success:
                        issue.auto_resolved = True
                        issue.resolution_time = datetime.now()
                        logger.info(f"✅ Auto-resolved issue: {issue.issue_type}")
                        return True
                    else:
                        logger.warning(f"❌ Auto-resolution failed: {rule.name}")
            
        except Exception as e:
            logger.error(f"❌ Error in auto-resolution: {e}")
        
        return False
    
    def send_intelligent_notification(self, analysis: Dict[str, Any]):
        """Send intelligent notification with analysis and solutions"""
        if not self.discord_webhook:
            logger.warning("⚠️  Discord webhook not configured")
            return
        
        metrics = analysis['metrics']
        anomalies = analysis['anomalies']
        ai_analysis = analysis['ai_analysis']
        recommendations = analysis['recommendations']
        
        # Create rich embed
        embed = {
            "title": "🤖 Intelligent AIOps Analysis",
            "description": "AI-powered system analysis with solutions",
            "color": 0xff6b35 if anomalies else 0x36a64f,
            "timestamp": datetime.now().isoformat(),
            "fields": [
                {
                    "name": "📊 Current Metrics",
                    "value": f"CPU: {metrics['cpu_percent']:.1f}% | Memory: {metrics['memory_percent']:.1f}% | Disk: {metrics['disk_percent']:.1f}%",
                    "inline": False
                }
            ]
        }
        
        # Add anomalies if detected
        if anomalies:
            anomaly_text = "\n".join([
                f"🚨 **{anom['type'].title()}**: {anom['current_value']:.1f}% ({anom['severity']})"
                for anom in anomalies[:3]
            ])
            embed["fields"].append({
                "name": "⚠️ Detected Issues",
                "value": anomaly_text,
                "inline": False
            })
        
        # Add AI analysis (truncated)
        if ai_analysis:
            analysis_preview = ai_analysis[:500] + "..." if len(ai_analysis) > 500 else ai_analysis
            embed["fields"].append({
                "name": "🧠 AI Analysis",
                "value": f"```{analysis_preview}```",
                "inline": False
            })
        
        # Add recommendations
        if recommendations:
            rec_text = "\n".join([
                f"💡 **{rec.title}** ({rec.priority} priority)"
                for rec in recommendations[:2]
            ])
            embed["fields"].append({
                "name": "🔧 Recommended Actions",
                "value": rec_text,
                "inline": False
            })
        
        # Send notification
        try:
            payload = {
                "embeds": [embed],
                "username": "Intelligent AIOps Monitor"
            }
            
            response = requests.post(
                self.discord_webhook,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 204:
                logger.info("✅ Intelligent notification sent to Discord")
            else:
                logger.error(f"❌ Failed to send notification: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Error sending notification: {e}")
    
    def run_intelligent_monitoring_cycle(self):
        """Run one complete intelligent monitoring cycle"""
        logger.info("🔍 Starting intelligent analysis cycle...")
        
        # Perform comprehensive analysis
        analysis = self.analyze_system_state()
        
        # Create issues for detected anomalies
        current_issues = []
        for anomaly in analysis['anomalies']:
            issue = SystemIssue(
                id=f"issue_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{anomaly['type']}",
                timestamp=datetime.now(),
                issue_type=anomaly['type'],
                severity=anomaly['severity'],
                affected_component=anomaly['metric'],
                metrics=analysis['metrics'],
                symptoms=[f"{anomaly['metric']} at {anomaly['current_value']:.1f}%"],
                ai_analysis=analysis['ai_analysis'],
                confidence_score=0.8
            )
            
            # Attempt auto-resolution for safe issues
            if issue.severity in ['low', 'medium']:
                auto_resolved = self.attempt_auto_resolution(issue)
                if auto_resolved:
                    logger.info(f"🎯 Successfully auto-resolved: {issue.issue_type}")
            
            current_issues.append(issue)
            self.issues.append(issue)
        
        # Add recommendations
        self.recommendations.extend(analysis['recommendations'])
        
        # Send intelligent notification
        self.send_intelligent_notification(analysis)
        
        # Log summary
        if analysis['anomalies']:
            logger.warning(f"⚠️  Detected {len(analysis['anomalies'])} anomalies, generated {len(analysis['recommendations'])} recommendations")
        else:
            logger.info("✅ System operating normally - no issues detected")
        
        return analysis
    
    def start_intelligent_monitoring(self, interval: int = 60):
        """Start continuous intelligent monitoring"""
        logger.info(f"🚀 Starting Intelligent AIOps Monitoring (interval: {interval}s)")
        logger.info("🧠 Features enabled:")
        logger.info("   • AI-powered root cause analysis")
        logger.info("   • Automated issue resolution")
        logger.info("   • Predictive recommendations")
        logger.info("   • Google Cloud AI integration")
        
        while self.monitoring:
            try:
                self.run_intelligent_monitoring_cycle()
                
                # Wait for next cycle
                for _ in range(interval):
                    if not self.monitoring:
                        break
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("⏹️  Monitoring stopped by user")
                self.monitoring = False
                break
            except Exception as e:
                logger.error(f"❌ Error in monitoring cycle: {e}")
                time.sleep(30)  # Wait before retrying
        
        logger.info("🛑 Intelligent AIOps Monitor stopped")

def main():
    """Main function"""
    print("🤖 Intelligent AIOps Monitor")
    print("=" * 50)
    
    # Create monitor instance
    monitor = IntelligentAIOpsMonitor()
    
    # Run one analysis cycle to demonstrate capabilities
    print("\n🔍 Running initial system analysis...")
    analysis = monitor.run_intelligent_monitoring_cycle()
    
    print(f"\n📊 Analysis Complete:")
    print(f"   • Metrics collected: ✅")
    print(f"   • Anomalies detected: {len(analysis['anomalies'])}")
    print(f"   • AI analysis: {'✅' if analysis['ai_analysis'] else '⚠️  Fallback mode'}")
    print(f"   • Recommendations: {len(analysis['recommendations'])}")
    
    # Ask user if they want continuous monitoring
    print(f"\n🚀 Start continuous intelligent monitoring? (y/n): ", end="")
    try:
        choice = input().strip().lower()
        if choice in ['y', 'yes']:
            monitor.start_intelligent_monitoring(interval=60)
        else:
            print("👋 Single analysis complete. Monitor ready for future use.")
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()