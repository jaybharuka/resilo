#!/usr/bin/env python3
"""
AIOps Security Analytics Dashboard
Comprehensive security analytics with threat visualization, risk scoring, and security KPIs

Features:
- Real-time security metrics and KPI tracking
- Advanced threat visualization and dashboards
- Risk scoring and trend analysis
- Security posture assessment
- Executive reporting and compliance metrics
- Predictive analytics and forecasting
- Custom dashboard creation and alerts
- Integration with all security systems
"""

import asyncio
import json
import logging
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, Counter
import uuid
import sqlite3
import math

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('security_analytics')

class MetricType(Enum):
    """Types of security metrics"""
    COUNT = "count"
    PERCENTAGE = "percentage"
    RATIO = "ratio"
    SCORE = "score"
    DURATION = "duration"
    RATE = "rate"
    TREND = "trend"

class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class DashboardType(Enum):
    """Types of security dashboards"""
    EXECUTIVE = "executive"
    OPERATIONS = "operations"
    COMPLIANCE = "compliance"
    THREAT_HUNTING = "threat_hunting"
    INCIDENT_RESPONSE = "incident_response"
    RISK_MANAGEMENT = "risk_management"

class TimeRange(Enum):
    """Time range options"""
    REAL_TIME = "real_time"
    LAST_HOUR = "last_hour"
    LAST_24H = "last_24h"
    LAST_7D = "last_7d"
    LAST_30D = "last_30d"
    LAST_90D = "last_90d"
    LAST_YEAR = "last_year"

@dataclass
class SecurityMetric:
    """Security metric definition"""
    metric_id: str
    name: str
    description: str
    metric_type: MetricType
    value: float
    unit: str
    timestamp: datetime
    source: str
    threshold_critical: Optional[float] = None
    threshold_warning: Optional[float] = None
    trend_direction: Optional[str] = None  # up, down, stable
    trend_percentage: Optional[float] = None
    category: str = "general"
    tags: List[str] = field(default_factory=list)

@dataclass
class SecurityKPI:
    """Security Key Performance Indicator"""
    kpi_id: str
    name: str
    description: str
    current_value: float
    target_value: float
    unit: str
    calculation_method: str
    last_updated: datetime
    trend_data: List[Tuple[datetime, float]] = field(default_factory=list)
    achievement_percentage: float = 0.0
    status: str = "unknown"  # excellent, good, warning, critical

@dataclass
class SecurityAlert:
    """Security analytics alert"""
    alert_id: str
    title: str
    description: str
    severity: AlertSeverity
    metric_id: str
    threshold_value: float
    actual_value: float
    timestamp: datetime
    source_system: str
    acknowledged: bool = False
    resolved: bool = False
    assignee: Optional[str] = None
    resolution_notes: Optional[str] = None

@dataclass
class DashboardWidget:
    """Dashboard widget configuration"""
    widget_id: str
    title: str
    widget_type: str  # chart, metric, table, gauge, heatmap
    data_source: str
    query: str
    visualization_config: Dict[str, Any]
    position: Dict[str, int]  # x, y, width, height
    refresh_interval: int = 300  # seconds
    is_active: bool = True

@dataclass
class SecurityDashboard:
    """Security dashboard configuration"""
    dashboard_id: str
    name: str
    description: str
    dashboard_type: DashboardType
    widgets: List[DashboardWidget]
    created_by: str
    created_time: datetime
    last_modified: datetime
    is_public: bool = False
    access_permissions: List[str] = field(default_factory=list)

@dataclass
class ThreatAnalysis:
    """Threat analysis results"""
    analysis_id: str
    analysis_type: str
    start_time: datetime
    end_time: datetime
    total_events: int
    threat_score: float
    threat_level: str
    top_threats: List[Dict[str, Any]]
    attack_patterns: List[Dict[str, Any]]
    geographic_distribution: Dict[str, int]
    timeline_analysis: List[Dict[str, Any]]
    recommendations: List[str]

@dataclass
class RiskAssessment:
    """Security risk assessment"""
    assessment_id: str
    assessment_date: datetime
    overall_risk_score: float
    risk_level: str
    risk_categories: Dict[str, float]
    vulnerabilities: List[Dict[str, Any]]
    threat_landscape: Dict[str, Any]
    mitigation_recommendations: List[Dict[str, Any]]
    compliance_status: Dict[str, Any]

