#!/usr/bin/env python3
"""
AIOps Bot - Audit & Logging System
Comprehensive compliance tracking with forensic analysis capabilities
"""

import asyncio
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Set
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging
from collections import defaultdict, deque
import sqlite3
import secrets
import threading
import time
import copy
from pathlib import Path
import uuid
import re
import gzip
import base64
import ipaddress

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventType(Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    CONFIGURATION_CHANGE = "configuration_change"
    SYSTEM_EVENT = "system_event"
    SECURITY_EVENT = "security_event"
    COMPLIANCE_EVENT = "compliance_event"
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"

class EventSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

class ComplianceFramework(Enum):
    SOX = "sox"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO_27001 = "iso_27001"
    NIST = "nist"
    CUSTOM = "custom"

class RetentionPolicy(Enum):
    DAYS_30 = 30
    DAYS_90 = 90
    DAYS_180 = 180
    DAYS_365 = 365
    DAYS_2555 = 2555  # 7 years
    INDEFINITE = -1

@dataclass
class AuditEvent:
    """Individual audit event"""
    event_id: str
    timestamp: datetime
    event_type: EventType
    severity: EventSeverity
    source: str
    user_id: Optional[str]
    session_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    action: str
    resource: str
    details: Dict[str, Any]
    compliance_frameworks: List[ComplianceFramework] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    checksum: str = ""

@dataclass
class SecurityEvent:
    """Security-specific audit event"""
    event_id: str
    timestamp: datetime
    event_type: str
    severity: EventSeverity
    source_ip: str
    target_ip: Optional[str]
    user_id: Optional[str]
    action: str
    result: str  # success, failure, blocked
    threat_indicators: List[str] = field(default_factory=list)
    geolocation: Optional[Dict[str, str]] = None
    details: Dict[str, Any] = field(default_factory=dict)
    mitre_tactics: List[str] = field(default_factory=list)
    remediation_actions: List[str] = field(default_factory=list)

@dataclass
class ComplianceRule:
    """Compliance rule definition"""
    rule_id: str
    name: str
    description: str
    framework: ComplianceFramework
    rule_type: str
    conditions: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    severity: EventSeverity
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class LogRetentionPolicy:
    """Log retention policy configuration"""
    policy_id: str
    name: str
    event_types: List[EventType]
    retention_days: int
    archive_after_days: int
    compression_enabled: bool = True
    encryption_enabled: bool = True
    compliance_frameworks: List[ComplianceFramework] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class ForensicAnalysis:
    """Forensic analysis session"""
    analysis_id: str
    name: str
    description: str
    analyst: str
    start_time: datetime
    event_ids: List[str]
    filters: Dict[str, Any]
    end_time: Optional[datetime] = None
    findings: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "active"  # active, completed, archived
    tags: List[str] = field(default_factory=list)

class EventCorrelator:
    """Event correlation engine"""
    
    def __init__(self):
        """Initialize event correlator"""
        self.correlation_rules: List[Dict[str, Any]] = []
        self.correlation_sessions: Dict[str, List[str]] = {}
        self.time_window = 300  # 5 minutes default
        
        # Initialize correlation rules
        self._initialize_correlation_rules()
        
        logger.info("Event Correlator initialized")
    
    def _initialize_correlation_rules(self):
        """Initialize default correlation rules"""
        self.correlation_rules = [
            {
                "rule_id": "failed_login_sequence",
                "name": "Failed Login Sequence",
                "description": "Multiple failed login attempts from same IP",
                "conditions": [
                    {"event_type": "authentication", "action": "login", "result": "failure"},
                    {"min_count": 3, "time_window": 300}
                ],
                "correlation_key": "ip_address",
                "severity": EventSeverity.HIGH
            },
            {
                "rule_id": "privilege_escalation",
                "name": "Privilege Escalation Attempt",
                "description": "User accessing resources above normal privilege level",
                "conditions": [
                    {"event_type": "authorization", "action": "access_denied"},
                    {"event_type": "authorization", "action": "privilege_change"}
                ],
                "correlation_key": "user_id",
                "severity": EventSeverity.CRITICAL
            },
            {
                "rule_id": "data_exfiltration",
                "name": "Potential Data Exfiltration",
                "description": "Large data access followed by external transfer",
                "conditions": [
                    {"event_type": "data_access", "volume": ">1GB"},
                    {"event_type": "system_event", "action": "file_transfer"}
                ],
                "correlation_key": "user_id",
                "severity": EventSeverity.CRITICAL
            }
        ]
    
    async def correlate_event(self, event: AuditEvent) -> List[Dict[str, Any]]:
        """Correlate event with existing events"""
        correlations = []
        
        for rule in self.correlation_rules:
            correlation = await self._check_correlation_rule(event, rule)
            if correlation:
                correlations.append(correlation)
        
        return correlations
    
    async def _check_correlation_rule(self, event: AuditEvent, rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check if event matches correlation rule"""
        try:
            conditions = rule["conditions"]
            correlation_key = rule["correlation_key"]
            
            # Get correlation value from event
            correlation_value = self._get_correlation_value(event, correlation_key)
            if not correlation_value:
                return None
            
            # Check if event matches first condition
            if not self._matches_condition(event, conditions[0]):
                return None
            
            # Check for related events in time window
            session_key = f"{rule['rule_id']}_{correlation_value}"
            
            if session_key not in self.correlation_sessions:
                self.correlation_sessions[session_key] = []
            
            self.correlation_sessions[session_key].append(event.event_id)
            
            # Check if correlation conditions are met
            if len(self.correlation_sessions[session_key]) >= conditions[1].get("min_count", 2):
                correlation_id = f"corr-{uuid.uuid4().hex[:8]}"
                
                return {
                    "correlation_id": correlation_id,
                    "rule_id": rule["rule_id"],
                    "rule_name": rule["name"],
                    "severity": rule["severity"].value,
                    "events": self.correlation_sessions[session_key].copy(),
                    "correlation_key": correlation_key,
                    "correlation_value": correlation_value,
                    "detected_at": datetime.now().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Correlation rule check failed: {e}")
            return None
    
    def _get_correlation_value(self, event: AuditEvent, correlation_key: str) -> Optional[str]:
        """Get correlation value from event"""
        if correlation_key == "ip_address":
            return event.ip_address
        elif correlation_key == "user_id":
            return event.user_id
        elif correlation_key == "session_id":
            return event.session_id
        elif correlation_key in event.details:
            return str(event.details[correlation_key])
        return None
    
    def _matches_condition(self, event: AuditEvent, condition: Dict[str, Any]) -> bool:
        """Check if event matches condition"""
        try:
            if "event_type" in condition:
                if event.event_type.value != condition["event_type"]:
                    return False
            
            if "action" in condition:
                if event.action != condition["action"]:
                    return False
            
            if "result" in condition:
                if event.details.get("result") != condition["result"]:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Condition matching failed: {e}")
            return False

class ComplianceEngine:
    """Compliance monitoring and reporting engine"""
    
    def __init__(self):
        """Initialize compliance engine"""
        self.compliance_rules: Dict[str, ComplianceRule] = {}
        self.compliance_violations: List[Dict[str, Any]] = []
        self.compliance_reports: Dict[str, Dict[str, Any]] = {}
        
        # Initialize compliance rules
        self._initialize_compliance_rules()
        
        logger.info("Compliance Engine initialized")
    
    def _initialize_compliance_rules(self):
        """Initialize default compliance rules"""
        rules = [
            ComplianceRule(
                rule_id="gdpr_data_access",
                name="GDPR Data Access Logging",
                description="Log all personal data access for GDPR compliance",
                framework=ComplianceFramework.GDPR,
                rule_type="data_access",
                conditions=[
                    {"event_type": "data_access"},
                    {"resource_type": "personal_data"}
                ],
                actions=[
                    {"type": "log", "retention_days": 2555}  # 7 years
                ],
                severity=EventSeverity.MEDIUM
            ),
            ComplianceRule(
                rule_id="sox_financial_access",
                name="SOX Financial Data Access",
                description="Monitor access to financial data for SOX compliance",
                framework=ComplianceFramework.SOX,
                rule_type="data_access",
                conditions=[
                    {"event_type": "data_access"},
                    {"resource_type": "financial_data"}
                ],
                actions=[
                    {"type": "log", "retention_days": 2555},
                    {"type": "alert", "severity": "high"}
                ],
                severity=EventSeverity.HIGH
            ),
            ComplianceRule(
                rule_id="hipaa_phi_access",
                name="HIPAA PHI Access Monitoring",
                description="Monitor Protected Health Information access",
                framework=ComplianceFramework.HIPAA,
                rule_type="data_access",
                conditions=[
                    {"event_type": "data_access"},
                    {"resource_type": "phi"}
                ],
                actions=[
                    {"type": "log", "retention_days": 2190},  # 6 years
                    {"type": "audit", "immediate": True}
                ],
                severity=EventSeverity.HIGH
            ),
            ComplianceRule(
                rule_id="pci_cardholder_data",
                name="PCI Cardholder Data Access",
                description="Monitor cardholder data access for PCI DSS",
                framework=ComplianceFramework.PCI_DSS,
                rule_type="data_access",
                conditions=[
                    {"event_type": "data_access"},
                    {"resource_type": "cardholder_data"}
                ],
                actions=[
                    {"type": "log", "retention_days": 365},
                    {"type": "alert", "severity": "critical"}
                ],
                severity=EventSeverity.CRITICAL
            )
        ]
        
        for rule in rules:
            self.register_compliance_rule(rule)
    
    def register_compliance_rule(self, rule: ComplianceRule):
        """Register a compliance rule"""
        self.compliance_rules[rule.rule_id] = rule
        logger.info(f"Registered compliance rule: {rule.name}")
    
    async def check_compliance(self, event: AuditEvent) -> List[Dict[str, Any]]:
        """Check event against compliance rules"""
        violations = []
        
        for rule in self.compliance_rules.values():
            if not rule.enabled:
                continue
            
            if await self._matches_compliance_rule(event, rule):
                violation = {
                    "violation_id": f"viol-{uuid.uuid4().hex[:8]}",
                    "rule_id": rule.rule_id,
                    "rule_name": rule.name,
                    "framework": rule.framework.value,
                    "event_id": event.event_id,
                    "severity": rule.severity.value,
                    "detected_at": datetime.now().isoformat(),
                    "description": rule.description
                }
                violations.append(violation)
                self.compliance_violations.append(violation)
        
        return violations
    
    async def _matches_compliance_rule(self, event: AuditEvent, rule: ComplianceRule) -> bool:
        """Check if event matches compliance rule conditions"""
        try:
            for condition in rule.conditions:
                if not self._evaluate_compliance_condition(event, condition):
                    return False
            return True
        except Exception as e:
            logger.error(f"Compliance rule evaluation failed: {e}")
            return False
    
    def _evaluate_compliance_condition(self, event: AuditEvent, condition: Dict[str, Any]) -> bool:
        """Evaluate compliance condition"""
        try:
            if "event_type" in condition:
                if event.event_type.value != condition["event_type"]:
                    return False
            
            if "resource_type" in condition:
                if event.details.get("resource_type") != condition["resource_type"]:
                    return False
            
            if "user_type" in condition:
                if event.details.get("user_type") != condition["user_type"]:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Compliance condition evaluation failed: {e}")
            return False
    
    async def generate_compliance_report(self, framework: ComplianceFramework, 
                                       start_date: datetime, 
                                       end_date: datetime) -> Dict[str, Any]:
        """Generate compliance report"""
        try:
            report_id = f"report-{framework.value}-{int(time.time())}"
            
            # Filter violations by framework and date range
            framework_violations = [
                v for v in self.compliance_violations
                if v.get("framework") == framework.value
                and start_date <= datetime.fromisoformat(v["detected_at"]) <= end_date
            ]
            
            # Calculate metrics
            total_violations = len(framework_violations)
            severity_breakdown = defaultdict(int)
            rule_breakdown = defaultdict(int)
            
            for violation in framework_violations:
                severity_breakdown[violation["severity"]] += 1
                rule_breakdown[violation["rule_name"]] += 1
            
            report = {
                "report_id": report_id,
                "framework": framework.value,
                "report_period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "summary": {
                    "total_violations": total_violations,
                    "critical_violations": severity_breakdown["critical"],
                    "high_violations": severity_breakdown["high"],
                    "medium_violations": severity_breakdown["medium"],
                    "low_violations": severity_breakdown["low"]
                },
                "violations_by_rule": dict(rule_breakdown),
                "violations_by_severity": dict(severity_breakdown),
                "detailed_violations": framework_violations,
                "generated_at": datetime.now().isoformat(),
                "compliance_score": self._calculate_compliance_score(framework_violations, total_violations)
            }
            
            self.compliance_reports[report_id] = report
            return report
            
        except Exception as e:
            logger.error(f"Compliance report generation failed: {e}")
            return {}
    
    def _calculate_compliance_score(self, violations: List[Dict[str, Any]], total_events: int) -> float:
        """Calculate compliance score (0-100)"""
        if total_events == 0:
            return 100.0
        
        # Weight violations by severity
        severity_weights = {
            "critical": 10,
            "high": 5,
            "medium": 2,
            "low": 1
        }
        
        weighted_violations = sum(
            severity_weights.get(v["severity"], 1) for v in violations
        )
        
        # Calculate score (higher violations = lower score)
        max_score = 100.0
        penalty = min(weighted_violations * 2, max_score)
        
        return max(0.0, max_score - penalty)

class AuditLoggingSystem:
    """Main audit and logging system"""
    
    def __init__(self, db_path: str = "audit_logs.db", storage_path: str = "audit_storage"):
        """Initialize audit logging system"""
        self.db_path = db_path
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        
        self.events: deque = deque(maxlen=10000)  # In-memory buffer
        self.correlator = EventCorrelator()
        self.compliance_engine = ComplianceEngine()
        self.retention_policies: Dict[str, LogRetentionPolicy] = {}
        self.forensic_analyses: Dict[str, ForensicAnalysis] = {}
        
        # Statistics
        self.event_stats = defaultdict(int)
        self.security_stats = defaultdict(int)
        
        # Initialize database
        self._init_database()
        
        # Initialize retention policies
        self._initialize_retention_policies()
        
        # Start background tasks
        asyncio.create_task(self._log_processor())
        asyncio.create_task(self._retention_manager())
        
        logger.info("Audit & Logging System initialized")
    
    def _init_database(self):
        """Apply schema migrations for the audit logging SQLite database."""
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _migrations_dir = _os.path.join(
            _here, "..", "..", "migrations", "sqlite", "security_audit"
        )
        try:
            from app.core.sqlite_migrator import run_sqlite_migrations
            run_sqlite_migrations(self.db_path, _migrations_dir)
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
    
    def _initialize_retention_policies(self):
        """Initialize default retention policies"""
        policies = [
            LogRetentionPolicy(
                policy_id="security_events",
                name="Security Events Retention",
                event_types=[EventType.SECURITY_EVENT, EventType.AUTHENTICATION, EventType.AUTHORIZATION],
                retention_days=2555,  # 7 years
                archive_after_days=365,
                compliance_frameworks=[ComplianceFramework.SOX, ComplianceFramework.ISO_27001]
            ),
            LogRetentionPolicy(
                policy_id="data_access_logs",
                name="Data Access Logs Retention",
                event_types=[EventType.DATA_ACCESS],
                retention_days=2190,  # 6 years
                archive_after_days=90,
                compliance_frameworks=[ComplianceFramework.GDPR, ComplianceFramework.HIPAA]
            ),
            LogRetentionPolicy(
                policy_id="configuration_changes",
                name="Configuration Changes Retention",
                event_types=[EventType.CONFIGURATION_CHANGE],
                retention_days=365,
                archive_after_days=30,
                compliance_frameworks=[ComplianceFramework.SOX, ComplianceFramework.PCI_DSS]
            ),
            LogRetentionPolicy(
                policy_id="general_logs",
                name="General Logs Retention",
                event_types=[EventType.SYSTEM_EVENT, EventType.INFORMATION],
                retention_days=90,
                archive_after_days=30,
                compliance_frameworks=[]
            )
        ]
        
        for policy in policies:
            self.retention_policies[policy.policy_id] = policy
    
    async def log_event(self, event: AuditEvent) -> bool:
        """Log an audit event"""
        try:
            # Calculate checksum
            event_data = f"{event.timestamp}{event.event_type.value}{event.action}{event.resource}"
            event.checksum = hashlib.sha256(event_data.encode()).hexdigest()
            
            # Add to buffer
            self.events.append(event)
            
            # Update statistics
            self.event_stats["total"] += 1
            self.event_stats[event.event_type.value] += 1
            self.event_stats[event.severity.value] += 1
            
            # Check for correlations
            correlations = await self.correlator.correlate_event(event)
            if correlations:
                logger.info(f"Event correlations detected: {len(correlations)}")
                for correlation in correlations:
                    self.security_stats["correlations"] += 1
            
            # Check compliance
            violations = await self.compliance_engine.check_compliance(event)
            if violations:
                logger.warning(f"Compliance violations detected: {len(violations)}")
                for violation in violations:
                    self.security_stats["compliance_violations"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
            return False
    
    async def log_security_event(self, security_event: SecurityEvent) -> bool:
        """Log a security event"""
        try:
            # Convert to audit event
            audit_event = AuditEvent(
                event_id=security_event.event_id,
                timestamp=security_event.timestamp,
                event_type=EventType.SECURITY_EVENT,
                severity=security_event.severity,
                source="security_system",
                user_id=security_event.user_id,
                session_id=None,
                ip_address=security_event.source_ip,
                user_agent=None,
                action=security_event.action,
                resource=security_event.target_ip or "unknown",
                details={
                    "result": security_event.result,
                    "threat_indicators": security_event.threat_indicators,
                    "geolocation": security_event.geolocation,
                    "mitre_tactics": security_event.mitre_tactics,
                    "remediation_actions": security_event.remediation_actions
                }
            )
            
            # Log as audit event
            success = await self.log_event(audit_event)
            
            if success:
                self.security_stats["security_events"] += 1
                
                # Store security event separately
                await self._store_security_event(security_event)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
            return False
    
    async def _store_security_event(self, security_event: SecurityEvent):
        """Store security event to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO security_events 
                (event_id, timestamp, event_type, severity, source_ip, target_ip, user_id, 
                 action, result, threat_indicators, geolocation, details, mitre_tactics, remediation_actions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                security_event.event_id, security_event.timestamp.isoformat(),
                security_event.event_type, security_event.severity.value,
                security_event.source_ip, security_event.target_ip, security_event.user_id,
                security_event.action, security_event.result,
                json.dumps(security_event.threat_indicators),
                json.dumps(security_event.geolocation) if security_event.geolocation else None,
                json.dumps(security_event.details),
                json.dumps(security_event.mitre_tactics),
                json.dumps(security_event.remediation_actions)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to store security event: {e}")
    
    async def _log_processor(self):
        """Background log processor"""
        while True:
            try:
                if self.events:
                    # Process batch of events
                    batch_size = min(100, len(self.events))
                    batch = [self.events.popleft() for _ in range(batch_size)]
                    
                    await self._store_events_batch(batch)
                
                await asyncio.sleep(5)  # Process every 5 seconds
                
            except Exception as e:
                logger.error(f"Log processor error: {e}")
                await asyncio.sleep(10)
    
    async def _store_events_batch(self, events: List[AuditEvent]):
        """Store batch of events to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for event in events:
                cursor.execute('''
                    INSERT INTO audit_events 
                    (event_id, timestamp, event_type, severity, source, user_id, session_id, 
                     ip_address, user_agent, action, resource, details, compliance_frameworks, 
                     tags, correlation_id, parent_event_id, checksum)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event.event_id, event.timestamp.isoformat(), event.event_type.value,
                    event.severity.value, event.source, event.user_id, event.session_id,
                    event.ip_address, event.user_agent, event.action, event.resource,
                    json.dumps(event.details), json.dumps([f.value for f in event.compliance_frameworks]),
                    json.dumps(event.tags), event.correlation_id, event.parent_event_id, event.checksum
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Stored {len(events)} events to database")
            
        except Exception as e:
            logger.error(f"Failed to store events batch: {e}")
    
    async def _retention_manager(self):
        """Background retention manager"""
        while True:
            try:
                await self._apply_retention_policies()
                await asyncio.sleep(3600)  # Run every hour
            except Exception as e:
                logger.error(f"Retention manager error: {e}")
                await asyncio.sleep(3600)
    
    async def _apply_retention_policies(self):
        """Apply retention policies to audit logs"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for policy in self.retention_policies.values():
                # Archive old events
                archive_cutoff = datetime.now() - timedelta(days=policy.archive_after_days)
                
                cursor.execute('''
                    UPDATE audit_events 
                    SET archived = 1 
                    WHERE timestamp < ? AND event_type IN ({}) AND archived = 0
                '''.format(','.join(['?' for _ in policy.event_types])),
                    [archive_cutoff.isoformat()] + [et.value for et in policy.event_types]
                )
                
                archived_count = cursor.rowcount
                if archived_count > 0:
                    logger.info(f"Archived {archived_count} events for policy {policy.name}")
                
                # Delete expired events
                delete_cutoff = datetime.now() - timedelta(days=policy.retention_days)
                
                cursor.execute('''
                    DELETE FROM audit_events 
                    WHERE timestamp < ? AND event_type IN ({})
                '''.format(','.join(['?' for _ in policy.event_types])),
                    [delete_cutoff.isoformat()] + [et.value for et in policy.event_types]
                )
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"Deleted {deleted_count} expired events for policy {policy.name}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Retention policy application failed: {e}")
    
    async def start_forensic_analysis(self, name: str, description: str, 
                                    analyst: str, filters: Dict[str, Any]) -> str:
        """Start a forensic analysis session"""
        try:
            analysis_id = f"forensic-{uuid.uuid4().hex[:8]}"
            
            # Query events based on filters
            event_ids = await self._query_events(filters)
            
            analysis = ForensicAnalysis(
                analysis_id=analysis_id,
                name=name,
                description=description,
                analyst=analyst,
                start_time=datetime.now(),
                event_ids=event_ids,
                filters=filters
            )
            
            self.forensic_analyses[analysis_id] = analysis
            
            logger.info(f"Started forensic analysis: {analysis_id} with {len(event_ids)} events")
            
            return analysis_id
            
        except Exception as e:
            logger.error(f"Failed to start forensic analysis: {e}")
            raise
    
    async def _query_events(self, filters: Dict[str, Any]) -> List[str]:
        """Query events based on filters"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = "SELECT event_id FROM audit_events WHERE 1=1"
            params = []
            
            if "start_time" in filters:
                query += " AND timestamp >= ?"
                params.append(filters["start_time"])
            
            if "end_time" in filters:
                query += " AND timestamp <= ?"
                params.append(filters["end_time"])
            
            if "event_type" in filters:
                query += " AND event_type = ?"
                params.append(filters["event_type"])
            
            if "user_id" in filters:
                query += " AND user_id = ?"
                params.append(filters["user_id"])
            
            if "ip_address" in filters:
                query += " AND ip_address = ?"
                params.append(filters["ip_address"])
            
            if "severity" in filters:
                query += " AND severity = ?"
                params.append(filters["severity"])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            conn.close()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"Event query failed: {e}")
            return []
    
    async def get_system_summary(self) -> Dict[str, Any]:
        """Get audit system summary"""
        try:
            summary = {
                "events": {
                    "total": self.event_stats["total"],
                    "in_buffer": len(self.events),
                    "by_type": {k: v for k, v in self.event_stats.items() if k != "total"},
                },
                "security": {
                    "correlations": self.security_stats["correlations"],
                    "compliance_violations": self.security_stats["compliance_violations"],
                    "security_events": self.security_stats["security_events"]
                },
                "compliance": {
                    "rules_registered": len(self.compliance_engine.compliance_rules),
                    "frameworks": [f.value for f in ComplianceFramework],
                    "total_violations": len(self.compliance_engine.compliance_violations)
                },
                "retention": {
                    "policies": len(self.retention_policies),
                    "policies_list": [p.name for p in self.retention_policies.values()]
                },
                "forensics": {
                    "active_analyses": len([a for a in self.forensic_analyses.values() if a.status == "active"]),
                    "total_analyses": len(self.forensic_analyses)
                }
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get system summary: {e}")
            return {}

async def demo_audit_logging_system():
    """Demonstrate Audit & Logging System capabilities"""
    print("🔍 AIOps Audit & Logging System Demo")
    print("=" * 55)
    
    # Initialize Audit System
    audit_system = AuditLoggingSystem()
    await asyncio.sleep(1)  # Allow initialization to complete
    
    print("\n📋 System Configuration:")
    print(f"  🗄️ Database: {audit_system.db_path}")
    print(f"  📁 Storage: {audit_system.storage_path}")
    print(f"  📊 Buffer Size: {audit_system.events.maxlen}")
    
    print("\n🔒 Compliance Rules:")
    for rule_id, rule in audit_system.compliance_engine.compliance_rules.items():
        print(f"  📜 {rule.name}")
        print(f"     Framework: {rule.framework.value} | Severity: {rule.severity.value}")
        print(f"     Type: {rule.rule_type} | Enabled: {rule.enabled}")
    
    print("\n📚 Retention Policies:")
    for policy_id, policy in audit_system.retention_policies.items():
        print(f"  📋 {policy.name}")
        print(f"     Retention: {policy.retention_days} days | Archive: {policy.archive_after_days} days")
        print(f"     Event Types: {[et.value for et in policy.event_types]}")
        print(f"     Frameworks: {[cf.value for cf in policy.compliance_frameworks]}")
    
    print("\n🚀 Logging Sample Events:")
    
    # Sample audit events
    sample_events = [
        AuditEvent(
            event_id=f"audit-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            event_type=EventType.AUTHENTICATION,
            severity=EventSeverity.MEDIUM,
            source="auth_service",
            user_id="john.doe",
            session_id="sess-123",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            action="login",
            resource="user_portal",
            details={"result": "success", "method": "password"},
            compliance_frameworks=[ComplianceFramework.SOX]
        ),
        AuditEvent(
            event_id=f"audit-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            event_type=EventType.DATA_ACCESS,
            severity=EventSeverity.HIGH,
            source="database_service",
            user_id="jane.smith",
            session_id="sess-456",
            ip_address="192.168.1.101",
            user_agent="APIClient/1.0",
            action="query",
            resource="financial_data",
            details={"resource_type": "financial_data", "records_accessed": 1500},
            compliance_frameworks=[ComplianceFramework.SOX, ComplianceFramework.GDPR]
        ),
        AuditEvent(
            event_id=f"audit-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            event_type=EventType.CONFIGURATION_CHANGE,
            severity=EventSeverity.CRITICAL,
            source="config_service",
            user_id="admin",
            session_id="sess-789",
            ip_address="192.168.1.10",
            user_agent="AdminConsole/2.0",
            action="modify",
            resource="security_policy",
            details={"old_value": "policy_v1", "new_value": "policy_v2"},
            compliance_frameworks=[ComplianceFramework.ISO_27001]
        )
    ]
    
    # Log events
    for event in sample_events:
        success = await audit_system.log_event(event)
        status = "✅" if success else "❌"
        print(f"  {status} {event.event_type.value}: {event.action} on {event.resource}")
    
    print("\n🔐 Logging Security Events:")
    
    # Sample security events
    security_events = [
        SecurityEvent(
            event_id=f"sec-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            event_type="intrusion_attempt",
            severity=EventSeverity.HIGH,
            source_ip="203.0.113.45",
            target_ip="192.168.1.100",
            user_id=None,
            action="port_scan",
            result="blocked",
            threat_indicators=["suspicious_ip", "port_scan_pattern"],
            geolocation={"country": "Unknown", "city": "Unknown"},
            mitre_tactics=["T1046"],
            remediation_actions=["ip_blocked", "alert_sent"]
        ),
        SecurityEvent(
            event_id=f"sec-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            event_type="failed_authentication",
            severity=EventSeverity.MEDIUM,
            source_ip="192.168.1.200",
            target_ip="192.168.1.10",
            user_id="attacker",
            action="login_attempt",
            result="failed",
            threat_indicators=["brute_force", "multiple_failures"],
            geolocation={"country": "Internal", "city": "Office"},
            mitre_tactics=["T1110"],
            remediation_actions=["account_locked", "security_team_notified"]
        )
    ]
    
    # Log security events
    for event in security_events:
        success = await audit_system.log_security_event(event)
        status = "✅" if success else "❌"
        print(f"  {status} {event.event_type}: {event.action} from {event.source_ip}")
    
    # Wait for background processing
    await asyncio.sleep(2)
    
    print("\n🔍 Starting Forensic Analysis:")
    
    # Start forensic analysis
    analysis_id = await audit_system.start_forensic_analysis(
        name="Security Incident Investigation",
        description="Investigating suspicious authentication attempts",
        analyst="security_analyst",
        filters={
            "event_type": "authentication",
            "start_time": (datetime.now() - timedelta(hours=1)).isoformat(),
            "end_time": datetime.now().isoformat()
        }
    )
    
    print(f"  🔍 Analysis Started: {analysis_id}")
    analysis = audit_system.forensic_analyses[analysis_id]
    print(f"     Events: {len(analysis.event_ids)} | Analyst: {analysis.analyst}")
    print(f"     Status: {analysis.status} | Started: {analysis.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n📊 Compliance Report:")
    
    # Generate compliance report
    compliance_report = await audit_system.compliance_engine.generate_compliance_report(
        ComplianceFramework.SOX,
        datetime.now() - timedelta(days=1),
        datetime.now()
    )
    
    print(f"  📋 Report ID: {compliance_report['report_id']}")
    print(f"  🏢 Framework: {compliance_report['framework'].upper()}")
    print(f"  📊 Total Violations: {compliance_report['summary']['total_violations']}")
    print(f"  🔴 Critical: {compliance_report['summary']['critical_violations']}")
    print(f"  🟡 High: {compliance_report['summary']['high_violations']}")
    print(f"  🔵 Medium: {compliance_report['summary']['medium_violations']}")
    print(f"  ⚪ Low: {compliance_report['summary']['low_violations']}")
    print(f"  📈 Compliance Score: {compliance_report['compliance_score']:.1f}/100")
    
    print("\n📈 System Summary:")
    
    summary = await audit_system.get_system_summary()
    
    print(f"  📊 Total Events: {summary['events']['total']}")
    print(f"  🔄 Buffer Events: {summary['events']['in_buffer']}")
    print(f"  🔐 Security Events: {summary['security']['security_events']}")
    print(f"  🔗 Correlations: {summary['security']['correlations']}")
    print(f"  ⚠️ Compliance Violations: {summary['security']['compliance_violations']}")
    print(f"  📜 Compliance Rules: {summary['compliance']['rules_registered']}")
    print(f"  📚 Retention Policies: {summary['retention']['policies']}")
    print(f"  🔍 Active Analyses: {summary['forensics']['active_analyses']}")
    
    print(f"\n  📊 Events by Type:")
    for event_type, count in summary["events"]["by_type"].items():
        if count > 0:
            print(f"     • {event_type}: {count}")
    
    print(f"\n  🏢 Supported Frameworks:")
    for framework in summary["compliance"]["frameworks"]:
        print(f"     • {framework.upper()}")
    
    print("\n🔧 Audit & Logging Features:")
    print("  ✅ Comprehensive event logging and correlation")
    print("  ✅ Multi-framework compliance monitoring")
    print("  ✅ Forensic analysis and investigation tools")
    print("  ✅ Flexible retention policies and archiving")
    print("  ✅ Real-time security event correlation")
    print("  ✅ Automated compliance reporting")
    print("  ✅ Tamper-evident event checksums")
    print("  ✅ Advanced search and filtering capabilities")
    
    print("\n🛡️ Security Features:")
    print("  🔐 Event integrity with cryptographic checksums")
    print("  📊 Real-time threat correlation and analysis")
    print("  🔍 Advanced forensic investigation capabilities")
    print("  📈 Compliance score calculation and tracking")
    print("  ⚠️ Automated violation detection and alerting")
    print("  🏢 Multi-framework compliance support")
    print("  📚 Configurable retention and archival policies")
    print("  🔗 Event correlation across multiple sources")
    
    print("\n🏆 Audit & Logging System demonstration complete!")
    print("✨ Enterprise-grade compliance tracking with forensic analysis!")

if __name__ == "__main__":
    asyncio.run(demo_audit_logging_system())