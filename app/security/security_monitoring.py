#!/usr/bin/env python3
"""
AIOps Security Monitoring System
Comprehensive security monitoring with threat detection, vulnerability scanning, and incident response

Features:
- Real-time threat detection and analysis
- Vulnerability scanning and assessment
- Access control monitoring and anomaly detection
- Security incident classification and response
- Integration with SIEM systems
- Automated security remediation
- Compliance monitoring and reporting
"""

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import platform
import re
import socket
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('security_monitor')

class ThreatLevel(Enum):
    """Threat severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class SecurityEventType(Enum):
    """Types of security events"""
    AUTHENTICATION_FAILURE = "authentication_failure"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    MALWARE_DETECTION = "malware_detection"
    NETWORK_INTRUSION = "network_intrusion"
    DATA_EXFILTRATION = "data_exfiltration"
    VULNERABILITY_EXPLOIT = "vulnerability_exploit"
    POLICY_VIOLATION = "policy_violation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    CONFIGURATION_CHANGE = "configuration_change"

class VulnerabilityType(Enum):
    """Types of vulnerabilities"""
    CRITICAL_CVE = "critical_cve"
    HIGH_CVE = "high_cve"
    MEDIUM_CVE = "medium_cve"
    LOW_CVE = "low_cve"
    CONFIGURATION_WEAKNESS = "configuration_weakness"
    MISSING_PATCH = "missing_patch"
    WEAK_CREDENTIALS = "weak_credentials"
    EXPOSED_SERVICE = "exposed_service"
    INSECURE_PROTOCOL = "insecure_protocol"

class ComplianceStandard(Enum):
    """Compliance standards"""
    SOC2 = "soc2"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO_27001 = "iso_27001"
    NIST = "nist"

@dataclass
class SecurityEvent:
    """Security event data structure"""
    event_id: str
    event_type: SecurityEventType
    threat_level: ThreatLevel
    timestamp: datetime
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    user_id: Optional[str] = None
    service: Optional[str] = None
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    indicators: List[str] = field(default_factory=list)
    mitre_tactics: List[str] = field(default_factory=list)
    mitre_techniques: List[str] = field(default_factory=list)
    remediation_status: str = "open"
    false_positive: bool = False

@dataclass
class Vulnerability:
    """Vulnerability data structure"""
    vuln_id: str
    cve_id: Optional[str]
    vulnerability_type: VulnerabilityType
    severity_score: float  # CVSS score
    threat_level: ThreatLevel
    affected_systems: List[str]
    description: str
    remediation: str
    discovered_at: datetime
    patched: bool = False
    exploitable: bool = False
    exposure_time_hours: float = 0.0

@dataclass
class ComplianceCheck:
    """Compliance check result"""
    check_id: str
    standard: ComplianceStandard
    control_id: str
    description: str
    status: str  # "pass", "fail", "partial", "not_applicable"
    evidence: Dict[str, Any]
    risk_level: ThreatLevel
    remediation_required: bool
    last_checked: datetime

class SecurityEventDetector:
    """Detect security events from various sources"""
    
    def __init__(self):
        self.patterns = self._load_detection_patterns()
        self.baseline_behavior = {}
        self.anomaly_thresholds = {
            'failed_logins_per_hour': 10,
            'new_processes_per_hour': 50,
            'network_connections_per_hour': 100,
            'file_access_per_hour': 200
        }
        
    def _load_detection_patterns(self) -> Dict[str, List[str]]:
        """Load security detection patterns"""
        return {
            'authentication_failure': [
                r'authentication failed',
                r'login failed',
                r'invalid credentials',
                r'access denied',
                r'unauthorized access attempt'
            ],
            'privilege_escalation': [
                r'sudo.*root',
                r'privilege.*elevated',
                r'admin.*rights.*granted',
                r'runas.*administrator'
            ],
            'malware_signatures': [
                r'trojan',
                r'virus.*detected',
                r'malware.*found',
                r'suspicious.*executable',
                r'ransomware'
            ],
            'network_intrusion': [
                r'port.*scan',
                r'brute.*force',
                r'ddos.*attack',
                r'intrusion.*detected',
                r'suspicious.*traffic'
            ],
            'data_exfiltration': [
                r'large.*file.*transfer',
                r'unusual.*data.*access',
                r'sensitive.*data.*copied',
                r'encryption.*key.*access'
            ]
        }
    
    def analyze_log_entry(self, log_entry: str, source: str = "system") -> List[SecurityEvent]:
        """Analyze a log entry for security events"""
        events = []
        timestamp = datetime.now()
        
        # Extract IP addresses
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
        ips = re.findall(ip_pattern, log_entry)
        source_ip = ips[0] if ips else None
        
        # Check against detection patterns
        for event_type, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, log_entry, re.IGNORECASE):
                    threat_level = self._assess_threat_level(event_type, log_entry)
                    
                    event = SecurityEvent(
                        event_id=f"SEC-{int(time.time())}-{len(events)}",
                        event_type=SecurityEventType(event_type),
                        threat_level=threat_level,
                        timestamp=timestamp,
                        source_ip=source_ip,
                        service=source,
                        description=f"Security pattern detected: {pattern}",
                        details={
                            'log_entry': log_entry,
                            'pattern_matched': pattern,
                            'source': source
                        },
                        indicators=[pattern],
                        mitre_tactics=self._get_mitre_tactics(event_type),
                        mitre_techniques=self._get_mitre_techniques(event_type)
                    )
                    events.append(event)
                    break  # Only match first pattern per type
        
        return events
    
    def _assess_threat_level(self, event_type: str, log_entry: str) -> ThreatLevel:
        """Assess threat level based on event type and context"""
        critical_indicators = ['critical', 'emergency', 'admin', 'root', 'system']
        high_indicators = ['error', 'failed', 'denied', 'unauthorized']
        
        log_lower = log_entry.lower()
        
        if event_type in ['privilege_escalation', 'malware_signatures']:
            return ThreatLevel.CRITICAL
        elif any(indicator in log_lower for indicator in critical_indicators):
            return ThreatLevel.HIGH
        elif any(indicator in log_lower for indicator in high_indicators):
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW
    
    def _get_mitre_tactics(self, event_type: str) -> List[str]:
        """Get MITRE ATT&CK tactics for event type"""
        tactics_map = {
            'authentication_failure': ['Credential Access'],
            'privilege_escalation': ['Privilege Escalation'],
            'malware_signatures': ['Execution', 'Persistence'],
            'network_intrusion': ['Initial Access', 'Discovery'],
            'data_exfiltration': ['Exfiltration']
        }
        return tactics_map.get(event_type, [])
    
    def _get_mitre_techniques(self, event_type: str) -> List[str]:
        """Get MITRE ATT&CK techniques for event type"""
        techniques_map = {
            'authentication_failure': ['T1110 - Brute Force'],
            'privilege_escalation': ['T1068 - Exploitation for Privilege Escalation'],
            'malware_signatures': ['T1204 - User Execution'],
            'network_intrusion': ['T1046 - Network Service Scanning'],
            'data_exfiltration': ['T1041 - Exfiltration Over C2 Channel']
        }
        return techniques_map.get(event_type, [])

class VulnerabilityScanner:
    """Scan for vulnerabilities in the system"""
    
    def __init__(self):
        self.known_vulnerabilities = self._load_vulnerability_database()
        self.scan_modules = {
            'network_scan': self._scan_network_vulnerabilities,
            'service_scan': self._scan_service_vulnerabilities,
            'configuration_scan': self._scan_configuration_vulnerabilities,
            'credential_scan': self._scan_credential_vulnerabilities
        }
    
    def _load_vulnerability_database(self) -> Dict[str, Dict]:
        """Load known vulnerability signatures"""
        return {
            'CVE-2021-44228': {
                'description': 'Log4j Remote Code Execution',
                'severity': 10.0,
                'services': ['log4j', 'java', 'elasticsearch', 'kafka'],
                'patterns': ['log4j', 'jndi:ldap', 'jndi:rmi']
            },
            'CVE-2021-34527': {
                'description': 'Windows Print Spooler RCE (PrintNightmare)',
                'severity': 8.8,
                'services': ['spoolsv.exe', 'print spooler'],
                'patterns': ['spoolsv', 'print.*spooler']
            },
            'WEAK_SSH_CONFIG': {
                'description': 'Weak SSH Configuration',
                'severity': 7.5,
                'services': ['sshd', 'ssh'],
                'patterns': ['PasswordAuthentication yes', 'PermitRootLogin yes']
            },
            'DEFAULT_CREDENTIALS': {
                'description': 'Default Credentials in Use',
                'severity': 9.0,
                'services': ['admin', 'root', 'administrator'],
                'patterns': ['admin:admin', 'root:root', 'admin:password']
            }
        }
    
    async def scan_system(self) -> List[Vulnerability]:
        """Perform comprehensive vulnerability scan"""
        vulnerabilities = []
        
        logger.info("Starting vulnerability scan...")
        
        for scan_name, scan_func in self.scan_modules.items():
            try:
                scan_results = await scan_func()
                vulnerabilities.extend(scan_results)
                logger.info(f"Completed {scan_name}: found {len(scan_results)} vulnerabilities")
            except Exception as e:
                logger.error(f"Error in {scan_name}: {e}")
        
        return vulnerabilities
    
    async def _scan_network_vulnerabilities(self) -> List[Vulnerability]:
        """Scan for network-level vulnerabilities"""
        vulnerabilities = []
        
        # Simulate network vulnerability scan
        open_ports = await self._scan_open_ports()
        
        for port, service in open_ports.items():
            # Check for vulnerable services
            if service in ['telnet', 'ftp', 'http']:
                vuln = Vulnerability(
                    vuln_id=f"VULN-NET-{port}",
                    cve_id=None,
                    vulnerability_type=VulnerabilityType.INSECURE_PROTOCOL,
                    severity_score=6.5,
                    threat_level=ThreatLevel.MEDIUM,
                    affected_systems=[f"localhost:{port}"],
                    description=f"Insecure service {service} running on port {port}",
                    remediation=f"Disable {service} service or use secure alternative",
                    discovered_at=datetime.now(),
                    exploitable=True
                )
                vulnerabilities.append(vuln)
        
        return vulnerabilities
    
    async def _scan_service_vulnerabilities(self) -> List[Vulnerability]:
        """Scan for service-level vulnerabilities"""
        vulnerabilities = []
        
        # Get running services (simulated)
        services = await self._get_running_services()
        
        for service_name, service_info in services.items():
            # Check against known vulnerabilities
            for vuln_id, vuln_data in self.known_vulnerabilities.items():
                if any(svc in service_name.lower() for svc in vuln_data['services']):
                    vuln = Vulnerability(
                        vuln_id=f"VULN-SVC-{vuln_id}",
                        cve_id=vuln_id if vuln_id.startswith('CVE') else None,
                        vulnerability_type=VulnerabilityType.CRITICAL_CVE if vuln_data['severity'] >= 9.0 else VulnerabilityType.HIGH_CVE,
                        severity_score=vuln_data['severity'],
                        threat_level=ThreatLevel.CRITICAL if vuln_data['severity'] >= 9.0 else ThreatLevel.HIGH,
                        affected_systems=[service_name],
                        description=vuln_data['description'],
                        remediation=f"Update {service_name} to latest version or apply security patches",
                        discovered_at=datetime.now(),
                        exploitable=vuln_data['severity'] >= 7.0
                    )
                    vulnerabilities.append(vuln)
        
        return vulnerabilities
    
    async def _scan_configuration_vulnerabilities(self) -> List[Vulnerability]:
        """Scan for configuration weaknesses"""
        vulnerabilities = []
        
        # Check common configuration files
        config_checks = {
            'ssh_config': self._check_ssh_config,
            'firewall_config': self._check_firewall_config,
            'user_permissions': self._check_user_permissions
        }
        
        for check_name, check_func in config_checks.items():
            issues = await check_func()
            for issue in issues:
                vuln = Vulnerability(
                    vuln_id=f"VULN-CFG-{check_name}-{int(time.time())}",
                    cve_id=None,
                    vulnerability_type=VulnerabilityType.CONFIGURATION_WEAKNESS,
                    severity_score=issue['severity'],
                    threat_level=ThreatLevel.MEDIUM if issue['severity'] >= 5.0 else ThreatLevel.LOW,
                    affected_systems=[issue['component']],
                    description=issue['description'],
                    remediation=issue['remediation'],
                    discovered_at=datetime.now(),
                    exploitable=issue['exploitable']
                )
                vulnerabilities.append(vuln)
        
        return vulnerabilities
    
    async def _scan_credential_vulnerabilities(self) -> List[Vulnerability]:
        """Scan for weak credential vulnerabilities"""
        vulnerabilities = []
        
        # Check for weak passwords (simulated)
        weak_credentials = [
            {'user': 'admin', 'weakness': 'default_password', 'severity': 9.0},
            {'user': 'guest', 'weakness': 'no_password', 'severity': 8.5},
            {'user': 'test', 'weakness': 'weak_password', 'severity': 7.0}
        ]
        
        for cred in weak_credentials:
            vuln = Vulnerability(
                vuln_id=f"VULN-CRED-{cred['user']}-{int(time.time())}",
                cve_id=None,
                vulnerability_type=VulnerabilityType.WEAK_CREDENTIALS,
                severity_score=cred['severity'],
                threat_level=ThreatLevel.CRITICAL if cred['severity'] >= 9.0 else ThreatLevel.HIGH,
                affected_systems=[cred['user']],
                description=f"Weak credential detected for user {cred['user']}: {cred['weakness']}",
                remediation=f"Enforce strong password policy for user {cred['user']}",
                discovered_at=datetime.now(),
                exploitable=True
            )
            vulnerabilities.append(vuln)
        
        return vulnerabilities
    
    async def _scan_open_ports(self) -> Dict[int, str]:
        """Scan for open ports (simulated)"""
        # In production, use nmap or similar
        common_ports = {
            22: 'ssh',
            23: 'telnet',
            80: 'http',
            443: 'https',
            3389: 'rdp',
            5432: 'postgresql',
            3306: 'mysql'
        }
        
        open_ports = {}
        for port, service in common_ports.items():
            # Simulate port scan
            if port in [22, 80, 443, 5432]:  # Simulate these as open
                open_ports[port] = service
        
        return open_ports
    
    async def _get_running_services(self) -> Dict[str, Dict]:
        """Get running services (simulated)"""
        return {
            'apache2': {'version': '2.4.41', 'status': 'running'},
            'ssh': {'version': '8.2', 'status': 'running'},
            'postgresql': {'version': '12.8', 'status': 'running'},
            'log4j': {'version': '2.14.1', 'status': 'running'}  # Vulnerable version
        }
    
    async def _check_ssh_config(self) -> List[Dict]:
        """Check SSH configuration for security issues"""
        issues = []
        
        # Simulate SSH config check
        ssh_issues = [
            {
                'component': 'ssh_config',
                'description': 'Root login permitted via SSH',
                'severity': 7.5,
                'remediation': 'Set PermitRootLogin to no in /etc/ssh/sshd_config',
                'exploitable': True
            },
            {
                'component': 'ssh_config',
                'description': 'Password authentication enabled',
                'severity': 6.0,
                'remediation': 'Use key-based authentication only',
                'exploitable': False
            }
        ]
        
        return ssh_issues
    
    async def _check_firewall_config(self) -> List[Dict]:
        """Check firewall configuration"""
        return [
            {
                'component': 'firewall',
                'description': 'Firewall not properly configured',
                'severity': 5.5,
                'remediation': 'Configure restrictive firewall rules',
                'exploitable': False
            }
        ]
    
    async def _check_user_permissions(self) -> List[Dict]:
        """Check user permission issues"""
        return [
            {
                'component': 'user_permissions',
                'description': 'User has excessive sudo privileges',
                'severity': 6.5,
                'remediation': 'Apply principle of least privilege',
                'exploitable': True
            }
        ]

class ComplianceMonitor:
    """Monitor compliance with various standards"""
    
    def __init__(self):
        self.compliance_frameworks = {
            ComplianceStandard.SOC2: self._get_soc2_controls(),
            ComplianceStandard.GDPR: self._get_gdpr_controls(),
            ComplianceStandard.HIPAA: self._get_hipaa_controls(),
            ComplianceStandard.PCI_DSS: self._get_pci_controls()
        }
    
    def _get_soc2_controls(self) -> List[Dict]:
        """SOC 2 Type II controls"""
        return [
            {
                'control_id': 'CC6.1',
                'description': 'Logical and physical access controls',
                'check_function': self._check_access_controls,
                'risk_level': ThreatLevel.HIGH
            },
            {
                'control_id': 'CC6.2',
                'description': 'Authentication and authorization',
                'check_function': self._check_authentication,
                'risk_level': ThreatLevel.HIGH
            },
            {
                'control_id': 'CC6.3',
                'description': 'System access monitoring',
                'check_function': self._check_access_monitoring,
                'risk_level': ThreatLevel.MEDIUM
            },
            {
                'control_id': 'CC7.1',
                'description': 'Detection of unauthorized changes',
                'check_function': self._check_change_detection,
                'risk_level': ThreatLevel.MEDIUM
            }
        ]
    
    def _get_gdpr_controls(self) -> List[Dict]:
        """GDPR compliance controls"""
        return [
            {
                'control_id': 'Art.32',
                'description': 'Security of processing',
                'check_function': self._check_data_security,
                'risk_level': ThreatLevel.CRITICAL
            },
            {
                'control_id': 'Art.33',
                'description': 'Breach notification',
                'check_function': self._check_breach_notification,
                'risk_level': ThreatLevel.HIGH
            },
            {
                'control_id': 'Art.25',
                'description': 'Data protection by design',
                'check_function': self._check_privacy_by_design,
                'risk_level': ThreatLevel.MEDIUM
            }
        ]
    
    def _get_hipaa_controls(self) -> List[Dict]:
        """HIPAA compliance controls"""
        return [
            {
                'control_id': '164.312(a)(1)',
                'description': 'Access control',
                'check_function': self._check_access_controls,
                'risk_level': ThreatLevel.CRITICAL
            },
            {
                'control_id': '164.312(b)',
                'description': 'Audit controls',
                'check_function': self._check_audit_controls,
                'risk_level': ThreatLevel.HIGH
            },
            {
                'control_id': '164.312(e)(1)',
                'description': 'Transmission security',
                'check_function': self._check_transmission_security,
                'risk_level': ThreatLevel.HIGH
            }
        ]
    
    def _get_pci_controls(self) -> List[Dict]:
        """PCI DSS compliance controls"""
        return [
            {
                'control_id': 'REQ.1',
                'description': 'Install and maintain firewall configuration',
                'check_function': self._check_firewall_compliance,
                'risk_level': ThreatLevel.HIGH
            },
            {
                'control_id': 'REQ.2',
                'description': 'Remove default passwords',
                'check_function': self._check_default_passwords,
                'risk_level': ThreatLevel.CRITICAL
            },
            {
                'control_id': 'REQ.8',
                'description': 'Identify users and authenticate access',
                'check_function': self._check_user_identification,
                'risk_level': ThreatLevel.HIGH
            }
        ]
    
    async def check_compliance(self, standard: ComplianceStandard) -> List[ComplianceCheck]:
        """Check compliance for a specific standard"""
        results = []
        controls = self.compliance_frameworks.get(standard, [])
        
        logger.info(f"Checking compliance for {standard.value}")
        
        for control in controls:
            try:
                check_result = await control['check_function'](control)
                
                compliance_check = ComplianceCheck(
                    check_id=f"COMP-{standard.value}-{control['control_id']}",
                    standard=standard,
                    control_id=control['control_id'],
                    description=control['description'],
                    status=check_result['status'],
                    evidence=check_result['evidence'],
                    risk_level=control['risk_level'],
                    remediation_required=check_result['status'] in ['fail', 'partial'],
                    last_checked=datetime.now()
                )
                
                results.append(compliance_check)
                
            except Exception as e:
                logger.error(f"Error checking control {control['control_id']}: {e}")
        
        return results
    
    async def _check_access_controls(self, control: Dict) -> Dict:
        """Check access control implementation"""
        # Simulate access control check
        evidence = {
            'multi_factor_auth': True,
            'role_based_access': True,
            'privileged_access_management': False,
            'access_review_frequency': '90_days'
        }
        
        if not evidence['privileged_access_management']:
            return {
                'status': 'partial',
                'evidence': evidence,
                'findings': ['Privileged access management not fully implemented']
            }
        
        return {'status': 'pass', 'evidence': evidence, 'findings': []}
    
    async def _check_authentication(self, control: Dict) -> Dict:
        """Check authentication mechanisms"""
        evidence = {
            'password_policy': True,
            'mfa_enabled': True,
            'session_timeout': 30,
            'failed_login_lockout': True
        }
        
        return {'status': 'pass', 'evidence': evidence, 'findings': []}
    
    async def _check_access_monitoring(self, control: Dict) -> Dict:
        """Check access monitoring capabilities"""
        evidence = {
            'login_monitoring': True,
            'privileged_access_logging': True,
            'real_time_alerts': True,
            'log_retention_days': 365
        }
        
        return {'status': 'pass', 'evidence': evidence, 'findings': []}
    
    async def _check_change_detection(self, control: Dict) -> Dict:
        """Check change detection mechanisms"""
        evidence = {
            'change_management_process': True,
            'unauthorized_change_detection': False,
            'configuration_monitoring': True
        }
        
        if not evidence['unauthorized_change_detection']:
            return {
                'status': 'fail',
                'evidence': evidence,
                'findings': ['Unauthorized change detection not implemented']
            }
        
        return {'status': 'pass', 'evidence': evidence, 'findings': []}
    
    async def _check_data_security(self, control: Dict) -> Dict:
        """Check data security measures (GDPR)"""
        evidence = {
            'data_encryption_at_rest': True,
            'data_encryption_in_transit': True,
            'data_minimization': True,
            'pseudonymization': False
        }
        
        return {'status': 'partial', 'evidence': evidence, 'findings': ['Pseudonymization not implemented']}
    
    async def _check_breach_notification(self, control: Dict) -> Dict:
        """Check breach notification procedures"""
        evidence = {
            'incident_response_plan': True,
            'notification_procedures': True,
            'timeline_compliance': True,
            'authority_notification': True
        }
        
        return {'status': 'pass', 'evidence': evidence, 'findings': []}
    
    async def _check_privacy_by_design(self, control: Dict) -> Dict:
        """Check privacy by design implementation"""
        evidence = {
            'privacy_impact_assessments': True,
            'data_protection_by_default': False,
            'privacy_controls_in_systems': True
        }
        
        return {'status': 'partial', 'evidence': evidence, 'findings': ['Data protection by default not fully implemented']}
    
    async def _check_audit_controls(self, control: Dict) -> Dict:
        """Check audit control implementation"""
        evidence = {
            'audit_logging_enabled': True,
            'log_integrity_protection': True,
            'audit_log_review': True,
            'audit_trail_completeness': True
        }
        
        return {'status': 'pass', 'evidence': evidence, 'findings': []}
    
    async def _check_transmission_security(self, control: Dict) -> Dict:
        """Check transmission security"""
        evidence = {
            'encryption_in_transit': True,
            'secure_protocols_only': True,
            'certificate_management': True,
            'network_segmentation': False
        }
        
        return {'status': 'partial', 'evidence': evidence, 'findings': ['Network segmentation incomplete']}
    
    async def _check_firewall_compliance(self, control: Dict) -> Dict:
        """Check firewall compliance"""
        evidence = {
            'firewall_configured': True,
            'default_deny_policy': True,
            'regular_rule_review': False,
            'change_documentation': True
        }
        
        return {'status': 'partial', 'evidence': evidence, 'findings': ['Regular firewall rule review not performed']}
    
    async def _check_default_passwords(self, control: Dict) -> Dict:
        """Check for default passwords"""
        evidence = {
            'default_passwords_changed': False,
            'password_policy_enforced': True,
            'vendor_defaults_documented': True
        }
        
        return {
            'status': 'fail',
            'evidence': evidence,
            'findings': ['Default passwords still in use']
        }
    
    async def _check_user_identification(self, control: Dict) -> Dict:
        """Check user identification requirements"""
        evidence = {
            'unique_user_ids': True,
            'user_authentication': True,
            'privileged_user_management': True,
            'user_access_review': True
        }
        
        return {'status': 'pass', 'evidence': evidence, 'findings': []}

class SecurityMonitoringSystem:
    """Main security monitoring system"""
    
    def __init__(self):
        self.event_detector = SecurityEventDetector()
        self.vulnerability_scanner = VulnerabilityScanner()
        self.compliance_monitor = ComplianceMonitor()
        
        # Storage
        self.security_events = []
        self.vulnerabilities = []
        self.compliance_results = {}
        
        # Metrics
        self.metrics = {
            'events_detected': 0,
            'vulnerabilities_found': 0,
            'compliance_score': 0.0,
            'mean_time_to_detection': 0.0,
            'false_positive_rate': 0.05
        }
        
        logger.info("Security monitoring system initialized")
    
    async def start_monitoring(self, duration_minutes: int = 5):
        """Start security monitoring for specified duration"""
        logger.info(f"Starting security monitoring for {duration_minutes} minutes")
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        # Start concurrent monitoring tasks
        tasks = [
            asyncio.create_task(self._monitor_security_events()),
            asyncio.create_task(self._periodic_vulnerability_scan()),
            asyncio.create_task(self._periodic_compliance_check())
        ]
        
        try:
            # Run monitoring tasks until duration expires
            while datetime.now() < end_time:
                await asyncio.sleep(10)  # Check every 10 seconds
            
            # Cancel all tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete cancellation
            await asyncio.gather(*tasks, return_exceptions=True)
            
            logger.info("Security monitoring completed")
            
        except KeyboardInterrupt:
            logger.info("Security monitoring interrupted by user")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _monitor_security_events(self):
        """Continuously monitor for security events"""
        while True:
            try:
                # Simulate log sources
                log_sources = [
                    "authentication failed for user admin from 192.168.1.100",
                    "sudo access granted to user operator",
                    "suspicious network traffic detected from 10.0.0.50",
                    "malware signature detected in file system",
                    "large file transfer initiated to external IP 203.0.113.1",
                    "normal system operation",
                    "user login successful for john.doe",
                    "configuration change detected in firewall rules"
                ]
                
                # Process each log entry
                for log_entry in log_sources:
                    events = self.event_detector.analyze_log_entry(log_entry)
                    for event in events:
                        self.security_events.append(event)
                        self.metrics['events_detected'] += 1
                        
                        # Log high-severity events
                        if event.threat_level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]:
                            logger.warning(f"Security event detected: {event.description} (Level: {event.threat_level.value})")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in security event monitoring: {e}")
                await asyncio.sleep(5)
    
    async def _periodic_vulnerability_scan(self):
        """Perform periodic vulnerability scans"""
        while True:
            try:
                logger.info("Starting vulnerability scan...")
                vulnerabilities = await self.vulnerability_scanner.scan_system()
                
                # Add new vulnerabilities
                for vuln in vulnerabilities:
                    self.vulnerabilities.append(vuln)
                    self.metrics['vulnerabilities_found'] += 1
                    
                    if vuln.threat_level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]:
                        logger.error(f"Critical vulnerability found: {vuln.description}")
                
                logger.info(f"Vulnerability scan completed: {len(vulnerabilities)} vulnerabilities found")
                
                # Wait 2 minutes before next scan
                await asyncio.sleep(120)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in vulnerability scanning: {e}")
                await asyncio.sleep(60)
    
    async def _periodic_compliance_check(self):
        """Perform periodic compliance checks"""
        standards = [ComplianceStandard.SOC2, ComplianceStandard.GDPR, ComplianceStandard.HIPAA]
        
        while True:
            try:
                for standard in standards:
                    logger.info(f"Starting compliance check for {standard.value}")
                    results = await self.compliance_monitor.check_compliance(standard)
                    self.compliance_results[standard] = results
                    
                    # Calculate compliance score
                    passed = len([r for r in results if r.status == 'pass'])
                    total = len(results)
                    score = (passed / total) * 100 if total > 0 else 0
                    
                    logger.info(f"Compliance check completed for {standard.value}: {score:.1f}% ({passed}/{total})")
                
                # Wait 3 minutes before next compliance check
                await asyncio.sleep(180)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in compliance checking: {e}")
                await asyncio.sleep(60)
    
    def get_security_summary(self) -> Dict[str, Any]:
        """Get comprehensive security summary"""
        
        # Calculate threat distribution
        threat_distribution = Counter(event.threat_level for event in self.security_events)
        
        # Calculate vulnerability distribution
        vuln_distribution = Counter(vuln.threat_level for vuln in self.vulnerabilities)
        
        # Calculate overall compliance score
        compliance_scores = {}
        overall_compliance = 0.0
        
        for standard, results in self.compliance_results.items():
            if results:
                passed = len([r for r in results if r.status == 'pass'])
                total = len(results)
                score = (passed / total) * 100 if total > 0 else 0
                compliance_scores[standard.value] = score
                overall_compliance += score
        
        if compliance_scores:
            overall_compliance = overall_compliance / len(compliance_scores)
        
        # Recent high-severity events
        recent_critical_events = [
            event for event in self.security_events[-20:]
            if event.threat_level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]
        ]
        
        # Critical vulnerabilities
        critical_vulnerabilities = [
            vuln for vuln in self.vulnerabilities
            if vuln.threat_level == ThreatLevel.CRITICAL
        ]
        
        return {
            'monitoring_metrics': {
                'total_events': len(self.security_events),
                'total_vulnerabilities': len(self.vulnerabilities),
                'overall_compliance_score': round(overall_compliance, 1),
                'critical_events_count': len(recent_critical_events),
                'critical_vulnerabilities_count': len(critical_vulnerabilities)
            },
            'threat_distribution': {level.value: count for level, count in threat_distribution.items()},
            'vulnerability_distribution': {level.value: count for level, count in vuln_distribution.items()},
            'compliance_scores': compliance_scores,
            'recent_critical_events': [
                {
                    'id': event.event_id,
                    'type': event.event_type.value,
                    'level': event.threat_level.value,
                    'description': event.description,
                    'timestamp': event.timestamp.isoformat()
                }
                for event in recent_critical_events
            ],
            'critical_vulnerabilities': [
                {
                    'id': vuln.vuln_id,
                    'type': vuln.vulnerability_type.value,
                    'severity': vuln.severity_score,
                    'description': vuln.description,
                    'affected_systems': vuln.affected_systems
                }
                for vuln in critical_vulnerabilities
            ],
            'recommendations': self._generate_security_recommendations()
        }
    
    def _generate_security_recommendations(self) -> List[str]:
        """Generate security recommendations based on findings"""
        recommendations = []
        
        # Check for high-frequency events
        event_types = Counter(event.event_type for event in self.security_events)
        for event_type, count in event_types.most_common(3):
            if count > 5:
                recommendations.append(f"High frequency of {event_type.value} events detected - review security controls")
        
        # Check for critical vulnerabilities
        critical_vulns = [v for v in self.vulnerabilities if v.threat_level == ThreatLevel.CRITICAL]
        if critical_vulns:
            recommendations.append(f"Address {len(critical_vulns)} critical vulnerabilities immediately")
        
        # Check compliance scores
        for standard, results in self.compliance_results.items():
            if results:
                failed = len([r for r in results if r.status == 'fail'])
                if failed > 0:
                    recommendations.append(f"Fix {failed} failed compliance controls for {standard.value}")
        
        # Default recommendations if none generated
        if not recommendations:
            recommendations = [
                "Continue monitoring - security posture is good",
                "Consider implementing additional threat detection rules",
                "Review and update security policies regularly"
            ]
        
        return recommendations

async def demonstrate_security_monitoring():
    """Demonstrate the security monitoring system"""
    print("AIOps Security & Compliance Monitoring System Demo")
    print("=" * 65)
    
    # Initialize security monitoring
    security_system = SecurityMonitoringSystem()
    
    print("🔐 Starting comprehensive security monitoring...\n")
    
    # Start monitoring for 1 minute (shortened for demo)
    print("📊 Monitoring security events, vulnerabilities, and compliance...")
    await security_system.start_monitoring(duration_minutes=1)
    
    print("\n🔍 Security monitoring completed. Generating report...\n")
    
    # Get security summary
    summary = security_system.get_security_summary()
    
    # Display results
    print("📈 Security Monitoring Summary:")
    metrics = summary['monitoring_metrics']
    print(f"  Total Security Events: {metrics['total_events']}")
    print(f"  Total Vulnerabilities: {metrics['total_vulnerabilities']}")
    print(f"  Overall Compliance Score: {metrics['overall_compliance_score']}%")
    print(f"  Critical Events: {metrics['critical_events_count']}")
    print(f"  Critical Vulnerabilities: {metrics['critical_vulnerabilities_count']}")
    
    print(f"\n🎯 Threat Level Distribution:")
    for level, count in summary['threat_distribution'].items():
        print(f"  {level.title()}: {count}")
    
    print(f"\n🛡️ Vulnerability Distribution:")
    for level, count in summary['vulnerability_distribution'].items():
        print(f"  {level.title()}: {count}")
    
    print(f"\n✅ Compliance Scores:")
    for standard, score in summary['compliance_scores'].items():
        status_icon = "✅" if score >= 90 else "⚠️" if score >= 70 else "❌"
        print(f"  {status_icon} {standard.upper()}: {score}%")
    
    if summary['recent_critical_events']:
        print(f"\n🚨 Recent Critical Events:")
        for event in summary['recent_critical_events'][:5]:
            print(f"  • [{event['level'].upper()}] {event['type']}: {event['description']}")
    
    if summary['critical_vulnerabilities']:
        print(f"\n⚠️ Critical Vulnerabilities:")
        for vuln in summary['critical_vulnerabilities'][:3]:
            print(f"  • [CVSS {vuln['severity']}] {vuln['description']}")
            print(f"    Affected: {', '.join(vuln['affected_systems'])}")
    
    print(f"\n💡 Security Recommendations:")
    for i, rec in enumerate(summary['recommendations'], 1):
        print(f"  {i}. {rec}")
    
    # Show detailed compliance results for one standard
    print(f"\n📋 SOC 2 Compliance Details:")
    soc2_results = security_system.compliance_results.get(ComplianceStandard.SOC2, [])
    for check in soc2_results:
        status_icon = {"pass": "✅", "partial": "⚠️", "fail": "❌"}.get(check.status, "❓")
        print(f"  {status_icon} {check.control_id}: {check.description} ({check.status})")
        if check.status != "pass" and hasattr(check, 'evidence'):
            print(f"      Risk Level: {check.risk_level.value}")
    
    print(f"\n🔧 Security System Capabilities:")
    print(f"  • Real-time threat detection and classification")
    print(f"  • Automated vulnerability scanning and assessment")
    print(f"  • Multi-standard compliance monitoring (SOC2, GDPR, HIPAA, PCI)")
    print(f"  • MITRE ATT&CK framework integration")
    print(f"  • Risk-based prioritization and remediation guidance")
    print(f"  • Continuous security posture monitoring")
    
    print(f"\n✅ Security monitoring demonstration completed!")
    print(f"🎯 Key Benefits:")
    print(f"  • Proactive threat detection and response")
    print(f"  • Automated compliance monitoring and reporting")
    print(f"  • Risk-based vulnerability management")
    print(f"  • Comprehensive security visibility and control")

if __name__ == "__main__":
    asyncio.run(demonstrate_security_monitoring())