class SecurityMetricsCalculator:
    """Security metrics calculation engine"""
    
    def __init__(self):
        self.metrics = {}  # metric_id -> SecurityMetric
        self.historical_data = defaultdict(list)  # metric_id -> [(timestamp, value)]
        logger.info("Security metrics calculator initialized")
    
    def calculate_threat_detection_rate(self, total_threats: int, detected_threats: int) -> SecurityMetric:
        """Calculate threat detection rate"""
        rate = (detected_threats / total_threats * 100) if total_threats > 0 else 0
        
        metric = SecurityMetric(
            metric_id="threat_detection_rate",
            name="Threat Detection Rate",
            description="Percentage of threats detected by security systems",
            metric_type=MetricType.PERCENTAGE,
            value=rate,
            unit="%",
            timestamp=datetime.now(),
            source="security_monitoring",
            threshold_critical=50.0,
            threshold_warning=75.0,
            category="threat_detection"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def calculate_mean_time_to_detection(self, detection_times: List[float]) -> SecurityMetric:
        """Calculate mean time to detection (MTTD)"""
        mttd = statistics.mean(detection_times) if detection_times else 0
        
        metric = SecurityMetric(
            metric_id="mean_time_to_detection",
            name="Mean Time to Detection",
            description="Average time to detect security incidents",
            metric_type=MetricType.DURATION,
            value=mttd,
            unit="minutes",
            timestamp=datetime.now(),
            source="incident_response",
            threshold_critical=120.0,  # 2 hours
            threshold_warning=60.0,   # 1 hour
            category="response_time"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def calculate_mean_time_to_response(self, response_times: List[float]) -> SecurityMetric:
        """Calculate mean time to response (MTTR)"""
        mttr = statistics.mean(response_times) if response_times else 0
        
        metric = SecurityMetric(
            metric_id="mean_time_to_response",
            name="Mean Time to Response",
            description="Average time to respond to security incidents",
            metric_type=MetricType.DURATION,
            value=mttr,
            unit="minutes",
            timestamp=datetime.now(),
            source="incident_response",
            threshold_critical=240.0,  # 4 hours
            threshold_warning=120.0,   # 2 hours
            category="response_time"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def calculate_security_posture_score(self, vulnerability_score: float, threat_score: float, 
                                       compliance_score: float) -> SecurityMetric:
        """Calculate overall security posture score"""
        # Weighted calculation
        weights = {'vulnerability': 0.4, 'threat': 0.3, 'compliance': 0.3}
        
        posture_score = (
            vulnerability_score * weights['vulnerability'] +
            threat_score * weights['threat'] +
            compliance_score * weights['compliance']
        )
        
        metric = SecurityMetric(
            metric_id="security_posture_score",
            name="Security Posture Score",
            description="Overall security posture assessment score",
            metric_type=MetricType.SCORE,
            value=posture_score,
            unit="score",
            timestamp=datetime.now(),
            source="analytics_engine",
            threshold_critical=60.0,
            threshold_warning=75.0,
            category="posture"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def calculate_vulnerability_density(self, total_vulnerabilities: int, total_assets: int) -> SecurityMetric:
        """Calculate vulnerability density"""
        density = (total_vulnerabilities / total_assets) if total_assets > 0 else 0
        
        metric = SecurityMetric(
            metric_id="vulnerability_density",
            name="Vulnerability Density",
            description="Number of vulnerabilities per asset",
            metric_type=MetricType.RATIO,
            value=density,
            unit="vulns/asset",
            timestamp=datetime.now(),
            source="vulnerability_scanner",
            threshold_critical=5.0,
            threshold_warning=2.0,
            category="vulnerability"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def calculate_patch_compliance_rate(self, patched_systems: int, total_systems: int) -> SecurityMetric:
        """Calculate patch compliance rate"""
        rate = (patched_systems / total_systems * 100) if total_systems > 0 else 0
        
        metric = SecurityMetric(
            metric_id="patch_compliance_rate",
            name="Patch Compliance Rate",
            description="Percentage of systems with latest security patches",
            metric_type=MetricType.PERCENTAGE,
            value=rate,
            unit="%",
            timestamp=datetime.now(),
            source="patch_management",
            threshold_critical=80.0,
            threshold_warning=90.0,
            category="compliance"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def calculate_failed_login_rate(self, failed_logins: int, total_logins: int) -> SecurityMetric:
        """Calculate failed login rate"""
        rate = (failed_logins / total_logins * 100) if total_logins > 0 else 0
        
        metric = SecurityMetric(
            metric_id="failed_login_rate",
            name="Failed Login Rate",
            description="Percentage of failed login attempts",
            metric_type=MetricType.PERCENTAGE,
            value=rate,
            unit="%",
            timestamp=datetime.now(),
            source="authentication_system",
            threshold_critical=10.0,
            threshold_warning=5.0,
            category="authentication"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def calculate_incident_closure_rate(self, closed_incidents: int, total_incidents: int) -> SecurityMetric:
        """Calculate incident closure rate"""
        rate = (closed_incidents / total_incidents * 100) if total_incidents > 0 else 0
        
        metric = SecurityMetric(
            metric_id="incident_closure_rate",
            name="Incident Closure Rate",
            description="Percentage of incidents closed within SLA",
            metric_type=MetricType.PERCENTAGE,
            value=rate,
            unit="%",
            timestamp=datetime.now(),
            source="incident_management",
            threshold_critical=80.0,
            threshold_warning=90.0,
            category="incident_response"
        )
        
        self._update_trend(metric)
        self.metrics[metric.metric_id] = metric
        return metric
    
    def _update_trend(self, metric: SecurityMetric):
        """Update trend analysis for metric"""
        metric_id = metric.metric_id
        current_time = metric.timestamp
        current_value = metric.value
        
        # Store historical data
        self.historical_data[metric_id].append((current_time, current_value))
        
        # Keep only last 30 data points
        if len(self.historical_data[metric_id]) > 30:
            self.historical_data[metric_id] = self.historical_data[metric_id][-30:]
        
        # Calculate trend if we have enough data
        if len(self.historical_data[metric_id]) >= 2:
            recent_values = [v for _, v in self.historical_data[metric_id][-5:]]  # Last 5 values
            older_values = [v for _, v in self.historical_data[metric_id][-10:-5]] # Previous 5 values
            
            if older_values:
                recent_avg = statistics.mean(recent_values)
                older_avg = statistics.mean(older_values)
                
                change = ((recent_avg - older_avg) / older_avg * 100) if older_avg != 0 else 0
                
                if abs(change) < 2:
                    metric.trend_direction = "stable"
                elif change > 0:
                    metric.trend_direction = "up"
                else:
                    metric.trend_direction = "down"
                
                metric.trend_percentage = abs(change)

class SecurityAnalyticsDashboard:
    """Main security analytics dashboard system"""
    
    def __init__(self):
        self.metrics_calculator = SecurityMetricsCalculator()
        self.dashboards = {}  # dashboard_id -> SecurityDashboard
        self.kpis = {}  # kpi_id -> SecurityKPI
        self.alerts = []  # List of SecurityAlert
        self.threat_analyses = {}  # analysis_id -> ThreatAnalysis
        self.risk_assessments = {}  # assessment_id -> RiskAssessment
        
        # Initialize with sample data
        self._initialize_sample_data()
        
        logger.info("Security analytics dashboard initialized")
    
    def _initialize_sample_data(self):
        """Initialize with sample security data"""
        
        # Calculate sample metrics
        self._calculate_sample_metrics()
        
        # Create sample KPIs
        self._create_sample_kpis()
        
        # Generate sample alerts
        self._generate_sample_alerts()
        
        # Create sample dashboards
        self._create_sample_dashboards()
        
        logger.info("Sample security analytics data initialized")
    
    def _calculate_sample_metrics(self):
        """Calculate sample security metrics"""
        
        # Threat detection metrics
        self.metrics_calculator.calculate_threat_detection_rate(100, 87)
        self.metrics_calculator.calculate_mean_time_to_detection([15, 23, 18, 45, 12, 30, 22])
        self.metrics_calculator.calculate_mean_time_to_response([45, 78, 23, 120, 67, 34, 56])
        
        # Vulnerability metrics
        self.metrics_calculator.calculate_vulnerability_density(234, 150)
        self.metrics_calculator.calculate_patch_compliance_rate(142, 150)
        
        # Authentication metrics
        self.metrics_calculator.calculate_failed_login_rate(45, 1200)
        
        # Incident metrics
        self.metrics_calculator.calculate_incident_closure_rate(28, 32)
        
        # Overall posture
        self.metrics_calculator.calculate_security_posture_score(75.0, 82.0, 88.0)
    
    def _create_sample_kpis(self):
        """Create sample security KPIs"""
        
        kpis_data = [
            {
                'kpi_id': 'kpi_security_incidents',
                'name': 'Monthly Security Incidents',
                'description': 'Number of security incidents per month',
                'current_value': 32,
                'target_value': 25,
                'unit': 'incidents',
                'calculation_method': 'count_monthly'
            },
            {
                'kpi_id': 'kpi_vulnerability_remediation',
                'name': 'Critical Vulnerability Remediation Time',
                'description': 'Average time to remediate critical vulnerabilities',
                'current_value': 3.2,
                'target_value': 2.0,
                'unit': 'days',
                'calculation_method': 'average_time'
            },
            {
                'kpi_id': 'kpi_compliance_score',
                'name': 'Compliance Score',
                'description': 'Overall regulatory compliance score',
                'current_value': 88.5,
                'target_value': 95.0,
                'unit': '%',
                'calculation_method': 'weighted_average'
            },
            {
                'kpi_id': 'kpi_employee_training',
                'name': 'Security Training Completion',
                'description': 'Percentage of employees completed security training',
                'current_value': 92.3,
                'target_value': 100.0,
                'unit': '%',
                'calculation_method': 'percentage'
            },
            {
                'kpi_id': 'kpi_phishing_success',
                'name': 'Phishing Test Success Rate',
                'description': 'Percentage of employees who identified phishing emails',
                'current_value': 78.5,
                'target_value': 90.0,
                'unit': '%',
                'calculation_method': 'percentage'
            }
        ]
        
        for kpi_data in kpis_data:
            # Generate trend data
            trend_data = []
            base_value = kpi_data['current_value']
            for i in range(30):  # Last 30 days
                date = datetime.now() - timedelta(days=29-i)
                # Add some variation
                variation = (i % 7 - 3) * 0.1 * base_value
                value = max(0, base_value + variation)
                trend_data.append((date, value))
            
            # Calculate achievement and status
            achievement = (kpi_data['current_value'] / kpi_data['target_value'] * 100) if kpi_data['target_value'] > 0 else 0
            
            if achievement >= 100:
                status = "excellent"
            elif achievement >= 90:
                status = "good"
            elif achievement >= 75:
                status = "warning"
            else:
                status = "critical"
            
            kpi = SecurityKPI(
                kpi_id=kpi_data['kpi_id'],
                name=kpi_data['name'],
                description=kpi_data['description'],
                current_value=kpi_data['current_value'],
                target_value=kpi_data['target_value'],
                unit=kpi_data['unit'],
                calculation_method=kpi_data['calculation_method'],
                last_updated=datetime.now(),
                trend_data=trend_data,
                achievement_percentage=achievement,
                status=status
            )
            
            self.kpis[kpi.kpi_id] = kpi
    
    def _generate_sample_alerts(self):
        """Generate sample security alerts"""
        
        alerts_data = [
            {
                'title': 'High Failed Login Rate Detected',
                'description': 'Failed login rate exceeded warning threshold of 5%',
                'severity': AlertSeverity.HIGH,
                'metric_id': 'failed_login_rate',
                'threshold_value': 5.0,
                'actual_value': 7.8,
                'source_system': 'authentication_monitor'
            },
            {
                'title': 'Mean Time to Detection Degraded',
                'description': 'MTTD exceeded critical threshold of 60 minutes',
                'severity': AlertSeverity.CRITICAL,
                'metric_id': 'mean_time_to_detection',
                'threshold_value': 60.0,
                'actual_value': 78.5,
                'source_system': 'incident_monitor'
            },
            {
                'title': 'Vulnerability Density Increasing',
                'description': 'Vulnerability density per asset exceeded warning threshold',
                'severity': AlertSeverity.MEDIUM,
                'metric_id': 'vulnerability_density',
                'threshold_value': 2.0,
                'actual_value': 2.8,
                'source_system': 'vulnerability_scanner'
            },
            {
                'title': 'Patch Compliance Below Target',
                'description': 'Patch compliance rate below critical threshold of 80%',
                'severity': AlertSeverity.HIGH,
                'metric_id': 'patch_compliance_rate',
                'threshold_value': 80.0,
                'actual_value': 76.3,
                'source_system': 'patch_management'
            }
        ]
        
        for alert_data in alerts_data:
            alert = SecurityAlert(
                alert_id=str(uuid.uuid4()),
                title=alert_data['title'],
                description=alert_data['description'],
                severity=alert_data['severity'],
                metric_id=alert_data['metric_id'],
                threshold_value=alert_data['threshold_value'],
                actual_value=alert_data['actual_value'],
                timestamp=datetime.now() - timedelta(minutes=30),
                source_system=alert_data['source_system']
            )
            
            self.alerts.append(alert)
    
    def _create_sample_dashboards(self):
        """Create sample security dashboards"""
        
        # Executive Dashboard
        exec_widgets = [
            DashboardWidget(
                widget_id="exec_security_posture",
                title="Security Posture Score",
                widget_type="gauge",
                data_source="metrics",
                query="security_posture_score",
                visualization_config={
                    "min_value": 0,
                    "max_value": 100,
                    "color_ranges": [
                        {"min": 0, "max": 60, "color": "red"},
                        {"min": 60, "max": 80, "color": "yellow"},
                        {"min": 80, "max": 100, "color": "green"}
                    ]
                },
                position={"x": 0, "y": 0, "width": 2, "height": 2}
            ),
            DashboardWidget(
                widget_id="exec_monthly_incidents",
                title="Monthly Incidents Trend",
                widget_type="line_chart",
                data_source="kpis",
                query="kpi_security_incidents",
                visualization_config={
                    "time_range": "last_12_months",
                    "show_target": True
                },
                position={"x": 2, "y": 0, "width": 4, "height": 2}
            ),
            DashboardWidget(
                widget_id="exec_compliance_overview",
                title="Compliance Overview",
                widget_type="bar_chart",
                data_source="compliance",
                query="compliance_frameworks",
                visualization_config={
                    "orientation": "horizontal",
                    "show_percentage": True
                },
                position={"x": 0, "y": 2, "width": 3, "height": 2}
            ),
            DashboardWidget(
                widget_id="exec_risk_heatmap",
                title="Risk Assessment Heatmap",
                widget_type="heatmap",
                data_source="risk",
                query="risk_by_category",
                visualization_config={
                    "categories": ["Network", "Applications", "Data", "Users"],
                    "color_scheme": "red_yellow_green"
                },
                position={"x": 3, "y": 2, "width": 3, "height": 2}
            )
        ]
        
        executive_dashboard = SecurityDashboard(
            dashboard_id="dash_executive",
            name="Executive Security Dashboard",
            description="High-level security metrics for executive leadership",
            dashboard_type=DashboardType.EXECUTIVE,
            widgets=exec_widgets,
            created_by="system",
            created_time=datetime.now() - timedelta(days=30),
            last_modified=datetime.now(),
            is_public=True
        )
        
        # Operations Dashboard
        ops_widgets = [
            DashboardWidget(
                widget_id="ops_threat_detection",
                title="Threat Detection Rate",
                widget_type="metric",
                data_source="metrics",
                query="threat_detection_rate",
                visualization_config={
                    "show_trend": True,
                    "comparison_period": "last_week"
                },
                position={"x": 0, "y": 0, "width": 2, "height": 1}
            ),
            DashboardWidget(
                widget_id="ops_mttd_mttr",
                title="MTTD vs MTTR",
                widget_type="dual_metric",
                data_source="metrics",
                query="mttd_mttr_comparison",
                visualization_config={
                    "metric1": "mean_time_to_detection",
                    "metric2": "mean_time_to_response",
                    "show_targets": True
                },
                position={"x": 2, "y": 0, "width": 2, "height": 1}
            ),
            DashboardWidget(
                widget_id="ops_active_alerts",
                title="Active Security Alerts",
                widget_type="table",
                data_source="alerts",
                query="active_alerts",
                visualization_config={
                    "columns": ["severity", "title", "timestamp", "source"],
                    "max_rows": 10,
                    "auto_refresh": True
                },
                position={"x": 0, "y": 1, "width": 4, "height": 2}
            ),
            DashboardWidget(
                widget_id="ops_incident_timeline",
                title="Incident Timeline",
                widget_type="timeline",
                data_source="incidents",
                query="recent_incidents",
                visualization_config={
                    "time_range": "last_24h",
                    "group_by": "severity"
                },
                position={"x": 4, "y": 0, "width": 2, "height": 3}
            )
        ]
        
        operations_dashboard = SecurityDashboard(
            dashboard_id="dash_operations",
            name="Security Operations Dashboard",
            description="Real-time security operations monitoring",
            dashboard_type=DashboardType.OPERATIONS,
            widgets=ops_widgets,
            created_by="system",
            created_time=datetime.now() - timedelta(days=15),
            last_modified=datetime.now(),
            is_public=True
        )
        
        self.dashboards = {
            executive_dashboard.dashboard_id: executive_dashboard,
            operations_dashboard.dashboard_id: operations_dashboard
        }
    
    def generate_threat_analysis(self, time_range: TimeRange = TimeRange.LAST_24H) -> ThreatAnalysis:
        """Generate comprehensive threat analysis"""
        analysis_id = str(uuid.uuid4())
        start_time = datetime.now() - timedelta(hours=24)
        end_time = datetime.now()
        
        # Simulate threat analysis data
        analysis = ThreatAnalysis(
            analysis_id=analysis_id,
            analysis_type="comprehensive",
            start_time=start_time,
            end_time=end_time,
            total_events=15847,
            threat_score=73.5,
            threat_level="medium",
            top_threats=[
                {
                    "threat_type": "malware",
                    "count": 23,
                    "severity": "high",
                    "trend": "increasing"
                },
                {
                    "threat_type": "phishing",
                    "count": 18,
                    "severity": "medium",
                    "trend": "stable"
                },
                {
                    "threat_type": "unauthorized_access",
                    "count": 12,
                    "severity": "high",
                    "trend": "decreasing"
                },
                {
                    "threat_type": "data_exfiltration",
                    "count": 7,
                    "severity": "critical",
                    "trend": "increasing"
                }
            ],
            attack_patterns=[
                {
                    "pattern": "credential_stuffing",
                    "frequency": 34,
                    "success_rate": 2.3,
                    "target_systems": ["web_apps", "vpn"]
                },
                {
                    "pattern": "lateral_movement",
                    "frequency": 12,
                    "success_rate": 8.7,
                    "target_systems": ["internal_network"]
                },
                {
                    "pattern": "privilege_escalation",
                    "frequency": 8,
                    "success_rate": 12.5,
                    "target_systems": ["domain_controllers"]
                }
            ],
            geographic_distribution={
                "US": 45,
                "CN": 23,
                "RU": 18,
                "DE": 8,
                "UK": 6
            },
            timeline_analysis=[
                {"hour": 2, "events": 450, "threats": 3},
                {"hour": 8, "events": 1200, "threats": 8},
                {"hour": 14, "events": 2100, "threats": 15},
                {"hour": 20, "events": 1800, "threats": 12}
            ],
            recommendations=[
                "Implement additional email security controls to reduce phishing attempts",
                "Enhance endpoint detection capabilities for malware prevention",
                "Review and strengthen access controls for critical systems",
                "Increase monitoring frequency for data exfiltration patterns"
            ]
        )
        
        self.threat_analyses[analysis_id] = analysis
        logger.info(f"Generated threat analysis {analysis_id}")
        return analysis
    
    def generate_risk_assessment(self) -> RiskAssessment:
        """Generate security risk assessment"""
        assessment_id = str(uuid.uuid4())
        
        # Calculate risk scores by category
        risk_categories = {
            "network_security": 72.5,
            "application_security": 68.3,
            "data_protection": 85.2,
            "identity_management": 79.8,
            "compliance": 88.5,
            "incident_response": 75.0,
            "third_party_risk": 65.4
        }
        
        overall_risk = statistics.mean(risk_categories.values())
        
        # Determine risk level
        if overall_risk >= 85:
            risk_level = "low"
        elif overall_risk >= 70:
            risk_level = "medium"
        elif overall_risk >= 55:
            risk_level = "high"
        else:
            risk_level = "critical"
        
        assessment = RiskAssessment(
            assessment_id=assessment_id,
            assessment_date=datetime.now(),
            overall_risk_score=overall_risk,
            risk_level=risk_level,
            risk_categories=risk_categories,
            vulnerabilities=[
                {
                    "cve_id": "CVE-2024-1234",
                    "severity": "critical",
                    "affected_systems": 15,
                    "exploitability": "high",
                    "impact": "data_breach"
                },
                {
                    "cve_id": "CVE-2024-5678",
                    "severity": "high",
                    "affected_systems": 23,
                    "exploitability": "medium",
                    "impact": "system_compromise"
                },
                {
                    "cve_id": "CVE-2024-9012",
                    "severity": "medium",
                    "affected_systems": 45,
                    "exploitability": "low",
                    "impact": "information_disclosure"
                }
            ],
            threat_landscape={
                "active_threat_groups": 12,
                "targeting_industry": True,
                "regional_threats": ["apt29", "lazarus", "carbanak"],
                "emerging_threats": ["ai_powered_attacks", "supply_chain"]
            },
            mitigation_recommendations=[
                {
                    "category": "network_security",
                    "recommendation": "Implement network segmentation",
                    "priority": "high",
                    "effort": "medium",
                    "impact": "high"
                },
                {
                    "category": "application_security",
                    "recommendation": "Deploy application security testing",
                    "priority": "medium",
                    "effort": "low",
                    "impact": "medium"
                },
                {
                    "category": "third_party_risk",
                    "recommendation": "Enhance vendor risk assessment",
                    "priority": "high",
                    "effort": "high",
                    "impact": "high"
                }
            ],
            compliance_status={
                "SOC2": {"status": "compliant", "score": 92.5},
                "GDPR": {"status": "compliant", "score": 88.7},
                "HIPAA": {"status": "non_compliant", "score": 74.2},
                "PCI_DSS": {"status": "compliant", "score": 95.1}
            }
        )
        
        self.risk_assessments[assessment_id] = assessment
        logger.info(f"Generated risk assessment {assessment_id}")
        return assessment
    
    def get_security_summary(self) -> Dict[str, Any]:
        """Get comprehensive security analytics summary"""
        
        # Get latest metrics
        metrics_summary = {}
        for metric_id, metric in self.metrics_calculator.metrics.items():
            metrics_summary[metric_id] = {
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "trend": metric.trend_direction,
                "status": self._get_metric_status(metric)
            }
        
        # Get KPI summary
        kpi_summary = {}
        for kpi_id, kpi in self.kpis.items():
            kpi_summary[kpi_id] = {
                "name": kpi.name,
                "current_value": kpi.current_value,
                "target_value": kpi.target_value,
                "achievement": kpi.achievement_percentage,
                "status": kpi.status
            }
        
        # Get alert summary
        alert_summary = {
            "total_alerts": len(self.alerts),
            "by_severity": Counter(alert.severity.value for alert in self.alerts),
            "unacknowledged": len([a for a in self.alerts if not a.acknowledged]),
            "recent_alerts": [
                {
                    "title": alert.title,
                    "severity": alert.severity.value,
                    "timestamp": alert.timestamp.isoformat()
                }
                for alert in sorted(self.alerts, key=lambda a: a.timestamp, reverse=True)[:5]
            ]
        }
        
        # Calculate overall security health
        metric_scores = []
        for metric in self.metrics_calculator.metrics.values():
            if metric.threshold_warning and metric.threshold_critical:
                if metric.value >= metric.threshold_warning:
                    score = 100
                elif metric.value >= metric.threshold_critical:
                    score = 75
                else:
                    score = 50
                metric_scores.append(score)
        
        overall_health = statistics.mean(metric_scores) if metric_scores else 0
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_security_health": round(overall_health, 1),
            "metrics_summary": metrics_summary,
            "kpi_summary": kpi_summary,
            "alert_summary": alert_summary,
            "dashboard_count": len(self.dashboards),
            "last_threat_analysis": max([ta.end_time for ta in self.threat_analyses.values()]).isoformat() if self.threat_analyses else None,
            "last_risk_assessment": max([ra.assessment_date for ra in self.risk_assessments.values()]).isoformat() if self.risk_assessments else None
        }
    
    def _get_metric_status(self, metric: SecurityMetric) -> str:
        """Get status for a metric based on thresholds"""
        if metric.threshold_critical and metric.threshold_warning:
            if metric.value >= metric.threshold_warning:
                return "good"
            elif metric.value >= metric.threshold_critical:
                return "warning"
            else:
                return "critical"
        return "unknown"

async def demonstrate_security_analytics():
    """Demonstrate the security analytics dashboard system"""
    print("AIOps Security Analytics Dashboard Demo")
    print("=" * 47)
    
    # Initialize security analytics dashboard
    analytics = SecurityAnalyticsDashboard()
    
    print("📊 Security analytics dashboard initialized with comprehensive metrics\n")
    
    # Show security summary
    summary = analytics.get_security_summary()
    
    print("🎯 Overall Security Health Score:", f"{summary['overall_security_health']}%")
    
    health_icon = "🟢" if summary['overall_security_health'] >= 80 else "🟡" if summary['overall_security_health'] >= 60 else "🔴"
    print(f"Status: {health_icon}")
    
    # Show key metrics
    print(f"\n📈 Key Security Metrics:")
    for metric_id, metric_data in summary['metrics_summary'].items():
        status_icon = {"good": "🟢", "warning": "🟡", "critical": "🔴"}.get(metric_data['status'], "❓")
        trend_icon = {"up": "📈", "down": "📉", "stable": "➡️"}.get(metric_data['trend'], "")
        
        print(f"  {status_icon} {metric_data['name']}: {metric_data['value']:.1f}{metric_data['unit']} {trend_icon}")
    
    # Show KPIs
    print(f"\n🎯 Security KPIs:")
    for kpi_id, kpi_data in summary['kpi_summary'].items():
        status_icon = {"excellent": "🟢", "good": "🟢", "warning": "🟡", "critical": "🔴"}.get(kpi_data['status'], "❓")
        print(f"  {status_icon} {kpi_data['name']}: {kpi_data['current_value']:.1f}{kpi_data.get('unit', '')} (Target: {kpi_data['target_value']:.1f})")
        print(f"      Achievement: {kpi_data['achievement']:.1f}%")
    
    # Show alerts
    print(f"\n🚨 Security Alerts Summary:")
    alert_summary = summary['alert_summary']
    print(f"  Total Alerts: {alert_summary['total_alerts']}")
    print(f"  Unacknowledged: {alert_summary['unacknowledged']}")
    
    print(f"  By Severity:")
    for severity, count in alert_summary['by_severity'].items():
        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}.get(severity, "❓")
        print(f"    {severity_icon} {severity}: {count}")
    
    if alert_summary['recent_alerts']:
        print(f"  Recent Alerts:")
        for alert in alert_summary['recent_alerts'][:3]:
            severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}.get(alert['severity'], "❓")
            print(f"    {severity_icon} {alert['title']}")
    
    # Generate threat analysis
    print(f"\n🔍 Generating threat analysis...")
    threat_analysis = analytics.generate_threat_analysis()
    
    print(f"  Analysis ID: {threat_analysis.analysis_id}")
    print(f"  Total Events Analyzed: {threat_analysis.total_events:,}")
    print(f"  Threat Score: {threat_analysis.threat_score:.1f}/100")
    print(f"  Threat Level: {threat_analysis.threat_level}")
    
    print(f"\n🎯 Top Threats Detected:")
    for threat in threat_analysis.top_threats:
        trend_icon = {"increasing": "📈", "decreasing": "📉", "stable": "➡️"}.get(threat['trend'], "")
        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(threat['severity'], "❓")
        print(f"    {severity_icon} {threat['threat_type']}: {threat['count']} events {trend_icon}")
    
    print(f"\n🌍 Geographic Distribution:")
    for country, count in threat_analysis.geographic_distribution.items():
        print(f"    {country}: {count} events")
    
    print(f"\n🔧 Attack Patterns:")
    for pattern in threat_analysis.attack_patterns:
        print(f"    • {pattern['pattern']}: {pattern['frequency']} attempts ({pattern['success_rate']:.1f}% success rate)")
    
    # Generate risk assessment
    print(f"\n🛡️ Generating risk assessment...")
    risk_assessment = analytics.generate_risk_assessment()
    
    print(f"  Assessment ID: {risk_assessment.assessment_id}")
    print(f"  Overall Risk Score: {risk_assessment.overall_risk_score:.1f}/100")
    print(f"  Risk Level: {risk_assessment.risk_level}")
    
    print(f"\n📊 Risk by Category:")
    for category, score in risk_assessment.risk_categories.items():
        risk_icon = "🟢" if score >= 80 else "🟡" if score >= 65 else "🔴"
        print(f"    {risk_icon} {category.replace('_', ' ').title()}: {score:.1f}/100")
    
    print(f"\n🔍 Critical Vulnerabilities:")
    for vuln in risk_assessment.vulnerabilities:
        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(vuln['severity'], "❓")
        print(f"    {severity_icon} {vuln['cve_id']}: {vuln['affected_systems']} systems affected")
    
    print(f"\n✅ Compliance Status:")
    for framework, status in risk_assessment.compliance_status.items():
        status_icon = "🟢" if status['status'] == 'compliant' else "🔴"
        print(f"    {status_icon} {framework}: {status['status']} ({status['score']:.1f}%)")
    
    # Show dashboard information
    print(f"\n📱 Available Dashboards:")
    for dashboard_id, dashboard in analytics.dashboards.items():
        print(f"  • {dashboard.name}")
        print(f"    Type: {dashboard.dashboard_type.value}")
        print(f"    Widgets: {len(dashboard.widgets)}")
        print(f"    Created: {dashboard.created_time.strftime('%Y-%m-%d')}")
        
        print(f"    Widget Types:")
        widget_types = Counter(w.widget_type for w in dashboard.widgets)
        for widget_type, count in widget_types.items():
            print(f"      - {widget_type}: {count}")
    
    # Show threat analysis recommendations
    print(f"\n💡 Security Recommendations:")
    for i, recommendation in enumerate(threat_analysis.recommendations, 1):
        print(f"  {i}. {recommendation}")
    
    print(f"\n🛠️ Risk Mitigation Recommendations:")
    for rec in risk_assessment.mitigation_recommendations:
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec['priority'], "❓")
        print(f"    {priority_icon} {rec['recommendation']} (Priority: {rec['priority']})")
        print(f"      Category: {rec['category'].replace('_', ' ').title()}")
        print(f"      Effort: {rec['effort']}, Impact: {rec['impact']}")
    
    print(f"\n📊 Dashboard Features:")
    print(f"  • Real-time security metrics monitoring")
    print(f"  • Executive and operational dashboards")
    print(f"  • Automated threat analysis and scoring")
    print(f"  • Comprehensive risk assessments")
    print(f"  • KPI tracking and target monitoring")
    print(f"  • Intelligent alerting and notifications")
    print(f"  • Trend analysis and forecasting")
    print(f"  • Compliance monitoring and reporting")
    
    print(f"\n🎯 Analytics Capabilities:")
    print(f"  • Threat detection rate optimization")
    print(f"  • Incident response time analysis")
    print(f"  • Vulnerability management tracking")
    print(f"  • Security posture scoring")
    print(f"  • Predictive threat modeling")
    print(f"  • Risk-based prioritization")
    print(f"  • Compliance gap analysis")
    
    print(f"\n✅ Security analytics dashboard demonstration completed!")
    print(f"🏆 Key Benefits:")
    print(f"  • Centralized security visibility")
    print(f"  • Data-driven decision making")
    print(f"  • Proactive threat detection")
    print(f"  • Comprehensive risk management")
    print(f"  • Automated reporting and compliance")
    print(f"  • Executive and operational insights")

if __name__ == "__main__":
    asyncio.run(demonstrate_security_analytics())