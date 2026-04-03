#!/usr/bin/env python3
"""
AIOps Compliance Automation Framework
Advanced compliance automation with audit trails, policy enforcement, and violation detection

Features:
- Multi-standard compliance automation (SOC2, GDPR, HIPAA, PCI DSS, ISO 27001)
- Real-time policy enforcement and violation detection
- Automated audit trail generation and management
- Evidence collection and compliance reporting
- Risk assessment and remediation workflows
- Continuous compliance monitoring and scoring
"""

import asyncio
import json
import logging
import hashlib
import time
import os
import csv
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, Counter
import uuid
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('compliance_automation')

class ComplianceFramework(Enum):
    """Supported compliance frameworks"""
    SOC2_TYPE1 = "soc2_type1"
    SOC2_TYPE2 = "soc2_type2"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO_27001 = "iso_27001"
    NIST_CSF = "nist_csf"
    FedRAMP = "fedramp"

class PolicyType(Enum):
    """Types of compliance policies"""
    ACCESS_CONTROL = "access_control"
    DATA_PROTECTION = "data_protection"
    INCIDENT_RESPONSE = "incident_response"
    VULNERABILITY_MANAGEMENT = "vulnerability_management"
    CHANGE_MANAGEMENT = "change_management"
    BUSINESS_CONTINUITY = "business_continuity"
    VENDOR_MANAGEMENT = "vendor_management"
    TRAINING_AWARENESS = "training_awareness"

