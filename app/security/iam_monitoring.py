#!/usr/bin/env python3
"""
AIOps IAM & Access Control Monitoring System
Advanced identity and access management monitoring with privilege escalation detection and anomaly analysis

Features:
- Real-time access pattern monitoring and analysis
- Privilege escalation detection and alerting
- Identity lifecycle management and compliance
- Access anomaly detection using behavioral analysis
- Role-based access control (RBAC) monitoring
- Multi-factor authentication (MFA) tracking
- Privileged account monitoring and auditing
- Access request workflow automation
"""

import asyncio
import json
import logging
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, Counter
import uuid
import statistics
import sqlite3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('iam_monitoring')

class AccessType(Enum):
    """Types of access events"""
    LOGIN = "login"
    LOGOUT = "logout"
    FAILED_LOGIN = "failed_login"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    RESOURCE_ACCESS = "resource_access"
    PERMISSION_CHANGE = "permission_change"
    ACCOUNT_CREATION = "account_creation"
    ACCOUNT_DELETION = "account_deletion"
    PASSWORD_CHANGE = "password_change"
    MFA_ENROLLMENT = "mfa_enrollment"
    MFA_BYPASS = "mfa_bypass"
    ROLE_ASSIGNMENT = "role_assignment"
    ROLE_REMOVAL = "role_removal"

