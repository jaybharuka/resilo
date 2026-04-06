#!/usr/bin/env python3
"""
Intelligent Alert Correlation System for AIOps Bot
Analyzes metric relationships, suppresses duplicates, and identifies root causes
"""

import json
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Alert:
    """Enhanced alert with correlation metadata"""
    id: str
    metric: str
    severity: str
    value: float
    threshold: float
    message: str
    timestamp: datetime
    source: str = "system"
    
    # Correlation fields
    correlation_id: Optional[str] = None
    parent_alert_id: Optional[str] = None
    related_alerts: List[str] = field(default_factory=list)
    root_cause_confidence: float = 0.0
    suppressed: bool = False
    suppression_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert alert to dictionary"""
        return {
            'id': self.id,
            'metric': self.metric,
            'severity': self.severity,
            'value': self.value,
            'threshold': self.threshold,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
            'correlation_id': self.correlation_id,
            'parent_alert_id': self.parent_alert_id,
            'related_alerts': self.related_alerts,
            'root_cause_confidence': self.root_cause_confidence,
            'suppressed': self.suppressed,
            'suppression_reason': self.suppression_reason
        }

@dataclass
class MetricRelationship:
    """Defines relationship between two metrics"""
    source_metric: str
    target_metric: str
    correlation_strength: float  # -1 to 1
    lag_seconds: int  # How long target follows source
    confidence: float  # 0 to 1
    relationship_type: str  # 'causes', 'correlates', 'inverse'
    
class AlertCorrelationEngine:
    """Intelligent alert correlation and root cause analysis"""
    
    def __init__(self):
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.metric_relationships: Dict[str, List[MetricRelationship]] = defaultdict(list)
        self.correlation_groups: Dict[str, List[str]] = {}
        
        # Time windows for correlation analysis
        self.correlation_window = 300  # 5 minutes
        self.causality_window = 60     # 1 minute for cause-effect detection
        
        # Thresholds for correlation decisions
        self.min_correlation_strength = 0.6
        self.min_relationship_confidence = 0.7
        self.max_alerts_per_group = 10
        
        # Metric relationship rules (can be learned over time)
        self._initialize_known_relationships()
        
        logger.info("🔗 Alert Correlation Engine initialized")
    
    def _initialize_known_relationships(self):
        """Initialize known metric relationships"""
        # System resource relationships
        relationships = [
            # CPU causes response time increases
            MetricRelationship(
                source_metric="system_cpu_usage_percent",
                target_metric="app_response_time_seconds", 
                correlation_strength=0.8,
                lag_seconds=30,
                confidence=0.9,
                relationship_type="causes"
            ),
            # Memory pressure causes error rates
            MetricRelationship(
                source_metric="system_memory_usage_percent",
                target_metric="app_error_rate_percent",
                correlation_strength=0.7,
                lag_seconds=60,
                confidence=0.8,
                relationship_type="causes"
            ),
            # High response time correlates with low throughput
            MetricRelationship(
                source_metric="app_response_time_seconds",
                target_metric="app_throughput_requests_per_sec",
                correlation_strength=-0.9,
                lag_seconds=15,
                confidence=0.95,
                relationship_type="inverse"
            ),
            # Disk usage affects overall performance
            MetricRelationship(
                source_metric="system_disk_usage_percent",
                target_metric="system_cpu_usage_percent",
                correlation_strength=0.6,
                lag_seconds=45,
                confidence=0.7,
                relationship_type="correlates"
            )
        ]
        
        for rel in relationships:
            self.metric_relationships[rel.source_metric].append(rel)
            
        logger.info(f"📊 Initialized {len(relationships)} known metric relationships")
    
    def add_alert(self, alert: Alert) -> Alert:
        """Add new alert and perform correlation analysis"""
        try:
            # Generate unique ID if not provided
            if not alert.id:
                alert.id = f"{alert.metric}_{int(alert.timestamp.timestamp())}"
            
            # Add to active alerts
            self.active_alerts[alert.id] = alert
            self.alert_history.append(alert)
            
            # Perform correlation analysis
            self._correlate_alert(alert)
            
            logger.info(f"➕ Alert added: {alert.metric} [{alert.severity}] - {alert.message}")
            
            return alert
            
        except Exception as e:
            logger.error(f"❌ Error adding alert: {e}")
            return alert
    
    def _correlate_alert(self, new_alert: Alert):
        """Correlate new alert with existing alerts"""
        try:
            # Find related alerts based on timing and relationships
            related_alerts = self._find_related_alerts(new_alert)
            
            if related_alerts:
                # Check if this should be suppressed or grouped
                correlation_result = self._analyze_correlation(new_alert, related_alerts)
                self._apply_correlation_result(new_alert, correlation_result)
            else:
                # No correlations found - might be a root cause
                new_alert.root_cause_confidence = 0.8
                logger.info(f"🎯 Potential root cause: {new_alert.metric}")
            
        except Exception as e:
            logger.error(f"❌ Error correlating alert: {e}")
    
    def _find_related_alerts(self, alert: Alert) -> List[Alert]:
        """Find alerts related to the given alert"""
        related = []
        cutoff_time = alert.timestamp - timedelta(seconds=self.correlation_window)
        
        for existing_alert in self.active_alerts.values():
            if existing_alert.id == alert.id:
                continue
                
            if existing_alert.timestamp < cutoff_time:
                continue
            
            # Check for direct metric relationships
            if self._are_metrics_related(existing_alert.metric, alert.metric):
                related.append(existing_alert)
                continue
            
            # Check for same metric (potential duplicate)
            if existing_alert.metric == alert.metric:
                time_diff = abs((alert.timestamp - existing_alert.timestamp).total_seconds())
                if time_diff < 120:  # Within 2 minutes
                    related.append(existing_alert)
                    continue
            
            # Check for same system/service
            if self._are_same_system(existing_alert.metric, alert.metric):
                related.append(existing_alert)
        
        return related
    
    def _are_metrics_related(self, metric1: str, metric2: str) -> bool:
        """Check if two metrics have known relationships"""
        # Check direct relationships
        for rel in self.metric_relationships.get(metric1, []):
            if rel.target_metric == metric2 and rel.confidence >= self.min_relationship_confidence:
                return True
        
        for rel in self.metric_relationships.get(metric2, []):
            if rel.target_metric == metric1 and rel.confidence >= self.min_relationship_confidence:
                return True
        
        return False
    
    def _are_same_system(self, metric1: str, metric2: str) -> bool:
        """Check if metrics belong to the same system component"""
        system_groups = {
            'system': ['system_cpu', 'system_memory', 'system_disk'],
            'application': ['app_response', 'app_error', 'app_throughput'],
            'network': ['network_', 'http_requests'],
            'database': ['db_', 'database_', 'sql_']
        }
        
        for group_metrics in system_groups.values():
            metric1_in_group = any(prefix in metric1.lower() for prefix in group_metrics)
            metric2_in_group = any(prefix in metric2.lower() for prefix in group_metrics)
            
            if metric1_in_group and metric2_in_group:
                return True
        
        return False
    
    def _analyze_correlation(self, new_alert: Alert, related_alerts: List[Alert]) -> dict:
        """Analyze correlation between new alert and related alerts"""
        result = {
            'action': 'none',  # 'suppress', 'group', 'escalate', 'none'
            'correlation_id': None,
            'parent_alert_id': None,
            'root_cause_confidence': 0.0,
            'suppression_reason': None
        }
        
        try:
            # Check for exact duplicates (same metric, similar time)
            for related in related_alerts:
                if related.metric == new_alert.metric:
                    time_diff = abs((new_alert.timestamp - related.timestamp).total_seconds())
                    if time_diff < 60:  # Within 1 minute
                        result['action'] = 'suppress'
                        result['suppression_reason'] = f"Duplicate of alert {related.id}"
                        result['parent_alert_id'] = related.id
                        return result
            
            # Check for causal relationships
            root_cause_alert = self._identify_root_cause(new_alert, related_alerts)
            if root_cause_alert:
                if root_cause_alert.id == new_alert.id:
                    # This is the root cause
                    result['root_cause_confidence'] = 0.9
                    result['action'] = 'escalate'
                else:
                    # This is a symptom
                    result['action'] = 'group'
                    result['parent_alert_id'] = root_cause_alert.id
                    result['correlation_id'] = root_cause_alert.correlation_id or root_cause_alert.id
                    result['suppression_reason'] = f"Symptom of {root_cause_alert.metric} issue"
            
            # Check for cascade effects
            cascade_confidence = self._calculate_cascade_confidence(new_alert, related_alerts)
            if cascade_confidence > 0.7:
                result['action'] = 'group'
                result['correlation_id'] = self._get_or_create_correlation_id(related_alerts)
                result['suppression_reason'] = f"Part of cascade effect (confidence: {cascade_confidence:.1%})"
            
        except Exception as e:
            logger.error(f"❌ Error analyzing correlation: {e}")
        
        return result
    
    def _identify_root_cause(self, new_alert: Alert, related_alerts: List[Alert]) -> Optional[Alert]:
        """Identify the root cause among related alerts"""
        all_alerts = [new_alert] + related_alerts
        
        # Sort by timestamp to find the earliest
        all_alerts.sort(key=lambda a: a.timestamp)
        
        # Look for known causal relationships
        for i, alert in enumerate(all_alerts):
            for j, other_alert in enumerate(all_alerts[i+1:], i+1):
                for rel in self.metric_relationships.get(alert.metric, []):
                    if (rel.target_metric == other_alert.metric and 
                        rel.relationship_type == 'causes' and
                        rel.confidence >= self.min_relationship_confidence):
                        
                        # Check if timing matches expected lag
                        time_diff = (other_alert.timestamp - alert.timestamp).total_seconds()
                        if abs(time_diff - rel.lag_seconds) < 60:  # Within 1 minute of expected lag
                            return alert  # This is the root cause
        
        # If no causal relationship found, assume earliest alert is root cause
        return all_alerts[0] if all_alerts else None
    
    def _calculate_cascade_confidence(self, new_alert: Alert, related_alerts: List[Alert]) -> float:
        """Calculate confidence that this is part of a cascade effect"""
        if not related_alerts:
            return 0.0
        
        # Factors that increase cascade confidence:
        # 1. Multiple related alerts in short time
        # 2. Alerts follow known patterns
        # 3. Severity escalation over time
        
        confidence = 0.0
        
        # Time clustering factor
        time_window = 300  # 5 minutes
        recent_alerts = [a for a in related_alerts 
                        if (new_alert.timestamp - a.timestamp).total_seconds() < time_window]
        
        if len(recent_alerts) >= 2:
            confidence += 0.4
        
        # Known relationship factor
        relationship_count = 0
        for related in related_alerts:
            if self._are_metrics_related(new_alert.metric, related.metric):
                relationship_count += 1
        
        if relationship_count > 0:
            confidence += min(0.4, relationship_count * 0.2)
        
        # Severity progression factor
        severities = {'info': 1, 'warning': 2, 'critical': 3}
        alert_severities = [severities.get(a.severity, 1) for a in [new_alert] + related_alerts]
        
        if len(set(alert_severities)) > 1:  # Multiple severity levels
            confidence += 0.2
        
        return min(1.0, confidence)
    
    def _get_or_create_correlation_id(self, related_alerts: List[Alert]) -> str:
        """Get existing correlation ID or create new one"""
        # Check if any related alert already has a correlation ID
        for alert in related_alerts:
            if alert.correlation_id:
                return alert.correlation_id
        
        # Create new correlation ID
        timestamp = int(datetime.now().timestamp())
        return f"corr_{timestamp}"
    
    def _apply_correlation_result(self, alert: Alert, result: dict):
        """Apply the correlation analysis result to the alert"""
        try:
            alert.correlation_id = result.get('correlation_id')
            alert.parent_alert_id = result.get('parent_alert_id')
            alert.root_cause_confidence = result.get('root_cause_confidence', 0.0)
            
            if result['action'] == 'suppress':
                alert.suppressed = True
                alert.suppression_reason = result['suppression_reason']
                logger.info(f"🚫 Alert suppressed: {alert.id} - {result['suppression_reason']}")
            
            elif result['action'] == 'group':
                alert.correlation_id = result['correlation_id']
                if result.get('suppression_reason'):
                    alert.suppression_reason = result['suppression_reason']
                logger.info(f"🔗 Alert grouped: {alert.id} -> {result['correlation_id']}")
            
            elif result['action'] == 'escalate':
                alert.root_cause_confidence = result['root_cause_confidence']
                logger.info(f"🎯 Root cause identified: {alert.id} (confidence: {result['root_cause_confidence']:.1%})")
            
            # Update related alerts
            self._update_related_alerts(alert, result)
            
        except Exception as e:
            logger.error(f"❌ Error applying correlation result: {e}")
    
    def _update_related_alerts(self, alert: Alert, result: dict):
        """Update related alerts with correlation information"""
        if not alert.correlation_id:
            return
        
        # Find and update related alerts
        for existing_alert in self.active_alerts.values():
            if existing_alert.id == alert.id:
                continue
            
            # Add to correlation group if related
            if (alert.parent_alert_id == existing_alert.id or 
                existing_alert.correlation_id == alert.correlation_id):
                
                if alert.id not in existing_alert.related_alerts:
                    existing_alert.related_alerts.append(alert.id)
                
                if existing_alert.id not in alert.related_alerts:
                    alert.related_alerts.append(existing_alert.id)
    
    def get_active_alerts(self, include_suppressed: bool = False) -> List[Alert]:
        """Get list of active alerts"""
        alerts = list(self.active_alerts.values())
        
        if not include_suppressed:
            alerts = [a for a in alerts if not a.suppressed]
        
        # Sort by severity and timestamp
        severity_order = {'critical': 3, 'warning': 2, 'info': 1}
        alerts.sort(key=lambda a: (severity_order.get(a.severity, 0), a.timestamp), reverse=True)
        
        return alerts
    
    def get_correlation_summary(self) -> dict:
        """Get summary of correlation analysis"""
        active_alerts = list(self.active_alerts.values())
        
        # Count alerts by status
        total_alerts = len(active_alerts)
        suppressed_alerts = len([a for a in active_alerts if a.suppressed])
        root_causes = len([a for a in active_alerts if a.root_cause_confidence > 0.7])
        
        # Count correlation groups
        correlation_groups = set(a.correlation_id for a in active_alerts if a.correlation_id)
        
        # Calculate suppression effectiveness
        suppression_rate = suppressed_alerts / total_alerts if total_alerts > 0 else 0
        
        return {
            'total_alerts': total_alerts,
            'active_alerts': total_alerts - suppressed_alerts,
            'suppressed_alerts': suppressed_alerts,
            'suppression_rate': suppression_rate,
            'root_causes_identified': root_causes,
            'correlation_groups': len(correlation_groups),
            'alert_reduction': f"{suppression_rate:.1%}"
        }
    
    def get_root_cause_analysis(self) -> List[dict]:
        """Get root cause analysis for current alerts"""
        root_causes = []
        
        # Find high-confidence root causes
        for alert in self.active_alerts.values():
            if alert.root_cause_confidence > 0.7 and not alert.suppressed:
                # Find related symptoms
                symptoms = [a for a in self.active_alerts.values() 
                           if a.parent_alert_id == alert.id or 
                              a.correlation_id == alert.correlation_id]
                
                root_causes.append({
                    'root_cause': alert.to_dict(),
                    'symptoms': [s.to_dict() for s in symptoms if s.id != alert.id],
                    'confidence': alert.root_cause_confidence,
                    'impact_metrics': list(set([alert.metric] + [s.metric for s in symptoms]))
                })
        
        return root_causes
    
    def cleanup_old_alerts(self, max_age_hours: int = 24):
        """Clean up old resolved alerts"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for alert_id, alert in self.active_alerts.items():
            if alert.timestamp < cutoff_time:
                to_remove.append(alert_id)
        
        for alert_id in to_remove:
            del self.active_alerts[alert_id]
        
        if to_remove:
            logger.info(f"🧹 Cleaned up {len(to_remove)} old alerts")