class ViolationSeverity(Enum):
    """Severity levels for compliance violations"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

class ComplianceStatus(Enum):
    """Compliance status levels"""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NOT_APPLICABLE = "not_applicable"
    PENDING_REVIEW = "pending_review"

class AuditEventType(Enum):
    """Types of audit events"""
    POLICY_CREATED = "policy_created"
    POLICY_UPDATED = "policy_updated"
    POLICY_DELETED = "policy_deleted"
    VIOLATION_DETECTED = "violation_detected"
    VIOLATION_RESOLVED = "violation_resolved"
    EVIDENCE_COLLECTED = "evidence_collected"
    CONTROL_TESTED = "control_tested"
    ASSESSMENT_COMPLETED = "assessment_completed"
    REMEDIATION_INITIATED = "remediation_initiated"

@dataclass
class CompliancePolicy:
    """Compliance policy definition"""
    policy_id: str
    name: str
    framework: ComplianceFramework
    policy_type: PolicyType
    control_id: str
    description: str
    requirements: List[str]
    implementation_guidance: str
    testing_procedures: List[str]
    evidence_requirements: List[str]
    risk_level: ViolationSeverity
    mandatory: bool = True
    frequency_days: int = 90
    owner: str = "compliance_team"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0"

@dataclass
class ComplianceViolation:
    """Compliance violation record"""
    violation_id: str
    policy_id: str
    framework: ComplianceFramework
    severity: ViolationSeverity
    title: str
    description: str
    affected_systems: List[str]
    detected_at: datetime
    root_cause: Optional[str] = None
    remediation_plan: Optional[str] = None
    remediation_deadline: Optional[datetime] = None
    status: str = "open"  # open, in_progress, resolved, false_positive
    assigned_to: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    business_impact: str = "medium"
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None

@dataclass
class AuditTrail:
    """Audit trail entry"""
    audit_id: str
    event_type: AuditEventType
    timestamp: datetime
    user_id: str
    source_system: str
    object_type: str
    object_id: str
    action: str
    details: Dict[str, Any]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    integrity_hash: Optional[str] = None

@dataclass
class EvidenceItem:
    """Evidence collection item"""
    evidence_id: str
    policy_id: str
    control_id: str
    evidence_type: str  # document, screenshot, log_file, configuration, etc.
    title: str
    description: str
    file_path: Optional[str]
    content: Optional[str]
    metadata: Dict[str, Any]
    collected_at: datetime
    collected_by: str
    hash_value: str
    retention_days: int = 2555  # 7 years default

@dataclass
class ComplianceAssessment:
    """Compliance assessment result"""
    assessment_id: str
    framework: ComplianceFramework
    scope: str
    assessed_by: str
    assessment_date: datetime
    status: ComplianceStatus
    score: float  # 0-100
    total_controls: int
    compliant_controls: int
    non_compliant_controls: int
    findings: List[str]
    recommendations: List[str]
    next_assessment_date: datetime
    report_path: Optional[str] = None

class PolicyEngine:
    """Compliance policy management and enforcement engine"""
    
    def __init__(self, db_path: str = "compliance.db"):
        self.db_path = db_path
        self.policies = {}
        self.violations = []
        self.audit_trail = []
        self.evidence_store = {}
        
        # Initialize database
        self._init_database()
        
        # Load default policies
        self._load_default_policies()
        
        logger.info("Compliance policy engine initialized")
    
    def _init_database(self):
        """Apply schema migrations for the compliance automation SQLite database."""
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _migrations_dir = _os.path.join(
            _here, "..", "..", "migrations", "sqlite", "security_compliance"
        )
        try:
            self.conn = sqlite3.connect(self.db_path)
            from app.core.sqlite_migrator import run_sqlite_migrations
            run_sqlite_migrations(self.db_path, _migrations_dir)
            logger.info("Compliance database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize compliance database: {e}")
    
    def _load_default_policies(self):
        """Load default compliance policies"""
        
        # SOC 2 Type II policies
        soc2_policies = [
            {
                'policy_id': 'SOC2-CC6.1',
                'name': 'Logical and Physical Access Controls',
                'framework': ComplianceFramework.SOC2_TYPE2,
                'policy_type': PolicyType.ACCESS_CONTROL,
                'control_id': 'CC6.1',
                'description': 'The entity implements logical and physical access security software, infrastructure, and architectures over protected information assets.',
                'requirements': [
                    'Multi-factor authentication for privileged accounts',
                    'Regular access reviews and recertification',
                    'Physical security controls for data centers',
                    'Network segmentation and firewall rules'
                ],
                'implementation_guidance': 'Implement role-based access control (RBAC) with principle of least privilege',
                'testing_procedures': [
                    'Review user access lists',
                    'Test MFA configuration',
                    'Validate physical access logs'
                ],
                'evidence_requirements': [
                    'User access matrices',
                    'MFA configuration screenshots',
                    'Physical access logs'
                ],
                'risk_level': ViolationSeverity.HIGH
            },
            {
                'policy_id': 'SOC2-CC7.1',
                'name': 'System Monitoring',
                'framework': ComplianceFramework.SOC2_TYPE2,
                'policy_type': PolicyType.INCIDENT_RESPONSE,
                'control_id': 'CC7.1',
                'description': 'The entity uses detection and monitoring procedures to identify system security events.',
                'requirements': [
                    'Continuous monitoring of system activities',
                    'Security event logging and alerting',
                    'Incident response procedures',
                    'Regular log reviews'
                ],
                'implementation_guidance': 'Deploy SIEM solution with automated alerting',
                'testing_procedures': [
                    'Review security logs',
                    'Test alerting mechanisms',
                    'Validate incident response procedures'
                ],
                'evidence_requirements': [
                    'Security monitoring dashboards',
                    'Incident response logs',
                    'Alert configuration settings'
                ],
                'risk_level': ViolationSeverity.MEDIUM
            }
        ]
        
        # GDPR policies
        gdpr_policies = [
            {
                'policy_id': 'GDPR-ART32',
                'name': 'Security of Processing',
                'framework': ComplianceFramework.GDPR,
                'policy_type': PolicyType.DATA_PROTECTION,
                'control_id': 'Article 32',
                'description': 'Taking into account the state of the art, implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk.',
                'requirements': [
                    'Encryption of personal data at rest and in transit',
                    'Regular testing and evaluation of security measures',
                    'Access controls and authentication',
                    'Data backup and recovery procedures'
                ],
                'implementation_guidance': 'Implement AES-256 encryption and regular security assessments',
                'testing_procedures': [
                    'Verify encryption implementation',
                    'Test backup and recovery procedures',
                    'Review access control logs'
                ],
                'evidence_requirements': [
                    'Encryption certificates',
                    'Security assessment reports',
                    'Backup test results'
                ],
                'risk_level': ViolationSeverity.CRITICAL
            }
        ]
        
        # HIPAA policies
        hipaa_policies = [
            {
                'policy_id': 'HIPAA-164.312A',
                'name': 'Access Control',
                'framework': ComplianceFramework.HIPAA,
                'policy_type': PolicyType.ACCESS_CONTROL,
                'control_id': '164.312(a)(1)',
                'description': 'Implement technical policies and procedures for electronic information systems that maintain electronic protected health information.',
                'requirements': [
                    'Unique user identification',
                    'Role-based access controls',
                    'Access logging and monitoring',
                    'Automatic logoff procedures'
                ],
                'implementation_guidance': 'Implement comprehensive access control system with audit trails',
                'testing_procedures': [
                    'Review user accounts and roles',
                    'Test automatic logoff functionality',
                    'Validate access logs'
                ],
                'evidence_requirements': [
                    'User access reports',
                    'Role assignment documentation',
                    'Access audit logs'
                ],
                'risk_level': ViolationSeverity.CRITICAL
            }
        ]
        
        # Combine all policies
        all_policies = soc2_policies + gdpr_policies + hipaa_policies
        
        for policy_data in all_policies:
            policy = CompliancePolicy(
                policy_id=policy_data['policy_id'],
                name=policy_data['name'],
                framework=policy_data['framework'],
                policy_type=policy_data['policy_type'],
                control_id=policy_data['control_id'],
                description=policy_data['description'],
                requirements=policy_data['requirements'],
                implementation_guidance=policy_data['implementation_guidance'],
                testing_procedures=policy_data['testing_procedures'],
                evidence_requirements=policy_data['evidence_requirements'],
                risk_level=policy_data['risk_level']
            )
            
            self.policies[policy.policy_id] = policy
            self._save_policy_to_db(policy)
        
        logger.info(f"Loaded {len(all_policies)} default compliance policies")
    
    def _save_policy_to_db(self, policy: CompliancePolicy):
        """Save policy to database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO policies 
                (policy_id, name, framework, policy_type, control_id, description, 
                 requirements, implementation_guidance, testing_procedures, 
                 evidence_requirements, risk_level, mandatory, frequency_days, 
                 owner, created_at, updated_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                policy.policy_id, policy.name, policy.framework.value,
                policy.policy_type.value, policy.control_id, policy.description,
                json.dumps(policy.requirements), policy.implementation_guidance,
                json.dumps(policy.testing_procedures), json.dumps(policy.evidence_requirements),
                policy.risk_level.value, policy.mandatory, policy.frequency_days,
                policy.owner, policy.created_at.isoformat(), policy.updated_at.isoformat(),
                policy.version
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save policy {policy.policy_id}: {e}")
    
    async def check_policy_compliance(self, policy_id: str) -> Tuple[ComplianceStatus, List[str]]:
        """Check compliance for a specific policy"""
        if policy_id not in self.policies:
            return ComplianceStatus.NOT_APPLICABLE, ["Policy not found"]
        
        policy = self.policies[policy_id]
        findings = []
        
        # Simulate policy compliance checks based on policy type
        if policy.policy_type == PolicyType.ACCESS_CONTROL:
            compliance_score = await self._check_access_control_compliance(policy)
        elif policy.policy_type == PolicyType.DATA_PROTECTION:
            compliance_score = await self._check_data_protection_compliance(policy)
        elif policy.policy_type == PolicyType.INCIDENT_RESPONSE:
            compliance_score = await self._check_incident_response_compliance(policy)
        else:
            compliance_score = 75.0  # Default simulation
        
        # Determine compliance status based on score
        if compliance_score >= 95:
            status = ComplianceStatus.COMPLIANT
        elif compliance_score >= 70:
            status = ComplianceStatus.PARTIALLY_COMPLIANT
            findings.append(f"Compliance score {compliance_score}% below target of 95%")
        else:
            status = ComplianceStatus.NON_COMPLIANT
            findings.append(f"Critical compliance gaps detected (score: {compliance_score}%)")
        
        # Generate detailed findings
        if compliance_score < 100:
            findings.extend(self._generate_compliance_findings(policy, compliance_score))
        
        return status, findings
    
    async def _check_access_control_compliance(self, policy: CompliancePolicy) -> float:
        """Check access control compliance"""
        checks = {
            'mfa_enabled': 90,  # 90% compliance
            'rbac_implemented': 85,  # 85% compliance
            'access_reviews': 70,   # 70% compliance
            'privileged_access_monitoring': 80  # 80% compliance
        }
        
        return sum(checks.values()) / len(checks)
    
    async def _check_data_protection_compliance(self, policy: CompliancePolicy) -> float:
        """Check data protection compliance"""
        checks = {
            'encryption_at_rest': 95,    # 95% compliance
            'encryption_in_transit': 90, # 90% compliance
            'data_classification': 60,   # 60% compliance
            'backup_procedures': 85      # 85% compliance
        }
        
        return sum(checks.values()) / len(checks)
    
    async def _check_incident_response_compliance(self, policy: CompliancePolicy) -> float:
        """Check incident response compliance"""
        checks = {
            'monitoring_coverage': 80,   # 80% compliance
            'alert_configuration': 75,   # 75% compliance
            'response_procedures': 90,   # 90% compliance
            'log_retention': 95          # 95% compliance
        }
        
        return sum(checks.values()) / len(checks)
    
    def _generate_compliance_findings(self, policy: CompliancePolicy, score: float) -> List[str]:
        """Generate detailed compliance findings"""
        findings = []
        
        if score < 80:
            findings.append(f"Policy {policy.control_id} requires immediate attention")
        
        if policy.policy_type == PolicyType.ACCESS_CONTROL and score < 90:
            findings.append("Access control mechanisms need strengthening")
            findings.append("Consider implementing additional authentication factors")
        
        if policy.policy_type == PolicyType.DATA_PROTECTION and score < 85:
            findings.append("Data protection controls are insufficient")
            findings.append("Review encryption implementation and key management")
        
        if policy.policy_type == PolicyType.INCIDENT_RESPONSE and score < 85:
            findings.append("Incident response capabilities need improvement")
            findings.append("Enhance monitoring and alerting mechanisms")
        
        return findings
    
    async def detect_violations(self) -> List[ComplianceViolation]:
        """Detect compliance violations across all policies"""
        violations = []
        
        logger.info("Starting compliance violation detection...")
        
        for policy_id, policy in self.policies.items():
            status, findings = await self.check_policy_compliance(policy_id)
            
            if status in [ComplianceStatus.NON_COMPLIANT, ComplianceStatus.PARTIALLY_COMPLIANT]:
                for finding in findings:
                    violation = ComplianceViolation(
                        violation_id=f"VIO-{int(time.time())}-{len(violations)}",
                        policy_id=policy_id,
                        framework=policy.framework,
                        severity=self._determine_violation_severity(status, policy.risk_level),
                        title=f"Compliance violation: {policy.name}",
                        description=finding,
                        affected_systems=["system_infrastructure"],
                        detected_at=datetime.now(),
                        remediation_plan=self._generate_remediation_plan(policy, finding),
                        remediation_deadline=datetime.now() + timedelta(days=30),
                        business_impact="medium",
                        evidence={
                            'policy_id': policy_id,
                            'control_id': policy.control_id,
                            'framework': policy.framework.value,
                            'finding': finding
                        }
                    )
                    violations.append(violation)
                    self._save_violation_to_db(violation)
        
        self.violations.extend(violations)
        logger.info(f"Detected {len(violations)} compliance violations")
        
        return violations
    
    def _determine_violation_severity(self, status: ComplianceStatus, policy_risk: ViolationSeverity) -> ViolationSeverity:
        """Determine violation severity based on status and policy risk"""
        if status == ComplianceStatus.NON_COMPLIANT:
            if policy_risk == ViolationSeverity.CRITICAL:
                return ViolationSeverity.CRITICAL
            elif policy_risk == ViolationSeverity.HIGH:
                return ViolationSeverity.HIGH
            else:
                return ViolationSeverity.MEDIUM
        else:  # PARTIALLY_COMPLIANT
            if policy_risk == ViolationSeverity.CRITICAL:
                return ViolationSeverity.HIGH
            elif policy_risk == ViolationSeverity.HIGH:
                return ViolationSeverity.MEDIUM
            else:
                return ViolationSeverity.LOW
    
    def _generate_remediation_plan(self, policy: CompliancePolicy, finding: str) -> str:
        """Generate remediation plan for violation"""
        remediation_templates = {
            PolicyType.ACCESS_CONTROL: "Review and strengthen access control mechanisms. Implement additional authentication factors and role-based access controls.",
            PolicyType.DATA_PROTECTION: "Enhance data protection controls. Review encryption implementation and data handling procedures.",
            PolicyType.INCIDENT_RESPONSE: "Improve incident response capabilities. Enhance monitoring, alerting, and response procedures.",
            PolicyType.VULNERABILITY_MANAGEMENT: "Strengthen vulnerability management processes. Implement regular scanning and patching procedures.",
            PolicyType.CHANGE_MANAGEMENT: "Improve change management controls. Implement approval workflows and change tracking."
        }
        
        base_plan = remediation_templates.get(policy.policy_type, "Review and remediate identified compliance gaps.")
        return f"{base_plan} Specific action: {finding}"
    
    def _save_violation_to_db(self, violation: ComplianceViolation):
        """Save violation to database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO violations 
                (violation_id, policy_id, framework, severity, title, description,
                 affected_systems, detected_at, root_cause, remediation_plan,
                 remediation_deadline, status, assigned_to, evidence, 
                 business_impact, resolution_notes, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                violation.violation_id, violation.policy_id, violation.framework.value,
                violation.severity.value, violation.title, violation.description,
                json.dumps(violation.affected_systems), violation.detected_at.isoformat(),
                violation.root_cause, violation.remediation_plan,
                violation.remediation_deadline.isoformat() if violation.remediation_deadline else None,
                violation.status, violation.assigned_to, json.dumps(violation.evidence),
                violation.business_impact, violation.resolution_notes,
                violation.resolved_at.isoformat() if violation.resolved_at else None
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save violation {violation.violation_id}: {e}")
    
    def log_audit_event(self, event_type: AuditEventType, user_id: str, 
                       object_type: str, object_id: str, action: str, 
                       details: Dict[str, Any], source_system: str = "compliance_system"):
        """Log audit event"""
        audit_entry = AuditTrail(
            audit_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(),
            user_id=user_id,
            source_system=source_system,
            object_type=object_type,
            object_id=object_id,
            action=action,
            details=details,
            ip_address="127.0.0.1",  # Simulated
            session_id=str(uuid.uuid4())
        )
        
        # Generate integrity hash
        hash_data = f"{audit_entry.timestamp}{audit_entry.user_id}{audit_entry.object_id}{audit_entry.action}"
        audit_entry.integrity_hash = hashlib.sha256(hash_data.encode()).hexdigest()
        
        self.audit_trail.append(audit_entry)
        self._save_audit_to_db(audit_entry)
        
        logger.debug(f"Logged audit event: {event_type.value} by {user_id}")
    
    def _save_audit_to_db(self, audit_entry: AuditTrail):
        """Save audit entry to database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO audit_trail 
                (audit_id, event_type, timestamp, user_id, source_system,
                 object_type, object_id, action, details, ip_address,
                 user_agent, session_id, integrity_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                audit_entry.audit_id, audit_entry.event_type.value,
                audit_entry.timestamp.isoformat(), audit_entry.user_id,
                audit_entry.source_system, audit_entry.object_type,
                audit_entry.object_id, audit_entry.action,
                json.dumps(audit_entry.details), audit_entry.ip_address,
                audit_entry.user_agent, audit_entry.session_id,
                audit_entry.integrity_hash
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save audit entry {audit_entry.audit_id}: {e}")
    
    async def collect_evidence(self, policy_id: str, evidence_type: str, 
                              title: str, content: str) -> EvidenceItem:
        """Collect compliance evidence"""
        evidence = EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            policy_id=policy_id,
            control_id=self.policies[policy_id].control_id if policy_id in self.policies else "UNKNOWN",
            evidence_type=evidence_type,
            title=title,
            description=f"Evidence collected for policy {policy_id}",
            file_path=None,
            content=content,
            metadata={
                'collection_method': 'automated',
                'data_classification': 'confidential',
                'retention_period': '7_years'
            },
            collected_at=datetime.now(),
            collected_by="compliance_system",
            hash_value=hashlib.sha256(content.encode()).hexdigest()
        )
        
        self.evidence_store[evidence.evidence_id] = evidence
        self._save_evidence_to_db(evidence)
        
        # Log audit event
        self.log_audit_event(
            AuditEventType.EVIDENCE_COLLECTED,
            "system",
            "evidence",
            evidence.evidence_id,
            "evidence_collected",
            {
                'policy_id': policy_id,
                'evidence_type': evidence_type,
                'title': title
            }
        )
        
        logger.info(f"Collected evidence {evidence.evidence_id} for policy {policy_id}")
        return evidence
    
    def _save_evidence_to_db(self, evidence: EvidenceItem):
        """Save evidence to database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO evidence 
                (evidence_id, policy_id, control_id, evidence_type, title,
                 description, file_path, content, metadata, collected_at,
                 collected_by, hash_value, retention_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                evidence.evidence_id, evidence.policy_id, evidence.control_id,
                evidence.evidence_type, evidence.title, evidence.description,
                evidence.file_path, evidence.content, json.dumps(evidence.metadata),
                evidence.collected_at.isoformat(), evidence.collected_by,
                evidence.hash_value, evidence.retention_days
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save evidence {evidence.evidence_id}: {e}")
    
    async def generate_compliance_assessment(self, framework: ComplianceFramework) -> ComplianceAssessment:
        """Generate comprehensive compliance assessment"""
        
        # Filter policies for framework
        framework_policies = {
            pid: policy for pid, policy in self.policies.items()
            if policy.framework == framework
        }
        
        if not framework_policies:
            raise ValueError(f"No policies found for framework {framework.value}")
        
        compliant_count = 0
        non_compliant_count = 0
        findings = []
        recommendations = []
        
        # Check each policy
        for policy_id, policy in framework_policies.items():
            status, policy_findings = await self.check_policy_compliance(policy_id)
            
            if status == ComplianceStatus.COMPLIANT:
                compliant_count += 1
            else:
                non_compliant_count += 1
                findings.extend(policy_findings)
                
                # Generate recommendations
                if policy.risk_level in [ViolationSeverity.CRITICAL, ViolationSeverity.HIGH]:
                    recommendations.append(f"PRIORITY: Address {policy.control_id} - {policy.name}")
                else:
                    recommendations.append(f"Address {policy.control_id} - {policy.name}")
        
        # Calculate overall score
        total_controls = len(framework_policies)
        score = (compliant_count / total_controls * 100) if total_controls > 0 else 0
        
        # Determine overall status
        if score >= 95:
            overall_status = ComplianceStatus.COMPLIANT
        elif score >= 70:
            overall_status = ComplianceStatus.PARTIALLY_COMPLIANT
        else:
            overall_status = ComplianceStatus.NON_COMPLIANT
        
        assessment = ComplianceAssessment(
            assessment_id=f"ASSESS-{framework.value}-{int(time.time())}",
            framework=framework,
            scope="Full organizational assessment",
            assessed_by="compliance_automation_system",
            assessment_date=datetime.now(),
            status=overall_status,
            score=round(score, 2),
            total_controls=total_controls,
            compliant_controls=compliant_count,
            non_compliant_controls=non_compliant_count,
            findings=findings,
            recommendations=recommendations[:10],  # Top 10 recommendations
            next_assessment_date=datetime.now() + timedelta(days=90)
        )
        
        # Log assessment
        self.log_audit_event(
            AuditEventType.ASSESSMENT_COMPLETED,
            "system",
            "assessment",
            assessment.assessment_id,
            "compliance_assessment_generated",
            {
                'framework': framework.value,
                'score': score,
                'status': overall_status.value,
                'total_controls': total_controls
            }
        )
        
        logger.info(f"Generated compliance assessment {assessment.assessment_id} for {framework.value}: {score}%")
        
        return assessment
    
    def generate_compliance_report(self, assessment: ComplianceAssessment) -> str:
        """Generate detailed compliance report"""
        
        report_lines = [
            f"COMPLIANCE ASSESSMENT REPORT",
            f"=" * 50,
            f"Framework: {assessment.framework.value.upper()}",
            f"Assessment ID: {assessment.assessment_id}",
            f"Assessed By: {assessment.assessed_by}",
            f"Assessment Date: {assessment.assessment_date.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Next Assessment: {assessment.next_assessment_date.strftime('%Y-%m-%d')}",
            f"",
            f"EXECUTIVE SUMMARY",
            f"-" * 20,
            f"Overall Status: {assessment.status.value.upper()}",
            f"Compliance Score: {assessment.score}%",
            f"Total Controls: {assessment.total_controls}",
            f"Compliant: {assessment.compliant_controls}",
            f"Non-Compliant: {assessment.non_compliant_controls}",
            f"",
            f"FINDINGS ({len(assessment.findings)})",
            f"-" * 20
        ]
        
        for i, finding in enumerate(assessment.findings, 1):
            report_lines.append(f"{i}. {finding}")
        
        if not assessment.findings:
            report_lines.append("No compliance issues identified.")
        
        report_lines.extend([
            f"",
            f"RECOMMENDATIONS ({len(assessment.recommendations)})",
            f"-" * 20
        ])
        
        for i, rec in enumerate(assessment.recommendations, 1):
            report_lines.append(f"{i}. {rec}")
        
        if not assessment.recommendations:
            report_lines.append("No recommendations at this time.")
        
        report_lines.extend([
            f"",
            f"AUDIT TRAIL SUMMARY",
            f"-" * 20,
            f"Total Audit Events: {len(self.audit_trail)}",
            f"Evidence Items Collected: {len(self.evidence_store)}",
            f"Violations Detected: {len(self.violations)}",
            f"",
            f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Report Hash: {hashlib.sha256(''.join(report_lines).encode()).hexdigest()[:16]}"
        ])
        
        return '\n'.join(report_lines)
    
    def get_compliance_dashboard_data(self) -> Dict[str, Any]:
        """Get compliance dashboard data"""
        
        # Framework compliance scores
        framework_scores = {}
        for framework in ComplianceFramework:
            framework_policies = [p for p in self.policies.values() if p.framework == framework]
            if framework_policies:
                # Simulate scores for demonstration
                scores = {
                    ComplianceFramework.SOC2_TYPE2: 75.0,
                    ComplianceFramework.GDPR: 82.5,
                    ComplianceFramework.HIPAA: 68.0,
                    ComplianceFramework.PCI_DSS: 0.0,
                    ComplianceFramework.ISO_27001: 0.0
                }
                framework_scores[framework.value] = scores.get(framework, 0.0)
        
        # Violation distribution
        violation_by_severity = Counter(v.severity for v in self.violations)
        violation_by_framework = Counter(v.framework for v in self.violations)
        
        # Recent activity
        recent_violations = sorted(self.violations, key=lambda v: v.detected_at, reverse=True)[:5]
        recent_audits = sorted(self.audit_trail, key=lambda a: a.timestamp, reverse=True)[:10]
        
        # Compliance trends (simulated)
        compliance_trend = [
            {'date': '2025-09-01', 'score': 65.0},
            {'date': '2025-09-07', 'score': 70.0},
            {'date': '2025-09-14', 'score': 75.0}
        ]
        
        return {
            'summary': {
                'total_policies': len(self.policies),
                'total_violations': len(self.violations),
                'total_evidence_items': len(self.evidence_store),
                'total_audit_events': len(self.audit_trail),
                'average_compliance_score': sum(framework_scores.values()) / len(framework_scores) if framework_scores else 0
            },
            'framework_scores': framework_scores,
            'violations': {
                'by_severity': {sev.value: count for sev, count in violation_by_severity.items()},
                'by_framework': {fw.value: count for fw, count in violation_by_framework.items()},
                'recent': [
                    {
                        'id': v.violation_id,
                        'title': v.title,
                        'severity': v.severity.value,
                        'framework': v.framework.value,
                        'detected_at': v.detected_at.isoformat()
                    }
                    for v in recent_violations
                ]
            },
            'audit_activity': [
                {
                    'event_type': a.event_type.value,
                    'user_id': a.user_id,
                    'action': a.action,
                    'timestamp': a.timestamp.isoformat()
                }
                for a in recent_audits
            ],
            'compliance_trend': compliance_trend,
            'risk_distribution': {
                'critical': len([v for v in self.violations if v.severity == ViolationSeverity.CRITICAL]),
                'high': len([v for v in self.violations if v.severity == ViolationSeverity.HIGH]),
                'medium': len([v for v in self.violations if v.severity == ViolationSeverity.MEDIUM]),
                'low': len([v for v in self.violations if v.severity == ViolationSeverity.LOW])
            }
        }

async def demonstrate_compliance_automation():
    """Demonstrate the compliance automation framework"""
    print("AIOps Compliance Automation Framework Demo")
    print("=" * 55)
    
    # Initialize compliance engine
    policy_engine = PolicyEngine()
    
    print("🔧 Compliance automation system initialized with default policies\n")
    
    # Show loaded policies
    print(f"📋 Loaded Policies Summary:")
    framework_counts = Counter(policy.framework for policy in policy_engine.policies.values())
    for framework, count in framework_counts.items():
        print(f"  {framework.value.upper()}: {count} policies")
    
    print(f"  Total Policies: {len(policy_engine.policies)}")
    
    # Detect violations
    print(f"\n🔍 Scanning for compliance violations...")
    violations = await policy_engine.detect_violations()
    
    print(f"  Found {len(violations)} compliance violations")
    
    # Show violation summary
    if violations:
        print(f"\n⚠️ Violation Summary:")
        severity_counts = Counter(v.severity for v in violations)
        for severity, count in severity_counts.items():
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity.value, "ℹ️")
            print(f"  {icon} {severity.value.title()}: {count}")
        
        print(f"\n📝 Recent Violations:")
        for violation in violations[:5]:
            print(f"  • [{violation.severity.value.upper()}] {violation.title}")
            print(f"    Framework: {violation.framework.value.upper()}")
            print(f"    Remediation: {violation.remediation_plan[:80]}...")
    
    # Collect evidence
    print(f"\n📁 Collecting compliance evidence...")
    evidence_items = []
    
    for policy_id in list(policy_engine.policies.keys())[:3]:  # Collect for first 3 policies
        evidence = await policy_engine.collect_evidence(
            policy_id=policy_id,
            evidence_type="configuration_snapshot",
            title=f"System configuration for {policy_id}",
            content=f"Configuration data for policy {policy_id} - timestamp: {datetime.now()}"
        )
        evidence_items.append(evidence)
    
    print(f"  Collected {len(evidence_items)} evidence items")
    
    # Generate assessments for each framework
    print(f"\n📊 Generating compliance assessments...")
    assessments = {}
    
    frameworks_to_assess = [ComplianceFramework.SOC2_TYPE2, ComplianceFramework.GDPR, ComplianceFramework.HIPAA]
    
    for framework in frameworks_to_assess:
        try:
            assessment = await policy_engine.generate_compliance_assessment(framework)
            assessments[framework] = assessment
            
            status_icon = {"compliant": "✅", "partially_compliant": "⚠️", "non_compliant": "❌"}.get(assessment.status.value, "❓")
            print(f"  {status_icon} {framework.value.upper()}: {assessment.score}% ({assessment.status.value})")
            
        except Exception as e:
            print(f"  ❌ {framework.value.upper()}: Error - {e}")
    
    # Show detailed assessment for SOC 2
    if ComplianceFramework.SOC2_TYPE2 in assessments:
        soc2_assessment = assessments[ComplianceFramework.SOC2_TYPE2]
        print(f"\n📋 SOC 2 Type II Assessment Details:")
        print(f"  Total Controls: {soc2_assessment.total_controls}")
        print(f"  Compliant: {soc2_assessment.compliant_controls}")
        print(f"  Non-Compliant: {soc2_assessment.non_compliant_controls}")
        print(f"  Next Assessment: {soc2_assessment.next_assessment_date.strftime('%Y-%m-%d')}")
        
        if soc2_assessment.findings:
            print(f"  Key Findings:")
            for finding in soc2_assessment.findings[:3]:
                print(f"    • {finding}")
        
        if soc2_assessment.recommendations:
            print(f"  Top Recommendations:")
            for rec in soc2_assessment.recommendations[:3]:
                print(f"    • {rec}")
    
    # Generate compliance report
    if ComplianceFramework.SOC2_TYPE2 in assessments:
        print(f"\n📄 Generating compliance report...")
        report = policy_engine.generate_compliance_report(assessments[ComplianceFramework.SOC2_TYPE2])
        
        # Show first part of report
        report_lines = report.split('\n')
        print("  Report Preview:")
        for line in report_lines[:15]:
            print(f"    {line}")
        print(f"    ... ({len(report_lines) - 15} more lines)")
    
    # Show audit trail
    print(f"\n📋 Audit Trail Summary:")
    audit_events = Counter(entry.event_type for entry in policy_engine.audit_trail)
    for event_type, count in audit_events.items():
        print(f"  {event_type.value}: {count}")
    
    print(f"  Total Audit Events: {len(policy_engine.audit_trail)}")
    
    # Get dashboard data
    print(f"\n📊 Compliance Dashboard Data:")
    dashboard_data = policy_engine.get_compliance_dashboard_data()
    
    print(f"  Summary:")
    summary = dashboard_data['summary']
    print(f"    Total Policies: {summary['total_policies']}")
    print(f"    Total Violations: {summary['total_violations']}")
    print(f"    Evidence Items: {summary['total_evidence_items']}")
    print(f"    Audit Events: {summary['total_audit_events']}")
    print(f"    Avg Compliance Score: {summary['average_compliance_score']:.1f}%")
    
    print(f"\n  Framework Scores:")
    for framework, score in dashboard_data['framework_scores'].items():
        if score > 0:
            status_icon = "✅" if score >= 90 else "⚠️" if score >= 70 else "❌"
            print(f"    {status_icon} {framework.upper()}: {score}%")
    
    print(f"\n  Risk Distribution:")
    risk_dist = dashboard_data['risk_distribution']
    total_risk_items = sum(risk_dist.values())
    if total_risk_items > 0:
        for risk_level, count in risk_dist.items():
            percentage = (count / total_risk_items) * 100
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(risk_level, "ℹ️")
            print(f"    {icon} {risk_level.title()}: {count} ({percentage:.1f}%)")
    
    print(f"\n🔧 System Capabilities:")
    print(f"  • Multi-framework compliance automation (SOC2, GDPR, HIPAA, PCI DSS)")
    print(f"  • Real-time violation detection and remediation planning")
    print(f"  • Comprehensive audit trail with integrity protection")
    print(f"  • Automated evidence collection and management")
    print(f"  • Risk-based compliance scoring and reporting")
    print(f"  • Continuous compliance monitoring and alerting")
    
    print(f"\n✅ Compliance automation demonstration completed!")
    print(f"🎯 Key Benefits:")
    print(f"  • Automated compliance monitoring and reporting")
    print(f"  • Risk-based violation detection and prioritization")
    print(f"  • Comprehensive audit trails for regulatory requirements")
    print(f"  • Evidence-based compliance assessments")
    print(f"  • Continuous monitoring and improvement recommendations")

if __name__ == "__main__":
    asyncio.run(demonstrate_compliance_automation())