class RiskLevel(Enum):
    """Risk levels for access events"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

class AccountType(Enum):
    """Types of user accounts"""
    STANDARD_USER = "standard_user"
    PRIVILEGED_USER = "privileged_user"
    SERVICE_ACCOUNT = "service_account"
    ADMIN_ACCOUNT = "admin_account"
    GUEST_ACCOUNT = "guest_account"
    SYSTEM_ACCOUNT = "system_account"

class AccessStatus(Enum):
    """Access attempt status"""
    GRANTED = "granted"
    DENIED = "denied"
    PENDING = "pending"
    EXPIRED = "expired"
    SUSPENDED = "suspended"

class AuthenticationMethod(Enum):
    """Authentication methods"""
    PASSWORD = "password"
    MFA = "mfa"
    SSO = "sso"
    CERTIFICATE = "certificate"
    BIOMETRIC = "biometric"
    TOKEN = "token"
    API_KEY = "api_key"

@dataclass
class AccessEvent:
    """Access control event"""
    event_id: str
    timestamp: datetime
    user_id: str
    username: str
    access_type: AccessType
    resource: str
    source_ip: str
    user_agent: str
    authentication_method: AuthenticationMethod
    access_status: AccessStatus
    risk_level: RiskLevel
    session_id: Optional[str] = None
    geolocation: Optional[Dict[str, str]] = None
    device_info: Optional[Dict[str, str]] = None
    permissions_granted: List[str] = field(default_factory=list)
    additional_context: Dict[str, Any] = field(default_factory=dict)
    anomaly_score: float = 0.0
    is_suspicious: bool = False

@dataclass
class UserProfile:
    """User profile with behavioral patterns"""
    user_id: str
    username: str
    email: str
    account_type: AccountType
    creation_date: datetime
    last_login: Optional[datetime]
    login_count: int
    failed_login_count: int
    roles: List[str]
    permissions: List[str]
    typical_login_hours: List[int]  # Hours 0-23
    typical_locations: List[str]  # IP ranges or locations
    typical_devices: List[str]
    mfa_enabled: bool
    last_password_change: Optional[datetime]
    account_locked: bool = False
    is_active: bool = True
    risk_score: float = 0.0
    behavioral_baseline: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AccessRule:
    """Access control rule"""
    rule_id: str
    name: str
    description: str
    resource_pattern: str
    allowed_roles: List[str]
    allowed_permissions: List[str]
    time_restrictions: Optional[Dict[str, Any]] = None
    location_restrictions: Optional[List[str]] = None
    conditions: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    priority: int = 100

@dataclass
class PrivilegeEscalation:
    """Privilege escalation detection"""
    escalation_id: str
    user_id: str
    username: str
    from_permissions: List[str]
    to_permissions: List[str]
    escalation_type: str  # horizontal, vertical, abuse
    detection_timestamp: datetime
    risk_level: RiskLevel
    confidence_score: float
    context: Dict[str, Any]
    investigated: bool = False
    false_positive: bool = False

@dataclass
class AccessAnomaly:
    """Access anomaly detection result"""
    anomaly_id: str
    user_id: str
    username: str
    anomaly_type: str
    description: str
    detection_timestamp: datetime
    anomaly_score: float
    risk_level: RiskLevel
    baseline_deviation: Dict[str, float]
    contributing_factors: List[str]
    event_context: Dict[str, Any]
    requires_investigation: bool = True

class IAMDatabase:
    """IAM monitoring database interface"""
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info(f"IAM database initialized: {db_path}")
    
    def _create_tables(self):
        """Apply schema migrations for the IAM monitoring SQLite database."""
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _migrations_dir = _os.path.join(
            _here, "..", "..", "migrations", "sqlite", "security_iam"
        )
        if self.db_path == ":memory:":
            # In-memory DB: execute the SQL file directly on self.conn.
            _sql_file = _os.path.join(_migrations_dir, "001_initial.sql")
            with open(_sql_file, encoding="utf-8") as _f:
                self.conn.executescript(_f.read())
        else:
            from app.core.sqlite_migrator import run_sqlite_migrations
            run_sqlite_migrations(self.db_path, _migrations_dir)
    
    def store_access_event(self, event: AccessEvent):
        """Store access event"""
        self.conn.execute("""
        INSERT OR REPLACE INTO access_events
        (event_id, timestamp, user_id, username, access_type, resource, source_ip,
         authentication_method, access_status, risk_level, anomaly_score, is_suspicious, context)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.event_id, event.timestamp.isoformat(), event.user_id, event.username,
            event.access_type.value, event.resource, event.source_ip,
            event.authentication_method.value, event.access_status.value,
            event.risk_level.value, event.anomaly_score, int(event.is_suspicious),
            json.dumps(event.additional_context)
        ))
        self.conn.commit()
    
    def store_user_profile(self, profile: UserProfile):
        """Store user profile"""
        profile_data = {
            'roles': profile.roles,
            'permissions': profile.permissions,
            'typical_login_hours': profile.typical_login_hours,
            'typical_locations': profile.typical_locations,
            'typical_devices': profile.typical_devices,
            'behavioral_baseline': profile.behavioral_baseline
        }
        
        self.conn.execute("""
        INSERT OR REPLACE INTO user_profiles
        (user_id, username, email, account_type, creation_date, last_login,
         login_count, failed_login_count, mfa_enabled, account_locked, is_active,
         risk_score, profile_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile.user_id, profile.username, profile.email, profile.account_type.value,
            profile.creation_date.isoformat(),
            profile.last_login.isoformat() if profile.last_login else None,
            profile.login_count, profile.failed_login_count, int(profile.mfa_enabled),
            int(profile.account_locked), int(profile.is_active), profile.risk_score,
            json.dumps(profile_data)
        ))
        self.conn.commit()
    
    def store_privilege_escalation(self, escalation: PrivilegeEscalation):
        """Store privilege escalation"""
        details = {
            'from_permissions': escalation.from_permissions,
            'to_permissions': escalation.to_permissions,
            'context': escalation.context
        }
        
        self.conn.execute("""
        INSERT OR REPLACE INTO privilege_escalations
        (escalation_id, user_id, username, escalation_type, detection_timestamp,
         risk_level, confidence_score, investigated, false_positive, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            escalation.escalation_id, escalation.user_id, escalation.username,
            escalation.escalation_type, escalation.detection_timestamp.isoformat(),
            escalation.risk_level.value, escalation.confidence_score,
            int(escalation.investigated), int(escalation.false_positive),
            json.dumps(details)
        ))
        self.conn.commit()
    
    def store_access_anomaly(self, anomaly: AccessAnomaly):
        """Store access anomaly"""
        details = {
            'baseline_deviation': anomaly.baseline_deviation,
            'contributing_factors': anomaly.contributing_factors,
            'event_context': anomaly.event_context
        }
        
        self.conn.execute("""
        INSERT OR REPLACE INTO access_anomalies
        (anomaly_id, user_id, username, anomaly_type, description, detection_timestamp,
         anomaly_score, risk_level, requires_investigation, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            anomaly.anomaly_id, anomaly.user_id, anomaly.username, anomaly.anomaly_type,
            anomaly.description, anomaly.detection_timestamp.isoformat(),
            anomaly.anomaly_score, anomaly.risk_level.value,
            int(anomaly.requires_investigation), json.dumps(details)
        ))
        self.conn.commit()
    
    def get_recent_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent access events"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor = self.conn.execute("""
        SELECT * FROM access_events 
        WHERE timestamp > ? 
        ORDER BY timestamp DESC
        """, (cutoff,))
        return [dict(row) for row in cursor.fetchall()]

class BehavioralAnalyzer:
    """Behavioral analysis for access anomaly detection"""
    
    def __init__(self):
        self.user_baselines = {}  # user_id -> baseline metrics
        logger.info("Behavioral analyzer initialized")
    
    def update_user_baseline(self, user_id: str, events: List[AccessEvent]):
        """Update user behavioral baseline"""
        if not events:
            return
        
        # Calculate baseline metrics
        login_hours = []
        login_locations = []
        devices = []
        access_patterns = defaultdict(int)
        
        for event in events:
            if event.access_type == AccessType.LOGIN and event.access_status == AccessStatus.GRANTED:
                login_hours.append(event.timestamp.hour)
                if event.source_ip:
                    login_locations.append(event.source_ip)
                if event.device_info:
                    device_id = event.device_info.get('device_id', 'unknown')
                    devices.append(device_id)
                
                # Track access patterns
                access_patterns[event.resource] += 1
                access_patterns[f"hour_{event.timestamp.hour}"] += 1
                access_patterns[f"weekday_{event.timestamp.weekday()}"] += 1
        
        baseline = {
            'typical_hours': {
                'mean': statistics.mean(login_hours) if login_hours else 12,
                'std': statistics.stdev(login_hours) if len(login_hours) > 1 else 4
            },
            'common_locations': Counter(login_locations).most_common(5),
            'common_devices': Counter(devices).most_common(3),
            'access_frequency': dict(access_patterns),
            'total_logins': len([e for e in events if e.access_type == AccessType.LOGIN]),
            'failed_logins': len([e for e in events if e.access_type == AccessType.FAILED_LOGIN]),
            'last_updated': datetime.now().isoformat()
        }
        
        self.user_baselines[user_id] = baseline
        logger.debug(f"Updated baseline for user {user_id}")
    
    def calculate_anomaly_score(self, user_id: str, event: AccessEvent) -> Tuple[float, List[str]]:
        """Calculate anomaly score for an access event"""
        if user_id not in self.user_baselines:
            return 0.0, []
        
        baseline = self.user_baselines[user_id]
        anomaly_factors = []
        score = 0.0
        
        # Time-based anomaly
        if event.access_type == AccessType.LOGIN:
            hour_mean = baseline['typical_hours']['mean']
            hour_std = baseline['typical_hours']['std']
            hour_deviation = abs(event.timestamp.hour - hour_mean)
            
            if hour_deviation > 2 * hour_std:
                score += 0.3
                anomaly_factors.append(f"unusual_login_time_{event.timestamp.hour}")
        
        # Location-based anomaly
        common_locations = [loc[0] for loc in baseline['common_locations']]
        if event.source_ip and event.source_ip not in common_locations:
            score += 0.25
            anomaly_factors.append(f"new_location_{event.source_ip}")
        
        # Device-based anomaly
        if event.device_info:
            device_id = event.device_info.get('device_id', 'unknown')
            common_devices = [dev[0] for dev in baseline['common_devices']]
            if device_id not in common_devices:
                score += 0.2
                anomaly_factors.append(f"new_device_{device_id}")
        
        # Access pattern anomaly
        resource_frequency = baseline['access_frequency'].get(event.resource, 0)
        if resource_frequency == 0:
            score += 0.15
            anomaly_factors.append(f"new_resource_{event.resource}")
        
        # Failed login pattern
        if event.access_type == AccessType.FAILED_LOGIN:
            recent_failures = baseline.get('recent_failures', 0)
            if recent_failures > 3:
                score += 0.4
                anomaly_factors.append("multiple_failed_logins")
        
        # Privilege escalation pattern
        if event.access_type == AccessType.PRIVILEGE_ESCALATION:
            score += 0.5
            anomaly_factors.append("privilege_escalation_attempt")
        
        return min(score, 1.0), anomaly_factors

class PrivilegeEscalationDetector:
    """Privilege escalation detection system"""
    
    def __init__(self):
        self.permission_hierarchy = self._build_permission_hierarchy()
        self.recent_escalations = {}  # user_id -> list of escalations
        logger.info("Privilege escalation detector initialized")
    
    def _build_permission_hierarchy(self) -> Dict[str, int]:
        """Build permission hierarchy for escalation detection"""
        return {
            'guest': 1,
            'user': 2,
            'power_user': 3,
            'admin': 4,
            'super_admin': 5,
            'system_admin': 6,
            'root': 10
        }
    
    def detect_escalation(self, user_id: str, old_permissions: List[str], 
                         new_permissions: List[str]) -> Optional[PrivilegeEscalation]:
        """Detect privilege escalation"""
        
        old_level = max([self.permission_hierarchy.get(perm, 0) for perm in old_permissions] or [0])
        new_level = max([self.permission_hierarchy.get(perm, 0) for perm in new_permissions] or [0])
        
        if new_level <= old_level:
            return None
        
        # Calculate escalation type
        escalation_type = "vertical"  # Default
        if new_level - old_level >= 3:
            escalation_type = "major_vertical"
        elif len(new_permissions) > len(old_permissions) * 2:
            escalation_type = "horizontal"
        
        # Calculate risk and confidence
        level_jump = new_level - old_level
        risk_level = RiskLevel.LOW
        confidence_score = 0.5
        
        if level_jump >= 5:
            risk_level = RiskLevel.CRITICAL
            confidence_score = 0.9
        elif level_jump >= 3:
            risk_level = RiskLevel.HIGH
            confidence_score = 0.8
        elif level_jump >= 2:
            risk_level = RiskLevel.MEDIUM
            confidence_score = 0.7
        
        # Check for suspicious patterns
        if user_id in self.recent_escalations:
            recent_count = len(self.recent_escalations[user_id])
            if recent_count > 2:  # Multiple escalations
                risk_level = RiskLevel.CRITICAL
                confidence_score = min(confidence_score + 0.2, 1.0)
        
        escalation = PrivilegeEscalation(
            escalation_id=str(uuid.uuid4()),
            user_id=user_id,
            username=f"user_{user_id}",
            from_permissions=old_permissions,
            to_permissions=new_permissions,
            escalation_type=escalation_type,
            detection_timestamp=datetime.now(),
            risk_level=risk_level,
            confidence_score=confidence_score,
            context={
                'old_level': old_level,
                'new_level': new_level,
                'level_jump': level_jump,
                'permission_delta': list(set(new_permissions) - set(old_permissions))
            }
        )
        
        # Track escalation
        if user_id not in self.recent_escalations:
            self.recent_escalations[user_id] = []
        self.recent_escalations[user_id].append(escalation)
        
        # Keep only recent escalations (last 24 hours)
        cutoff = datetime.now() - timedelta(hours=24)
        self.recent_escalations[user_id] = [
            e for e in self.recent_escalations[user_id] 
            if e.detection_timestamp > cutoff
        ]
        
        logger.warning(f"Privilege escalation detected for user {user_id}: {escalation_type} ({risk_level.value})")
        
        return escalation

class IAMMonitoringSystem:
    """Main IAM monitoring and access control system"""
    
    def __init__(self):
        self.database = IAMDatabase()
        self.behavioral_analyzer = BehavioralAnalyzer()
        self.escalation_detector = PrivilegeEscalationDetector()
        self.user_profiles = {}  # user_id -> UserProfile
        self.access_rules = {}  # rule_id -> AccessRule
        self.active_sessions = {}  # session_id -> session_info
        
        # Initialize with sample data
        self._load_sample_data()
        
        logger.info("IAM monitoring system initialized")
    
    def _load_sample_data(self):
        """Load sample users, rules, and profiles"""
        
        # Sample user profiles
        sample_users = [
            UserProfile(
                user_id="USER-001",
                username="john.doe",
                email="john.doe@company.com",
                account_type=AccountType.STANDARD_USER,
                creation_date=datetime.now() - timedelta(days=365),
                last_login=datetime.now() - timedelta(hours=2),
                login_count=1250,
                failed_login_count=3,
                roles=["employee", "developer"],
                permissions=["read", "write", "execute"],
                typical_login_hours=[8, 9, 10, 14, 15, 16, 17],
                typical_locations=["192.168.1.100", "10.0.1.50"],
                typical_devices=["device_123", "device_456"],
                mfa_enabled=True,
                last_password_change=datetime.now() - timedelta(days=90)
            ),
            UserProfile(
                user_id="USER-002",
                username="jane.smith",
                email="jane.smith@company.com",
                account_type=AccountType.PRIVILEGED_USER,
                creation_date=datetime.now() - timedelta(days=200),
                last_login=datetime.now() - timedelta(hours=8),
                login_count=890,
                failed_login_count=1,
                roles=["employee", "manager", "security_admin"],
                permissions=["read", "write", "execute", "admin", "security"],
                typical_login_hours=[7, 8, 9, 13, 14, 15, 16],
                typical_locations=["192.168.1.200"],
                typical_devices=["device_789"],
                mfa_enabled=True,
                last_password_change=datetime.now() - timedelta(days=45)
            ),
            UserProfile(
                user_id="USER-003",
                username="admin.user",
                email="admin@company.com",
                account_type=AccountType.ADMIN_ACCOUNT,
                creation_date=datetime.now() - timedelta(days=500),
                last_login=datetime.now() - timedelta(hours=4),
                login_count=2100,
                failed_login_count=0,
                roles=["admin", "super_admin"],
                permissions=["read", "write", "execute", "admin", "super_admin", "system"],
                typical_login_hours=[6, 7, 8, 9, 18, 19, 20],
                typical_locations=["192.168.1.10"],
                typical_devices=["admin_device_001"],
                mfa_enabled=True,
                last_password_change=datetime.now() - timedelta(days=30)
            ),
            UserProfile(
                user_id="SVC-001",
                username="api.service",
                email="api-service@company.com",
                account_type=AccountType.SERVICE_ACCOUNT,
                creation_date=datetime.now() - timedelta(days=100),
                last_login=datetime.now() - timedelta(minutes=5),
                login_count=50000,
                failed_login_count=10,
                roles=["service", "api_access"],
                permissions=["api_read", "api_write"],
                typical_login_hours=list(range(24)),  # 24/7 service
                typical_locations=["10.0.2.100"],
                typical_devices=["server_001"],
                mfa_enabled=False,
                last_password_change=datetime.now() - timedelta(days=60)
            )
        ]
        
        for user in sample_users:
            self.user_profiles[user.user_id] = user
            self.database.store_user_profile(user)
        
        # Sample access rules
        sample_rules = [
            AccessRule(
                rule_id="RULE-001",
                name="Standard User Access",
                description="Basic access for standard users",
                resource_pattern="app/*",
                allowed_roles=["employee"],
                allowed_permissions=["read", "write"],
                time_restrictions={"allowed_hours": [6, 22]},
                location_restrictions=["192.168.1.0/24"]
            ),
            AccessRule(
                rule_id="RULE-002",
                name="Admin Access",
                description="Administrative access",
                resource_pattern="admin/*",
                allowed_roles=["admin", "super_admin"],
                allowed_permissions=["admin", "super_admin"],
                time_restrictions={"allowed_hours": [6, 20]},
                location_restrictions=["192.168.1.0/24", "10.0.1.0/24"]
            ),
            AccessRule(
                rule_id="RULE-003",
                name="Service Account Access",
                description="Service account API access",
                resource_pattern="api/*",
                allowed_roles=["service"],
                allowed_permissions=["api_read", "api_write"]
            )
        ]
        
        for rule in sample_rules:
            self.access_rules[rule.rule_id] = rule
        
        logger.info(f"Loaded sample data: {len(sample_users)} users, {len(sample_rules)} access rules")
    
    async def process_access_event(self, event_data: Dict[str, Any]) -> AccessEvent:
        """Process incoming access event"""
        
        # Create access event
        event = AccessEvent(
            event_id=event_data.get('event_id', str(uuid.uuid4())),
            timestamp=datetime.fromisoformat(event_data.get('timestamp', datetime.now().isoformat())),
            user_id=event_data['user_id'],
            username=event_data['username'],
            access_type=AccessType(event_data['access_type']),
            resource=event_data['resource'],
            source_ip=event_data['source_ip'],
            user_agent=event_data.get('user_agent', ''),
            authentication_method=AuthenticationMethod(event_data.get('auth_method', 'password')),
            access_status=AccessStatus(event_data['access_status']),
            risk_level=RiskLevel.LOW,  # Will be updated
            session_id=event_data.get('session_id'),
            geolocation=event_data.get('geolocation'),
            device_info=event_data.get('device_info'),
            permissions_granted=event_data.get('permissions_granted', []),
            additional_context=event_data.get('context', {})
        )
        
        # Behavioral analysis
        user_id = event.user_id
        if user_id in self.user_profiles:
            # Get recent events for baseline update
            recent_events = await self._get_user_recent_events(user_id, hours=168)  # 1 week
            self.behavioral_analyzer.update_user_baseline(user_id, recent_events)
            
            # Calculate anomaly score
            anomaly_score, factors = self.behavioral_analyzer.calculate_anomaly_score(user_id, event)
            event.anomaly_score = anomaly_score
            event.is_suspicious = anomaly_score > 0.6
            
            if factors:
                event.additional_context['anomaly_factors'] = factors
        
        # Risk assessment
        event.risk_level = self._assess_risk_level(event)
        
        # Check for privilege escalation
        if event.access_type == AccessType.PERMISSION_CHANGE:
            await self._check_privilege_escalation(event)
        
        # Generate access anomaly if needed
        if event.is_suspicious:
            await self._generate_access_anomaly(event)
        
        # Store event
        self.database.store_access_event(event)
        
        # Update user profile
        if user_id in self.user_profiles:
            await self._update_user_profile(user_id, event)
        
        logger.info(f"Processed access event {event.event_id} for user {event.username}")
        
        return event
    
    async def _get_user_recent_events(self, user_id: str, hours: int = 24) -> List[AccessEvent]:
        """Get recent events for a user"""
        # In a real implementation, this would query the database
        # For demo purposes, return empty list
        return []
    
    def _assess_risk_level(self, event: AccessEvent) -> RiskLevel:
        """Assess risk level for an access event"""
        
        risk_score = 0.0
        
        # Base risk by access type
        type_risks = {
            AccessType.FAILED_LOGIN: 0.3,
            AccessType.PRIVILEGE_ESCALATION: 0.8,
            AccessType.MFA_BYPASS: 0.7,
            AccessType.ACCOUNT_CREATION: 0.5,
            AccessType.PERMISSION_CHANGE: 0.6,
            AccessType.LOGIN: 0.1
        }
        
        risk_score += type_risks.get(event.access_type, 0.1)
        
        # Account type risk
        if event.user_id in self.user_profiles:
            user = self.user_profiles[event.user_id]
            if user.account_type in [AccountType.ADMIN_ACCOUNT, AccountType.PRIVILEGED_USER]:
                risk_score += 0.2
        
        # Authentication method risk
        auth_risks = {
            AuthenticationMethod.PASSWORD: 0.2,
            AuthenticationMethod.API_KEY: 0.3,
            AuthenticationMethod.MFA: 0.0,
            AuthenticationMethod.SSO: 0.1
        }
        risk_score += auth_risks.get(event.authentication_method, 0.1)
        
        # Anomaly score contribution
        risk_score += event.anomaly_score * 0.5
        
        # Access status risk
        if event.access_status == AccessStatus.DENIED:
            risk_score += 0.2
        
        # Convert to risk level
        if risk_score >= 0.8:
            return RiskLevel.CRITICAL
        elif risk_score >= 0.6:
            return RiskLevel.HIGH
        elif risk_score >= 0.4:
            return RiskLevel.MEDIUM
        elif risk_score >= 0.2:
            return RiskLevel.LOW
        else:
            return RiskLevel.INFORMATIONAL
    
    async def _check_privilege_escalation(self, event: AccessEvent):
        """Check for privilege escalation"""
        user_id = event.user_id
        
        if user_id not in self.user_profiles:
            return
        
        user = self.user_profiles[user_id]
        old_permissions = user.permissions.copy()
        new_permissions = event.permissions_granted
        
        if new_permissions:
            escalation = self.escalation_detector.detect_escalation(
                user_id, old_permissions, new_permissions
            )
            
            if escalation:
                self.database.store_privilege_escalation(escalation)
                logger.warning(f"Privilege escalation detected: {escalation.escalation_id}")
    
    async def _generate_access_anomaly(self, event: AccessEvent):
        """Generate access anomaly record"""
        user_id = event.user_id
        factors = event.additional_context.get('anomaly_factors', [])
        
        anomaly = AccessAnomaly(
            anomaly_id=str(uuid.uuid4()),
            user_id=user_id,
            username=event.username,
            anomaly_type="behavioral_deviation",
            description=f"Anomalous access pattern detected: {', '.join(factors)}",
            detection_timestamp=event.timestamp,
            anomaly_score=event.anomaly_score,
            risk_level=event.risk_level,
            baseline_deviation={},
            contributing_factors=factors,
            event_context={
                'event_id': event.event_id,
                'access_type': event.access_type.value,
                'resource': event.resource,
                'source_ip': event.source_ip
            }
        )
        
        self.database.store_access_anomaly(anomaly)
        logger.info(f"Access anomaly generated: {anomaly.anomaly_id}")
    
    async def _update_user_profile(self, user_id: str, event: AccessEvent):
        """Update user profile based on access event"""
        if user_id not in self.user_profiles:
            return
        
        user = self.user_profiles[user_id]
        
        # Update login statistics
        if event.access_type == AccessType.LOGIN:
            if event.access_status == AccessStatus.GRANTED:
                user.login_count += 1
                user.last_login = event.timestamp
            else:
                user.failed_login_count += 1
        
        # Update typical patterns
        if event.access_status == AccessStatus.GRANTED:
            if event.timestamp.hour not in user.typical_login_hours:
                user.typical_login_hours.append(event.timestamp.hour)
                user.typical_login_hours = sorted(user.typical_login_hours)
            
            if event.source_ip not in user.typical_locations:
                user.typical_locations.append(event.source_ip)
        
        # Store updated profile
        self.database.store_user_profile(user)
    
    def get_iam_dashboard_data(self) -> Dict[str, Any]:
        """Get IAM monitoring dashboard data"""
        
        # User statistics
        total_users = len(self.user_profiles)
        active_users = len([u for u in self.user_profiles.values() if u.is_active])
        privileged_users = len([u for u in self.user_profiles.values() 
                              if u.account_type in [AccountType.PRIVILEGED_USER, AccountType.ADMIN_ACCOUNT]])
        mfa_enabled_users = len([u for u in self.user_profiles.values() if u.mfa_enabled])
        
        # Account type distribution
        account_types = Counter(u.account_type.value for u in self.user_profiles.values())
        
        # Recent events (last 24 hours)
        recent_events = self.database.get_recent_events(24)
        
        # Risk distribution
        risk_distribution = Counter(event['risk_level'] for event in recent_events)
        
        # Access patterns
        access_types = Counter(event['access_type'] for event in recent_events)
        auth_methods = Counter(event['authentication_method'] for event in recent_events)
        
        # Suspicious activity
        suspicious_events = [e for e in recent_events if e['is_suspicious']]
        
        # Failed logins
        failed_logins = [e for e in recent_events if e['access_type'] == 'failed_login']
        
        return {
            'timestamp': datetime.now().isoformat(),
            'user_statistics': {
                'total_users': total_users,
                'active_users': active_users,
                'privileged_users': privileged_users,
                'mfa_enabled_users': mfa_enabled_users,
                'mfa_adoption_rate': (mfa_enabled_users / total_users * 100) if total_users > 0 else 0,
                'account_type_distribution': dict(account_types)
            },
            'access_statistics': {
                'total_events_24h': len(recent_events),
                'risk_distribution': dict(risk_distribution),
                'access_type_distribution': dict(access_types),
                'authentication_method_distribution': dict(auth_methods),
                'suspicious_events': len(suspicious_events),
                'failed_logins': len(failed_logins)
            },
            'security_metrics': {
                'average_risk_score': sum(u.risk_score for u in self.user_profiles.values()) / len(self.user_profiles) if self.user_profiles else 0,
                'privilege_escalations_24h': len([e for e in recent_events if e['access_type'] == 'privilege_escalation']),
                'anomaly_rate': (len(suspicious_events) / len(recent_events) * 100) if recent_events else 0,
                'failed_login_rate': (len(failed_logins) / len(recent_events) * 100) if recent_events else 0
            },
            'recent_activity': {
                'top_users_by_activity': self._get_top_active_users(recent_events),
                'top_resources_accessed': self._get_top_resources(recent_events),
                'suspicious_activities': suspicious_events[:10],
                'recent_privilege_changes': [e for e in recent_events if e['access_type'] == 'permission_change'][:5]
            }
        }
    
    def _get_top_active_users(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get top active users from recent events"""
        user_activity = Counter(event['username'] for event in events)
        top_users = user_activity.most_common(5)
        
        result = []
        for username, count in top_users:
            # Find user by username
            user_type = AccountType.STANDARD_USER.value
            for uid, user in self.user_profiles.items():
                if user.username == username:
                    user_type = user.account_type.value
                    break
            
            result.append({
                'username': username,
                'event_count': count,
                'user_type': user_type
            })
        
        return result
    
    def _get_top_resources(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get top accessed resources from recent events"""
        resource_access = Counter(event['resource'] for event in events)
        top_resources = resource_access.most_common(5)
        
        return [
            {
                'resource': resource,
                'access_count': count,
                'unique_users': len(set(e['username'] for e in events if e['resource'] == resource))
            }
            for resource, count in top_resources
        ]

async def demonstrate_iam_monitoring():
    """Demonstrate the IAM monitoring system"""
    print("AIOps IAM & Access Control Monitoring System Demo")
    print("=" * 58)
    
    # Initialize IAM monitoring system
    iam_system = IAMMonitoringSystem()
    
    print("🔐 IAM monitoring system initialized with sample data\n")
    
    # Show initial dashboard
    dashboard = iam_system.get_iam_dashboard_data()
    
    print("👥 User Statistics:")
    user_stats = dashboard['user_statistics']
    print(f"  Total Users: {user_stats['total_users']}")
    print(f"  Active Users: {user_stats['active_users']}")
    print(f"  Privileged Users: {user_stats['privileged_users']}")
    print(f"  MFA Enabled: {user_stats['mfa_enabled_users']} ({user_stats['mfa_adoption_rate']:.1f}%)")
    
    print(f"\n📊 Account Type Distribution:")
    for account_type, count in user_stats['account_type_distribution'].items():
        print(f"  {account_type}: {count}")
    
    # Simulate access events
    print(f"\n🚨 Processing access events for monitoring...")
    
    sample_events = [
        {
            'event_id': 'IAM-001',
            'timestamp': datetime.now().isoformat(),
            'user_id': 'USER-001',
            'username': 'john.doe',
            'access_type': 'login',
            'resource': 'app/dashboard',
            'source_ip': '192.168.1.100',
            'auth_method': 'mfa',
            'access_status': 'granted',
            'device_info': {'device_id': 'device_123'},
            'permissions_granted': ['read', 'write']
        },
        {
            'event_id': 'IAM-002',
            'timestamp': (datetime.now() - timedelta(minutes=30)).isoformat(),
            'user_id': 'USER-001',
            'username': 'john.doe',
            'access_type': 'login',
            'resource': 'app/dashboard',
            'source_ip': '203.0.113.100',  # Unusual location
            'auth_method': 'password',
            'access_status': 'granted',
            'device_info': {'device_id': 'device_999'},  # New device
            'permissions_granted': ['read', 'write']
        },
        {
            'event_id': 'IAM-003',
            'timestamp': (datetime.now() - timedelta(hours=1)).isoformat(),
            'user_id': 'USER-002',
            'username': 'jane.smith',
            'access_type': 'permission_change',
            'resource': 'admin/users',
            'source_ip': '192.168.1.200',
            'auth_method': 'mfa',
            'access_status': 'granted',
            'permissions_granted': ['read', 'write', 'admin', 'super_admin', 'system']  # Escalation
        },
        {
            'event_id': 'IAM-004',
            'timestamp': (datetime.now() - timedelta(minutes=15)).isoformat(),
            'user_id': 'USER-003',
            'username': 'admin.user',
            'access_type': 'login',
            'resource': 'admin/system',
            'source_ip': '192.168.1.10',
            'auth_method': 'mfa',
            'access_status': 'granted',
            'permissions_granted': ['admin', 'super_admin', 'system']
        },
        {
            'event_id': 'IAM-005',
            'timestamp': (datetime.now() - timedelta(minutes=45)).isoformat(),
            'user_id': 'USER-001',
            'username': 'john.doe',
            'access_type': 'failed_login',
            'resource': 'app/login',
            'source_ip': '198.51.100.50',  # Suspicious IP
            'auth_method': 'password',
            'access_status': 'denied'
        }
    ]
    
    processed_events = []
    
    for event_data in sample_events:
        print(f"  Processing event {event_data['event_id']}...")
        event = await iam_system.process_access_event(event_data)
        processed_events.append(event)
        
        risk_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "informational": "ℹ️"}.get(event.risk_level.value, "ℹ️")
        print(f"    {risk_icon} {event.access_type.value} by {event.username} - {event.risk_level.value}")
        
        if event.is_suspicious:
            print(f"      ⚠️ Anomaly detected (score: {event.anomaly_score:.2f})")
            if 'anomaly_factors' in event.additional_context:
                factors = event.additional_context['anomaly_factors']
                print(f"      Factors: {', '.join(factors)}")
    
    # Show updated dashboard
    print(f"\n📊 Updated IAM Dashboard:")
    updated_dashboard = iam_system.get_iam_dashboard_data()
    
    access_stats = updated_dashboard['access_statistics']
    security_metrics = updated_dashboard['security_metrics']
    
    print(f"  Events (24h): {access_stats['total_events_24h']}")
    print(f"  Suspicious Events: {access_stats['suspicious_events']}")
    print(f"  Failed Logins: {access_stats['failed_logins']}")
    print(f"  Privilege Escalations: {security_metrics['privilege_escalations_24h']}")
    
    print(f"\n🔍 Risk Distribution:")
    for risk_level, count in access_stats['risk_distribution'].items():
        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "informational": "ℹ️"}.get(risk_level, "ℹ️")
        print(f"  {icon} {risk_level}: {count}")
    
    print(f"\n🔐 Authentication Methods:")
    for method, count in access_stats['authentication_method_distribution'].items():
        print(f"  {method}: {count}")
    
    print(f"\n📈 Security Metrics:")
    print(f"  Average Risk Score: {security_metrics['average_risk_score']:.2f}")
    print(f"  Anomaly Rate: {security_metrics['anomaly_rate']:.1f}%")
    print(f"  Failed Login Rate: {security_metrics['failed_login_rate']:.1f}%")
    
    # Show recent activity
    recent_activity = updated_dashboard['recent_activity']
    
    print(f"\n👥 Top Active Users:")
    for user in recent_activity['top_users_by_activity']:
        print(f"  • {user['username']} ({user['user_type']}): {user['event_count']} events")
    
    print(f"\n📁 Top Accessed Resources:")
    for resource in recent_activity['top_resources_accessed']:
        print(f"  • {resource['resource']}: {resource['access_count']} accesses ({resource['unique_users']} unique users)")
    
    # Show specific alerts
    print(f"\n⚠️ Security Alerts:")
    
    suspicious_events = recent_activity['suspicious_activities']
    if suspicious_events:
        print(f"  Suspicious Activities ({len(suspicious_events)}):")
        for event in suspicious_events[:3]:
            print(f"    • {event['username']} - {event['access_type']} from {event['source_ip']}")
    
    privilege_changes = recent_activity['recent_privilege_changes']
    if privilege_changes:
        print(f"  Recent Privilege Changes ({len(privilege_changes)}):")
        for event in privilege_changes:
            print(f"    • {event['username']} - permissions modified")
    
    # Show user profiles with risk assessment
    print(f"\n👤 User Risk Assessment:")
    for user_id, user in iam_system.user_profiles.items():
        risk_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
            "high" if user.failed_login_count > 5 else "medium" if user.failed_login_count > 2 else "low", "🟢"
        )
        print(f"  {risk_icon} {user.username} ({user.account_type.value})")
        print(f"    Login Count: {user.login_count}, Failed: {user.failed_login_count}")
        print(f"    MFA Enabled: {'Yes' if user.mfa_enabled else 'No'}")
        print(f"    Last Login: {user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never'}")
    
    print(f"\n🔧 System Capabilities:")
    print(f"  • Real-time access pattern monitoring")
    print(f"  • Behavioral anomaly detection")
    print(f"  • Privilege escalation detection")
    print(f"  • Multi-factor authentication tracking")
    print(f"  • Identity lifecycle management")
    print(f"  • Role-based access control monitoring")
    print(f"  • Automated risk assessment")
    
    print(f"\n✅ IAM monitoring demonstration completed!")
    print(f"🎯 Key Benefits:")
    print(f"  • Proactive identity threat detection")
    print(f"  • Behavioral baseline establishment")
    print(f"  • Automated privilege monitoring")
    print(f"  • Comprehensive access auditing")
    print(f"  • Real-time anomaly alerting")

if __name__ == "__main__":
    asyncio.run(demonstrate_iam_monitoring())