def main():
    """Test the alert correlation system"""
    print("🔗 Alert Correlation System Test")
    print("=" * 40)
    
    engine = AlertCorrelationEngine()
    
    # Create test alerts that should be correlated
    base_time = datetime.now()
    
    # Scenario 1: CPU spike causes response time increase
    cpu_alert = Alert(
        id="cpu_001",
        metric="system_cpu_usage_percent",
        severity="warning",
        value=85.0,
        threshold=80.0,
        message="High CPU usage detected",
        timestamp=base_time
    )
    
    response_alert = Alert(
        id="resp_001", 
        metric="app_response_time_seconds",
        severity="warning",
        value=2.5,
        threshold=1.0,
        message="Response time degraded",
        timestamp=base_time + timedelta(seconds=30)
    )
    
    # Scenario 2: Memory pressure causes errors
    memory_alert = Alert(
        id="mem_001",
        metric="system_memory_usage_percent", 
        severity="critical",
        value=95.0,
        threshold=90.0,
        message="Memory usage critical",
        timestamp=base_time + timedelta(seconds=60)
    )
    
    error_alert = Alert(
        id="err_001",
        metric="app_error_rate_percent",
        severity="warning", 
        value=8.0,
        threshold=5.0,
        message="Error rate increased",
        timestamp=base_time + timedelta(seconds=120)
    )
    
    # Add alerts and see correlation
    print("\n📊 Adding test alerts...")
    engine.add_alert(cpu_alert)
    engine.add_alert(response_alert)
    engine.add_alert(memory_alert)
    engine.add_alert(error_alert)
    
    # Show results
    print(f"\n📈 Correlation Summary:")
    summary = engine.get_correlation_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")
    
    print(f"\n🎯 Root Cause Analysis:")
    root_causes = engine.get_root_cause_analysis()
    for rc in root_causes:
        print(f"   Root Cause: {rc['root_cause']['metric']} (confidence: {rc['confidence']:.1%})")
        print(f"   Symptoms: {[s['metric'] for s in rc['symptoms']]}")
    
    print(f"\n🔍 Active Alerts:")
    for alert in engine.get_active_alerts():
        status = "SUPPRESSED" if alert.suppressed else "ACTIVE"
        print(f"   [{status}] {alert.metric}: {alert.message}")
        if alert.suppression_reason:
            print(f"       Reason: {alert.suppression_reason}")

if __name__ == "__main__":
    main()