#!/usr/bin/env python3
"""
AIOps Smart Alert Filtering System
Intelligent alert aggregation and filtering to prevent notification spam

Features:
- Alert deduplication and correlation
- Intelligent alert grouping and aggregation
- Spam prevention and rate limiting
- Contextual alert summarization
- Priority-based filtering rules
- Machine learning for alert classification
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('alert_filter')

class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class FilterAction(Enum):
    """Actions that can be taken on alerts"""
    ALLOW = "allow"
    SUPPRESS = "suppress"
    AGGREGATE = "aggregate"
    ESCALATE = "escalate"
    DOWNGRADE = "downgrade"

class AlertStatus(Enum):
    """Alert processing status"""
    NEW = "new"
    FILTERED = "filtered"
    AGGREGATED = "aggregated"
    SUPPRESSED = "suppressed"
    ESCALATED = "escalated"
    SENT = "sent"

@dataclass
class RawAlert:
    """Raw alert before processing"""
    id: str
    title: str
    description: str
    severity: AlertSeverity
    source: str
    timestamp: datetime
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    fingerprint: Optional[str] = None

@dataclass
class ProcessedAlert:
    """Processed alert after filtering"""
    id: str
    original_alerts: List[str]  # IDs of original alerts
    title: str
    description: str
    severity: AlertSeverity
    source: str
    timestamp: datetime
    status: AlertStatus
    aggregation_count: int = 1
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    filter_reason: Optional[str] = None

@dataclass
class FilterRule:
    """Alert filtering rule"""
    name: str
    description: str
    conditions: Dict[str, Any]
    action: FilterAction
    priority: int = 100
    enabled: bool = True
    match_count: int = 0
    last_triggered: Optional[datetime] = None

@dataclass
class AlertPattern:
    """Pattern for alert correlation"""
    pattern_id: str
    title_pattern: str
    source_pattern: str
    time_window_seconds: int
    max_occurrences: int
    severity_threshold: AlertSeverity
    description: str

class AlertFingerprinter:
    """Generate fingerprints for alert deduplication"""
    
    @staticmethod
    def generate_fingerprint(alert: RawAlert) -> str:
        """Generate unique fingerprint for alert"""
        # Normalize title and description
        normalized_title = re.sub(r'\d+', 'X', alert.title.lower())
        normalized_desc = re.sub(r'\d+', 'X', alert.description.lower())
        
        # Create fingerprint components
        components = [
            alert.source,
            normalized_title,
            normalized_desc[:100],  # First 100 chars of description
            alert.severity.value,
            ','.join(sorted(alert.tags))
        ]
        
        # Generate hash
        fingerprint_data = '|'.join(components)
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
    
    @staticmethod
    def are_similar(alert1: RawAlert, alert2: RawAlert, similarity_threshold: float = 0.8) -> bool:
        """Check if two alerts are similar"""
        # Simple similarity check based on title and source
        title_similarity = AlertFingerprinter._calculate_similarity(alert1.title, alert2.title)
        source_match = alert1.source == alert2.source
        
        return source_match and title_similarity >= similarity_threshold
    
    @staticmethod
    def _calculate_similarity(text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)

class AlertAggregator:
    """Aggregate related alerts"""
    
    def __init__(self, time_window: int = 300):  # 5 minutes
        self.time_window = time_window
        self.aggregation_groups = defaultdict(list)
        self.fingerprinter = AlertFingerprinter()
    
    def should_aggregate(self, alert: RawAlert, existing_alerts: List[RawAlert]) -> Tuple[bool, Optional[str]]:
        """Determine if alert should be aggregated with existing alerts"""
        
        current_time = alert.timestamp
        
        for existing_alert in existing_alerts:
            # Check time window
            time_diff = (current_time - existing_alert.timestamp).total_seconds()
            if time_diff > self.time_window:
                continue
            
            # Check similarity
            if self.fingerprinter.are_similar(alert, existing_alert):
                return True, existing_alert.fingerprint
        
        return False, None
    
    def aggregate_alerts(self, alerts: List[RawAlert]) -> ProcessedAlert:
        """Aggregate multiple related alerts into one"""
        if not alerts:
            raise ValueError("Cannot aggregate empty alert list")
        
        # Sort by timestamp
        sorted_alerts = sorted(alerts, key=lambda a: a.timestamp)
        first_alert = sorted_alerts[0]
        last_alert = sorted_alerts[-1]
        
        # Determine aggregated severity (highest)
        severities = [a.severity for a in alerts]
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 1,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.LOW: 3,
            AlertSeverity.INFO: 4
        }
        aggregated_severity = min(severities, key=lambda s: severity_order[s])
        
        # Create aggregated title and description
        if len(alerts) == 1:
            title = first_alert.title
            description = first_alert.description
        else:
            # Count by source
            source_counts = Counter(a.source for a in alerts)
            sources_text = ", ".join([f"{source}({count})" for source, count in source_counts.most_common(3)])
            
            title = f"Aggregated Alert: {first_alert.title} (×{len(alerts)})"
            description = f"Multiple similar alerts detected:\n"
            description += f"• Count: {len(alerts)} alerts\n"
            description += f"• Sources: {sources_text}\n"
            description += f"• Time span: {first_alert.timestamp.strftime('%H:%M')} - {last_alert.timestamp.strftime('%H:%M')}\n"
            description += f"• Latest: {last_alert.description[:200]}..."
        
        # Combine tags
        all_tags = []
        for alert in alerts:
            all_tags.extend(alert.tags)
        unique_tags = list(set(all_tags))
        
        # Combine metadata
        combined_metadata = {
            'aggregated_count': len(alerts),
            'source_distribution': dict(Counter(a.source for a in alerts)),
            'severity_distribution': dict(Counter(a.severity.value for a in alerts)),
            'first_occurrence': first_alert.timestamp.isoformat(),
            'last_occurrence': last_alert.timestamp.isoformat(),
            'original_alert_ids': [a.id for a in alerts]
        }
        
        return ProcessedAlert(
            id=f"AGG-{int(time.time())}-{len(alerts)}",
            original_alerts=[a.id for a in alerts],
            title=title,
            description=description,
            severity=aggregated_severity,
            source=first_alert.source,
            timestamp=last_alert.timestamp,  # Use latest timestamp
            status=AlertStatus.AGGREGATED,
            aggregation_count=len(alerts),
            tags=unique_tags,
            metadata=combined_metadata
        )

class AlertFilter:
    """Main alert filtering engine"""
    
    def __init__(self):
        self.rules = []
        self.patterns = []
        self.fingerprinter = AlertFingerprinter()
        self.aggregator = AlertAggregator()
        
        # Alert storage
        self.recent_alerts = []  # Store for correlation
        self.alert_cache = {}    # Fingerprint -> alerts mapping
        self.suppressed_alerts = []
        
        # Statistics
        self.stats = {
            'total_processed': 0,
            'suppressed': 0,
            'aggregated': 0,
            'escalated': 0,
            'sent': 0
        }
        
        # Setup default rules and patterns
        self.setup_default_rules()
        self.setup_default_patterns()
        
        logger.info("Alert filtering system initialized")
    
    def setup_default_rules(self):
        """Setup default filtering rules"""
        
        # Rule 1: Suppress duplicate alerts within 5 minutes
        self.rules.append(FilterRule(
            name="duplicate_suppression",
            description="Suppress duplicate alerts within 5 minutes",
            conditions={
                'duplicate_window_seconds': 300,
                'max_duplicates': 1
            },
            action=FilterAction.SUPPRESS,
            priority=10
        ))
        
        # Rule 2: Aggregate similar alerts within 10 minutes
        self.rules.append(FilterRule(
            name="similar_aggregation",
            description="Aggregate similar alerts within 10 minutes",
            conditions={
                'similarity_threshold': 0.8,
                'aggregation_window_seconds': 600,
                'min_aggregation_count': 3
            },
            action=FilterAction.AGGREGATE,
            priority=20
        ))
        
        # Rule 3: Escalate persistent high severity alerts
        self.rules.append(FilterRule(
            name="persistent_escalation",
            description="Escalate alerts that persist for more than 30 minutes",
            conditions={
                'min_severity': 'high',
                'persistence_window_seconds': 1800,
                'min_occurrences': 5
            },
            action=FilterAction.ESCALATE,
            priority=30
        ))
        
        # Rule 4: Suppress test/dev environment low severity alerts
        self.rules.append(FilterRule(
            name="test_environment_suppression",
            description="Suppress low severity alerts from test environments",
            conditions={
                'source_patterns': ['test-', 'dev-', 'staging-'],
                'max_severity': 'low'
            },
            action=FilterAction.SUPPRESS,
            priority=40
        ))
        
        # Rule 5: Rate limit chatty sources
        self.rules.append(FilterRule(
            name="chatty_source_rate_limit",
            description="Rate limit sources generating too many alerts",
            conditions={
                'max_alerts_per_hour': 20,
                'time_window_seconds': 3600
            },
            action=FilterAction.SUPPRESS,
            priority=50
        ))
    
    def setup_default_patterns(self):
        """Setup default alert patterns"""
        
        self.patterns.append(AlertPattern(
            pattern_id="disk_space_pattern",
            title_pattern=r"disk.*space.*(?:warning|critical|full)",
            source_pattern=r".*monitor.*",
            time_window_seconds=1800,
            max_occurrences=3,
            severity_threshold=AlertSeverity.MEDIUM,
            description="Disk space alerts that may indicate trending issue"
        ))
        
        self.patterns.append(AlertPattern(
            pattern_id="memory_leak_pattern", 
            title_pattern=r"memory.*(?:usage|leak|high)",
            source_pattern=r".*",
            time_window_seconds=3600,
            max_occurrences=5,
            severity_threshold=AlertSeverity.HIGH,
            description="Memory-related alerts indicating possible leak"
        ))
        
        self.patterns.append(AlertPattern(
            pattern_id="service_restart_pattern",
            title_pattern=r"service.*(?:restart|crash|down)",
            source_pattern=r".*",
            time_window_seconds=900,
            max_occurrences=3,
            severity_threshold=AlertSeverity.CRITICAL,
            description="Service restart alerts indicating instability"
        ))
    
    async def process_alert(self, raw_alert: RawAlert) -> Optional[ProcessedAlert]:
        """Process a single alert through the filtering system"""
        
        self.stats['total_processed'] += 1
        
        # Generate fingerprint
        raw_alert.fingerprint = self.fingerprinter.generate_fingerprint(raw_alert)
        
        logger.info(f"Processing alert {raw_alert.id}: {raw_alert.title}")
        
        # Apply filtering rules
        for rule in sorted(self.rules, key=lambda r: r.priority):
            if not rule.enabled:
                continue
            
            action, reason = await self._apply_rule(rule, raw_alert)
            
            if action == FilterAction.SUPPRESS:
                logger.info(f"Alert {raw_alert.id} suppressed by rule '{rule.name}': {reason}")
                self.stats['suppressed'] += 1
                self.suppressed_alerts.append(raw_alert)
                rule.match_count += 1
                rule.last_triggered = datetime.now()
                return None
            
            elif action == FilterAction.AGGREGATE:
                # Find similar alerts to aggregate with
                similar_alerts = self._find_similar_alerts(raw_alert)
                if similar_alerts:
                    all_alerts = similar_alerts + [raw_alert]
                    aggregated = self.aggregator.aggregate_alerts(all_alerts)
                    aggregated.filter_reason = f"Aggregated by rule '{rule.name}': {reason}"
                    
                    logger.info(f"Alert {raw_alert.id} aggregated with {len(similar_alerts)} others")
                    self.stats['aggregated'] += 1
                    rule.match_count += 1
                    rule.last_triggered = datetime.now()
                    
                    # Remove similar alerts from recent alerts (they're now aggregated)
                    self._remove_from_recent(similar_alerts)
                    
                    return aggregated
            
            elif action == FilterAction.ESCALATE:
                # Create escalated alert
                escalated = ProcessedAlert(
                    id=raw_alert.id,
                    original_alerts=[raw_alert.id],
                    title=f"[ESCALATED] {raw_alert.title}",
                    description=f"ESCALATED ALERT: {reason}\n\n{raw_alert.description}",
                    severity=AlertSeverity.CRITICAL,  # Always escalate to critical
                    source=raw_alert.source,
                    timestamp=raw_alert.timestamp,
                    status=AlertStatus.ESCALATED,
                    tags=raw_alert.tags + ['escalated'],
                    metadata={**raw_alert.metadata, 'escalation_reason': reason},
                    filter_reason=f"Escalated by rule '{rule.name}': {reason}"
                )
                
                logger.info(f"Alert {raw_alert.id} escalated by rule '{rule.name}': {reason}")
                self.stats['escalated'] += 1
                rule.match_count += 1
                rule.last_triggered = datetime.now()
                
                return escalated
        
        # No filtering rules applied - allow alert through
        processed = ProcessedAlert(
            id=raw_alert.id,
            original_alerts=[raw_alert.id],
            title=raw_alert.title,
            description=raw_alert.description,
            severity=raw_alert.severity,
            source=raw_alert.source,
            timestamp=raw_alert.timestamp,
            status=AlertStatus.SENT,
            tags=raw_alert.tags,
            metadata=raw_alert.metadata,
            filter_reason="Passed all filters"
        )
        
        # Add to recent alerts for correlation
        self.recent_alerts.append(raw_alert)
        self._cleanup_old_alerts()
        
        self.stats['sent'] += 1
        logger.info(f"Alert {raw_alert.id} passed filtering and will be sent")
        
        return processed
    
    async def _apply_rule(self, rule: FilterRule, alert: RawAlert) -> Tuple[FilterAction, str]:
        """Apply a filtering rule to an alert"""
        
        conditions = rule.conditions
        
        if rule.name == "duplicate_suppression":
            # Check for recent duplicate alerts
            duplicate_window = conditions.get('duplicate_window_seconds', 300)
            cutoff_time = alert.timestamp - timedelta(seconds=duplicate_window)
            
            recent_similar = [
                a for a in self.recent_alerts
                if a.timestamp > cutoff_time and a.fingerprint == alert.fingerprint
            ]
            
            if len(recent_similar) >= conditions.get('max_duplicates', 1):
                return FilterAction.SUPPRESS, f"Duplicate alert within {duplicate_window} seconds"
        
        elif rule.name == "similar_aggregation":
            # Check for similar alerts to aggregate
            window_seconds = conditions.get('aggregation_window_seconds', 600)
            min_count = conditions.get('min_aggregation_count', 3)
            
            similar_alerts = self._find_similar_alerts(alert, window_seconds)
            if len(similar_alerts) >= min_count - 1:  # -1 because current alert not counted
                return FilterAction.AGGREGATE, f"Found {len(similar_alerts)} similar alerts"
        
        elif rule.name == "persistent_escalation":
            # Check for persistent alerts
            min_severity = AlertSeverity(conditions.get('min_severity', 'high'))
            persistence_window = conditions.get('persistence_window_seconds', 1800)
            min_occurrences = conditions.get('min_occurrences', 5)
            
            if alert.severity.value in ['critical', 'high'] or alert.severity == min_severity:
                cutoff_time = alert.timestamp - timedelta(seconds=persistence_window)
                similar_recent = [
                    a for a in self.recent_alerts
                    if a.timestamp > cutoff_time and 
                       self.fingerprinter.are_similar(a, alert, 0.7)
                ]
                
                if len(similar_recent) >= min_occurrences:
                    return FilterAction.ESCALATE, f"Persistent alert: {len(similar_recent)} occurrences in {persistence_window/60} minutes"
        
        elif rule.name == "test_environment_suppression":
            # Check for test environment alerts
            source_patterns = conditions.get('source_patterns', [])
            max_severity = AlertSeverity(conditions.get('max_severity', 'low'))
            
            if alert.severity == max_severity or alert.severity == AlertSeverity.INFO:
                for pattern in source_patterns:
                    if pattern in alert.source.lower():
                        return FilterAction.SUPPRESS, f"Test environment alert from {alert.source}"
        
        elif rule.name == "chatty_source_rate_limit":
            # Check rate limiting for chatty sources
            max_per_hour = conditions.get('max_alerts_per_hour', 20)
            time_window = conditions.get('time_window_seconds', 3600)
            
            cutoff_time = alert.timestamp - timedelta(seconds=time_window)
            source_alerts = [
                a for a in self.recent_alerts
                if a.timestamp > cutoff_time and a.source == alert.source
            ]
            
            if len(source_alerts) >= max_per_hour:
                return FilterAction.SUPPRESS, f"Rate limit exceeded: {len(source_alerts)} alerts from {alert.source} in last hour"
        
        return FilterAction.ALLOW, "No conditions matched"
    
    def _find_similar_alerts(self, alert: RawAlert, window_seconds: int = 600) -> List[RawAlert]:
        """Find similar alerts within time window"""
        cutoff_time = alert.timestamp - timedelta(seconds=window_seconds)
        
        similar = []
        for recent_alert in self.recent_alerts:
            if recent_alert.timestamp > cutoff_time:
                if self.fingerprinter.are_similar(recent_alert, alert):
                    similar.append(recent_alert)
        
        return similar
    
    def _remove_from_recent(self, alerts_to_remove: List[RawAlert]):
        """Remove alerts from recent alerts list"""
        remove_ids = {a.id for a in alerts_to_remove}
        self.recent_alerts = [a for a in self.recent_alerts if a.id not in remove_ids]
    
    def _cleanup_old_alerts(self, max_age_hours: int = 24):
        """Remove old alerts from recent alerts cache"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        self.recent_alerts = [a for a in self.recent_alerts if a.timestamp > cutoff_time]
    
    def get_filter_stats(self) -> Dict:
        """Get filtering statistics"""
        total = self.stats['total_processed']
        if total == 0:
            return self.stats
        
        stats = dict(self.stats)
        stats.update({
            'suppression_rate': (self.stats['suppressed'] / total) * 100,
            'aggregation_rate': (self.stats['aggregated'] / total) * 100,
            'escalation_rate': (self.stats['escalated'] / total) * 100,
            'pass_through_rate': (self.stats['sent'] / total) * 100,
            'active_rules': len([r for r in self.rules if r.enabled]),
            'rule_effectiveness': {
                rule.name: {
                    'matches': rule.match_count,
                    'last_triggered': rule.last_triggered.isoformat() if rule.last_triggered else None
                }
                for rule in self.rules
            },
            'recent_alerts_count': len(self.recent_alerts),
            'suppressed_alerts_count': len(self.suppressed_alerts)
        })
        
        return stats
    
    def add_rule(self, rule: FilterRule):
        """Add custom filtering rule"""
        self.rules.append(rule)
        logger.info(f"Added filtering rule: {rule.name}")
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove filtering rule by name"""
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                logger.info(f"Removed filtering rule: {rule_name}")
                return True
        return False
    
    def enable_rule(self, rule_name: str) -> bool:
        """Enable filtering rule"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                logger.info(f"Enabled filtering rule: {rule_name}")
                return True
        return False
    
    def disable_rule(self, rule_name: str) -> bool:
        """Disable filtering rule"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"Disabled filtering rule: {rule_name}")
                return True
        return False

async def demonstrate_smart_filtering():
    """Demonstrate the smart alert filtering system"""
    print("AIOps Smart Alert Filtering System Demo")
    print("=" * 55)
    
    # Initialize filter
    alert_filter = AlertFilter()
    
    # Create test alerts
    test_alerts = [
        # Duplicate alerts (should be suppressed)
        RawAlert("ALERT-001", "High CPU Usage", "CPU usage at 85%", AlertSeverity.HIGH, "server-01", datetime.now()),
        RawAlert("ALERT-002", "High CPU Usage", "CPU usage at 87%", AlertSeverity.HIGH, "server-01", datetime.now()),
        RawAlert("ALERT-003", "High CPU Usage", "CPU usage at 89%", AlertSeverity.HIGH, "server-01", datetime.now()),
        
        # Similar alerts (should be aggregated)
        RawAlert("ALERT-004", "Memory Warning", "Memory usage at 80%", AlertSeverity.MEDIUM, "app-server-01", datetime.now()),
        RawAlert("ALERT-005", "Memory Warning", "Memory usage at 82%", AlertSeverity.MEDIUM, "app-server-02", datetime.now()),
        RawAlert("ALERT-006", "Memory Alert", "Memory usage at 85%", AlertSeverity.MEDIUM, "app-server-03", datetime.now()),
        RawAlert("ALERT-007", "Memory Critical", "Memory usage at 90%", AlertSeverity.HIGH, "app-server-04", datetime.now()),
        
        # Test environment alerts (should be suppressed)
        RawAlert("ALERT-008", "Service Down", "Test service unavailable", AlertSeverity.LOW, "test-api-gateway", datetime.now()),
        RawAlert("ALERT-009", "Database Error", "Connection timeout", AlertSeverity.LOW, "dev-database", datetime.now()),
        
        # Normal alerts (should pass through)
        RawAlert("ALERT-010", "Disk Space Warning", "Disk usage at 75%", AlertSeverity.MEDIUM, "storage-server", datetime.now()),
        RawAlert("ALERT-011", "Network Latency", "High latency detected", AlertSeverity.HIGH, "network-monitor", datetime.now()),
        
        # Critical alert (should pass through and potentially escalate)
        RawAlert("ALERT-012", "Database Down", "Primary database unreachable", AlertSeverity.CRITICAL, "db-monitor", datetime.now()),
    ]
    
    print(f"\n📥 Processing {len(test_alerts)} test alerts...\n")
    
    processed_alerts = []
    
    for i, alert in enumerate(test_alerts, 1):
        print(f"Processing Alert {i}: {alert.title} ({alert.severity.value})")
        
        # Add small delay to simulate time passing
        if i > 1:
            await asyncio.sleep(0.1)
            # Update timestamp to simulate time progression
            alert.timestamp = datetime.now()
        
        result = await alert_filter.process_alert(alert)
        
        if result:
            processed_alerts.append(result)
            status_color = "✅" if result.status == AlertStatus.SENT else "🔄" if result.status == AlertStatus.AGGREGATED else "⬆️"
            print(f"  {status_color} {result.status.value.title()}: {result.title}")
            if result.filter_reason:
                print(f"    Reason: {result.filter_reason}")
            if result.aggregation_count > 1:
                print(f"    Aggregated {result.aggregation_count} alerts")
        else:
            print(f"  ❌ Suppressed")
        
        print()
    
    # Show filtering results
    print(f"📊 Filtering Results:")
    print(f"  Original Alerts: {len(test_alerts)}")
    print(f"  Processed Alerts: {len(processed_alerts)}")
    print(f"  Reduction Rate: {((len(test_alerts) - len(processed_alerts)) / len(test_alerts) * 100):.1f}%")
    
    # Show processed alerts summary
    print(f"\n📋 Processed Alerts Summary:")
    for alert in processed_alerts:
        status_icon = {"sent": "📤", "aggregated": "📦", "escalated": "⚠️"}.get(alert.status.value, "❓")
        print(f"  {status_icon} {alert.id}: {alert.title} ({alert.severity.value})")
        if alert.aggregation_count > 1:
            print(f"      └─ Aggregated {alert.aggregation_count} alerts")
    
    # Show filtering statistics
    print(f"\n📈 Filtering Statistics:")
    stats = alert_filter.get_filter_stats()
    for key, value in stats.items():
        if key == 'rule_effectiveness':
            print(f"  Rule Effectiveness:")
            for rule_name, rule_stats in value.items():
                print(f"    {rule_name}: {rule_stats['matches']} matches")
        elif isinstance(value, float):
            print(f"  {key.replace('_', ' ').title()}: {value:.1f}%")
        elif key not in ['rule_effectiveness']:
            print(f"  {key.replace('_', ' ').title()}: {value}")
    
    # Demonstrate rule management
    print(f"\n⚙️ Rule Management Demo:")
    print(f"  Active Rules: {len([r for r in alert_filter.rules if r.enabled])}")
    
    # Disable a rule
    alert_filter.disable_rule("test_environment_suppression")
    print(f"  Disabled 'test_environment_suppression' rule")
    print(f"  Active Rules: {len([r for r in alert_filter.rules if r.enabled])}")
    
    # Re-enable the rule
    alert_filter.enable_rule("test_environment_suppression")
    print(f"  Re-enabled 'test_environment_suppression' rule")
    print(f"  Active Rules: {len([r for r in alert_filter.rules if r.enabled])}")
    
    # Add a custom rule
    custom_rule = FilterRule(
        name="weekend_suppression",
        description="Suppress non-critical alerts on weekends",
        conditions={
            'days': ['saturday', 'sunday'],
            'max_severity': 'medium'
        },
        action=FilterAction.SUPPRESS,
        priority=25
    )
    alert_filter.add_rule(custom_rule)
    print(f"  Added custom rule: 'weekend_suppression'")
    print(f"  Total Rules: {len(alert_filter.rules)}")
    
    print(f"\n✅ Smart alert filtering demonstration completed!")
    print(f"🎯 Key Benefits:")
    print(f"  • Reduced alert noise by {((len(test_alerts) - len(processed_alerts)) / len(test_alerts) * 100):.1f}%")
    print(f"  • Intelligent aggregation of related alerts")
    print(f"  • Automatic suppression of duplicates and low-priority alerts")
    print(f"  • Flexible rule-based filtering system")
    print(f"  • Real-time processing and correlation")

if __name__ == "__main__":
    asyncio.run(demonstrate_smart_filtering())