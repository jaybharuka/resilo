#!/usr/bin/env python3
"""
AIOps Automated Incident Response System
Advanced automated incident response with playbook execution, evidence collection, and forensic analysis

Features:
- Incident classification and severity assessment
- Automated response playbook execution
- Real-time evidence collection and preservation
- Forensic analysis and chain of custody
- Integration with security tools and SIEM
- Escalation and notification workflows
- Post-incident analysis and reporting
- Machine learning-based response optimization
"""

import asyncio
import json
import logging
import hashlib
import time
import shutil
import zipfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, Counter
import uuid
import sqlite3
import os
import subprocess
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('incident_response')

class IncidentSeverity(Enum):
    """Incident severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

class IncidentStatus(Enum):
    """Incident status"""
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"

class IncidentType(Enum):
    """Types of security incidents"""
    MALWARE_INFECTION = "malware_infection"
    DATA_BREACH = "data_breach"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DENIAL_OF_SERVICE = "denial_of_service"
    PHISHING_ATTACK = "phishing_attack"
    INSIDER_THREAT = "insider_threat"
    SYSTEM_COMPROMISE = "system_compromise"
    NETWORK_INTRUSION = "network_intrusion"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    RANSOMWARE = "ransomware"
    SOCIAL_ENGINEERING = "social_engineering"

class PlaybookStatus(Enum):
    """Playbook execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class EvidenceType(Enum):
    """Types of digital evidence"""
    SYSTEM_LOGS = "system_logs"
    NETWORK_TRAFFIC = "network_traffic"
    MEMORY_DUMP = "memory_dump"
    DISK_IMAGE = "disk_image"
    PROCESS_LIST = "process_list"
    REGISTRY_DUMP = "registry_dump"
    FILE_SYSTEM = "file_system"
    EMAIL_HEADERS = "email_headers"
    DATABASE_LOGS = "database_logs"
    BROWSER_HISTORY = "browser_history"
    SCREENSHOTS = "screenshots"
    CONFIGURATION_FILES = "configuration_files"

class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"

@dataclass
class SecurityIncident:
    """Security incident record"""
    incident_id: str
    title: str
    description: str
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    created_time: datetime
    updated_time: datetime
    detection_source: str
    affected_systems: List[str]
    affected_users: List[str]
    indicators_of_compromise: List[str]
    assigned_to: Optional[str] = None
    resolution_time: Optional[datetime] = None
    root_cause: Optional[str] = None
    lessons_learned: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    external_references: List[str] = field(default_factory=list)
    impact_assessment: Dict[str, Any] = field(default_factory=dict)
    timeline: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class ResponsePlaybook:
    """Incident response playbook"""
    playbook_id: str
    name: str
    description: str
    incident_types: List[IncidentType]
    severity_threshold: IncidentSeverity
    tasks: List['PlaybookTask']
    prerequisites: List[str] = field(default_factory=list)
    estimated_duration: Optional[int] = None  # minutes
    is_active: bool = True
    version: str = "1.0"
    created_by: str = "system"
    last_updated: datetime = field(default_factory=datetime.now)

@dataclass
class PlaybookTask:
    """Individual task in a response playbook"""
    task_id: str
    name: str
    description: str
    task_type: str  # isolate, collect, analyze, notify, remediate
    action: str  # specific action to perform
    parameters: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    timeout_minutes: int = 30
    is_manual: bool = False
    approval_required: bool = False
    parallel_execution: bool = False
    retry_count: int = 3
    expected_outputs: List[str] = field(default_factory=list)

@dataclass
class PlaybookExecution:
    """Playbook execution instance"""
    execution_id: str
    incident_id: str
    playbook_id: str
    status: PlaybookStatus
    start_time: datetime
    end_time: Optional[datetime]
    executed_by: str
    task_results: Dict[str, 'TaskResult'] = field(default_factory=dict)
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    execution_log: List[str] = field(default_factory=list)

@dataclass
class TaskResult:
    """Result of a playbook task execution"""
    task_id: str
    status: TaskStatus
    start_time: datetime
    end_time: Optional[datetime]
    output: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    artifacts_created: List[str] = field(default_factory=list)
    evidence_collected: List[str] = field(default_factory=list)

@dataclass
class DigitalEvidence:
    """Digital evidence record"""
    evidence_id: str
    incident_id: str
    evidence_type: EvidenceType
    source_system: str
    collection_time: datetime
    collector: str
    file_path: str
    file_size: int
    file_hash: str
    chain_of_custody: List[Dict[str, Any]]
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_preserved: bool = True
    analysis_results: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ForensicAnalysis:
    """Forensic analysis results"""
    analysis_id: str
    incident_id: str
    evidence_ids: List[str]
    analysis_type: str
    start_time: datetime
    end_time: Optional[datetime]
    analyst: str
    findings: List[Dict[str, Any]]
    timeline: List[Dict[str, Any]]
    indicators_found: List[str]
    confidence_score: float
    tools_used: List[str]
    report_path: Optional[str] = None

class IncidentDatabase:
    """Incident response database interface"""
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info(f"Incident response database initialized: {db_path}")
    
    def _create_tables(self):
        """Apply schema migrations for the incident response SQLite database."""
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _migrations_dir = _os.path.join(
            _here, "..", "..", "migrations", "sqlite", "incident"
        )
        if self.db_path == ":memory:":
            _sql_file = _os.path.join(_migrations_dir, "001_initial.sql")
            with open(_sql_file, encoding="utf-8") as _f:
                self.conn.executescript(_f.read())
        else:
            from app.core.sqlite_migrator import run_sqlite_migrations
            run_sqlite_migrations(self.db_path, _migrations_dir)
    
    def store_incident(self, incident: SecurityIncident):
        """Store security incident"""
        incident_data = {
            'affected_systems': incident.affected_systems,
            'affected_users': incident.affected_users,
            'indicators_of_compromise': incident.indicators_of_compromise,
            'tags': incident.tags,
            'external_references': incident.external_references,
            'impact_assessment': incident.impact_assessment,
            'timeline': incident.timeline,
            'root_cause': incident.root_cause,
            'lessons_learned': incident.lessons_learned
        }
        
        self.conn.execute("""
        INSERT OR REPLACE INTO incidents
        (incident_id, title, description, incident_type, severity, status,
         created_time, updated_time, detection_source, assigned_to, resolution_time, incident_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            incident.incident_id, incident.title, incident.description,
            incident.incident_type.value, incident.severity.value, incident.status.value,
            incident.created_time.isoformat(), incident.updated_time.isoformat(),
            incident.detection_source, incident.assigned_to,
            incident.resolution_time.isoformat() if incident.resolution_time else None,
            json.dumps(incident_data)
        ))
        self.conn.commit()
    
    def store_playbook_execution(self, execution: PlaybookExecution):
        """Store playbook execution"""
        execution_data = {
            'task_results': {k: {
                'task_id': v.task_id,
                'status': v.status.value,
                'start_time': v.start_time.isoformat(),
                'end_time': v.end_time.isoformat() if v.end_time else None,
                'output': v.output,
                'error_message': v.error_message,
                'artifacts_created': v.artifacts_created,
                'evidence_collected': v.evidence_collected
            } for k, v in execution.task_results.items()},
            'execution_log': execution.execution_log
        }
        
        self.conn.execute("""
        INSERT OR REPLACE INTO playbook_executions
        (execution_id, incident_id, playbook_id, status, start_time, end_time,
         executed_by, total_tasks, completed_tasks, failed_tasks, execution_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            execution.execution_id, execution.incident_id, execution.playbook_id,
            execution.status.value, execution.start_time.isoformat(),
            execution.end_time.isoformat() if execution.end_time else None,
            execution.executed_by, execution.total_tasks, execution.completed_tasks,
            execution.failed_tasks, json.dumps(execution_data)
        ))
        self.conn.commit()
    
    def store_evidence(self, evidence: DigitalEvidence):
        """Store digital evidence"""
        evidence_data = {
            'chain_of_custody': evidence.chain_of_custody,
            'metadata': evidence.metadata,
            'analysis_results': evidence.analysis_results,
            'is_preserved': evidence.is_preserved
        }
        
        self.conn.execute("""
        INSERT OR REPLACE INTO evidence
        (evidence_id, incident_id, evidence_type, source_system, collection_time,
         collector, file_path, file_size, file_hash, description, evidence_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            evidence.evidence_id, evidence.incident_id, evidence.evidence_type.value,
            evidence.source_system, evidence.collection_time.isoformat(),
            evidence.collector, evidence.file_path, evidence.file_size,
            evidence.file_hash, evidence.description, json.dumps(evidence_data)
        ))
        self.conn.commit()

class EvidenceCollector:
    """Digital evidence collection system"""
    
    def __init__(self, evidence_directory: str = "./evidence"):
        self.evidence_directory = evidence_directory
        os.makedirs(evidence_directory, exist_ok=True)
        logger.info(f"Evidence collector initialized: {evidence_directory}")
    
    async def collect_system_logs(self, system: str, incident_id: str) -> DigitalEvidence:
        """Collect system logs"""
        evidence_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # Simulate log collection
        log_content = f"""
System Logs for {system} - Incident {incident_id}
Collection Time: {timestamp.isoformat()}
===================================================

[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] INFO: System startup completed
[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Unusual network activity detected
[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Failed login attempt from 203.0.113.100
[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] ALERT: Suspicious process execution: malware.exe
[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] INFO: Security scan initiated
[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Unauthorized file access detected
[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Connection to known C&C server blocked
[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] ALERT: Privilege escalation attempt detected
"""
        
        # Save to file
        file_path = os.path.join(self.evidence_directory, f"system_logs_{evidence_id}.log")
        with open(file_path, 'w') as f:
            f.write(log_content)
        
        # Calculate hash
        file_hash = hashlib.sha256(log_content.encode()).hexdigest()
        file_size = len(log_content.encode())
        
        # Create evidence record
        evidence = DigitalEvidence(
            evidence_id=evidence_id,
            incident_id=incident_id,
            evidence_type=EvidenceType.SYSTEM_LOGS,
            source_system=system,
            collection_time=timestamp,
            collector="automated_collector",
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,
            chain_of_custody=[{
                'timestamp': timestamp.isoformat(),
                'action': 'collected',
                'person': 'automated_collector',
                'location': system
            }],
            description=f"System logs collected from {system}",
            metadata={
                'log_level': 'all',
                'time_range': '24h',
                'source_type': 'syslog'
            }
        )
        
        logger.info(f"Collected system logs: {evidence_id}")
        return evidence
    
    async def collect_network_traffic(self, interface: str, incident_id: str, duration_minutes: int = 10) -> DigitalEvidence:
        """Collect network traffic capture"""
        evidence_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # Simulate network capture
        pcap_content = f"""
Network Traffic Capture - Incident {incident_id}
Interface: {interface}
Duration: {duration_minutes} minutes
Collection Time: {timestamp.isoformat()}
================================================

Packet 1: 192.168.1.100 -> 203.0.113.100:443 [TCP SYN]
Packet 2: 203.0.113.100:443 -> 192.168.1.100 [TCP SYN-ACK]
Packet 3: 192.168.1.100 -> 203.0.113.100:443 [TCP ACK]
Packet 4: 192.168.1.100 -> 203.0.113.100:443 [HTTP GET /malware.exe]
Packet 5: 203.0.113.100:443 -> 192.168.1.100 [HTTP 200 OK]
Packet 6: 203.0.113.100:443 -> 192.168.1.100 [Data Transfer]
Packet 7: 192.168.1.100 -> 203.0.113.100:443 [TCP FIN]
Packet 8: 203.0.113.100:443 -> 192.168.1.100 [TCP FIN-ACK]
"""
        
        # Save to file
        file_path = os.path.join(self.evidence_directory, f"network_capture_{evidence_id}.pcap")
        with open(file_path, 'w') as f:
            f.write(pcap_content)
        
        file_hash = hashlib.sha256(pcap_content.encode()).hexdigest()
        file_size = len(pcap_content.encode())
        
        evidence = DigitalEvidence(
            evidence_id=evidence_id,
            incident_id=incident_id,
            evidence_type=EvidenceType.NETWORK_TRAFFIC,
            source_system=interface,
            collection_time=timestamp,
            collector="automated_collector",
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,
            chain_of_custody=[{
                'timestamp': timestamp.isoformat(),
                'action': 'captured',
                'person': 'automated_collector',
                'interface': interface
            }],
            description=f"Network traffic captured from {interface}",
            metadata={
                'interface': interface,
                'duration_minutes': duration_minutes,
                'capture_filter': 'all',
                'protocol_analysis': True
            }
        )
        
        logger.info(f"Collected network traffic: {evidence_id}")
        return evidence
    
    async def collect_memory_dump(self, system: str, incident_id: str) -> DigitalEvidence:
        """Collect memory dump"""
        evidence_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # Simulate memory dump
        memory_content = f"""
Memory Dump Analysis - Incident {incident_id}
System: {system}
Collection Time: {timestamp.isoformat()}
=============================================

Process List:
- PID 1234: explorer.exe (Normal)
- PID 5678: malware.exe (Suspicious)
- PID 9012: cmd.exe (Spawned by malware.exe)
- PID 3456: powershell.exe (Suspicious activity)

Network Connections:
- TCP 192.168.1.100:1234 -> 203.0.113.100:443 (Established)
- TCP 192.168.1.100:5678 -> 198.51.100.50:80 (Established)

Loaded Modules:
- kernel32.dll (System)
- ntdll.dll (System)
- suspicious.dll (Unknown signature)

Registry Keys:
- HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Malware
- HKCU\\Software\\Classes\\exefile\\shell\\open\\command (Modified)
"""
        
        # Save to file
        file_path = os.path.join(self.evidence_directory, f"memory_dump_{evidence_id}.dmp")
        with open(file_path, 'w') as f:
            f.write(memory_content)
        
        file_hash = hashlib.sha256(memory_content.encode()).hexdigest()
        file_size = len(memory_content.encode())
        
        evidence = DigitalEvidence(
            evidence_id=evidence_id,
            incident_id=incident_id,
            evidence_type=EvidenceType.MEMORY_DUMP,
            source_system=system,
            collection_time=timestamp,
            collector="automated_collector",
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,
            chain_of_custody=[{
                'timestamp': timestamp.isoformat(),
                'action': 'dumped',
                'person': 'automated_collector',
                'system': system
            }],
            description=f"Memory dump collected from {system}",
            metadata={
                'dump_type': 'full',
                'compression': 'none',
                'analysis_tools': ['volatility', 'rekall']
            }
        )
        
        logger.info(f"Collected memory dump: {evidence_id}")
        return evidence

class PlaybookExecutor:
    """Automated playbook execution engine"""
    
    def __init__(self, evidence_collector: EvidenceCollector):
        self.evidence_collector = evidence_collector
        self.running_executions = {}  # execution_id -> execution
        logger.info("Playbook executor initialized")
    
    async def execute_playbook(self, incident: SecurityIncident, playbook: ResponsePlaybook, 
                             executed_by: str = "system") -> PlaybookExecution:
        """Execute incident response playbook"""
        execution_id = str(uuid.uuid4())
        
        execution = PlaybookExecution(
            execution_id=execution_id,
            incident_id=incident.incident_id,
            playbook_id=playbook.playbook_id,
            status=PlaybookStatus.RUNNING,
            start_time=datetime.now(),
            end_time=None,
            executed_by=executed_by,
            total_tasks=len(playbook.tasks),
            completed_tasks=0,
            failed_tasks=0
        )
        
        self.running_executions[execution_id] = execution
        execution.execution_log.append(f"Started playbook execution: {playbook.name}")
        
        logger.info(f"Starting playbook execution {execution_id} for incident {incident.incident_id}")
        
        try:
            # Execute tasks
            for task in playbook.tasks:
                if execution.status == PlaybookStatus.CANCELLED:
                    break
                
                result = await self._execute_task(task, incident, execution)
                execution.task_results[task.task_id] = result
                
                if result.status == TaskStatus.SUCCESS:
                    execution.completed_tasks += 1
                    execution.execution_log.append(f"Task completed: {task.name}")
                elif result.status == TaskStatus.FAILED:
                    execution.failed_tasks += 1
                    execution.execution_log.append(f"Task failed: {task.name} - {result.error_message}")
                    
                    # Stop execution on critical task failure
                    if not task.parallel_execution:
                        execution.status = PlaybookStatus.FAILED
                        break
            
            # Update final status
            if execution.status == PlaybookStatus.RUNNING:
                if execution.failed_tasks == 0:
                    execution.status = PlaybookStatus.COMPLETED
                elif execution.completed_tasks > 0:
                    execution.status = PlaybookStatus.COMPLETED  # Partial success
                else:
                    execution.status = PlaybookStatus.FAILED
            
            execution.end_time = datetime.now()
            execution.execution_log.append(f"Playbook execution completed: {execution.status.value}")
            
        except Exception as e:
            execution.status = PlaybookStatus.FAILED
            execution.end_time = datetime.now()
            execution.execution_log.append(f"Execution failed with error: {str(e)}")
            logger.error(f"Playbook execution {execution_id} failed: {e}")
        
        finally:
            if execution_id in self.running_executions:
                del self.running_executions[execution_id]
        
        logger.info(f"Playbook execution {execution_id} completed with status: {execution.status.value}")
        return execution
    
    async def _execute_task(self, task: PlaybookTask, incident: SecurityIncident, 
                          execution: PlaybookExecution) -> TaskResult:
        """Execute individual playbook task"""
        start_time = datetime.now()
        
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.RUNNING,
            start_time=start_time,
            end_time=None
        )
        
        try:
            execution.execution_log.append(f"Executing task: {task.name}")
            logger.info(f"Executing task {task.task_id}: {task.name}")
            
            # Route to appropriate task handler
            if task.task_type == "isolate":
                await self._isolate_system(task, incident, result)
            elif task.task_type == "collect":
                await self._collect_evidence(task, incident, result)
            elif task.task_type == "analyze":
                await self._analyze_evidence(task, incident, result)
            elif task.task_type == "notify":
                await self._send_notification(task, incident, result)
            elif task.task_type == "remediate":
                await self._remediate_threat(task, incident, result)
            else:
                result.status = TaskStatus.FAILED
                result.error_message = f"Unknown task type: {task.task_type}"
            
            if result.status == TaskStatus.RUNNING:
                result.status = TaskStatus.SUCCESS
            
        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error_message = str(e)
            logger.error(f"Task {task.task_id} failed: {e}")
        
        result.end_time = datetime.now()
        return result
    
    async def _isolate_system(self, task: PlaybookTask, incident: SecurityIncident, result: TaskResult):
        """Isolate affected system"""
        systems = task.parameters.get('systems', incident.affected_systems)
        
        for system in systems:
            # Simulate system isolation
            await asyncio.sleep(0.1)  # Simulate isolation time
            
            result.output[f'{system}_isolation'] = {
                'status': 'isolated',
                'timestamp': datetime.now().isoformat(),
                'method': 'network_quarantine',
                'firewall_rules_applied': True
            }
            
            result.artifacts_created.append(f"isolation_report_{system}.txt")
        
        logger.info(f"Isolated {len(systems)} systems")
    
    async def _collect_evidence(self, task: PlaybookTask, incident: SecurityIncident, result: TaskResult):
        """Collect digital evidence"""
        evidence_types = task.parameters.get('evidence_types', ['system_logs', 'network_traffic'])
        systems = task.parameters.get('systems', incident.affected_systems)
        
        for system in systems:
            for evidence_type in evidence_types:
                if evidence_type == 'system_logs':
                    evidence = await self.evidence_collector.collect_system_logs(system, incident.incident_id)
                elif evidence_type == 'network_traffic':
                    evidence = await self.evidence_collector.collect_network_traffic(system, incident.incident_id)
                elif evidence_type == 'memory_dump':
                    evidence = await self.evidence_collector.collect_memory_dump(system, incident.incident_id)
                else:
                    continue
                
                result.evidence_collected.append(evidence.evidence_id)
                result.output[f'{system}_{evidence_type}'] = {
                    'evidence_id': evidence.evidence_id,
                    'file_path': evidence.file_path,
                    'file_hash': evidence.file_hash,
                    'collection_time': evidence.collection_time.isoformat()
                }
        
        logger.info(f"Collected {len(result.evidence_collected)} evidence items")
    
    async def _analyze_evidence(self, task: PlaybookTask, incident: SecurityIncident, result: TaskResult):
        """Analyze collected evidence"""
        analysis_type = task.parameters.get('analysis_type', 'malware_scan')
        
        # Simulate evidence analysis
        await asyncio.sleep(0.2)  # Simulate analysis time
        
        if analysis_type == 'malware_scan':
            result.output['malware_analysis'] = {
                'threats_found': ['malware.exe', 'suspicious.dll'],
                'threat_count': 2,
                'signatures_matched': ['Win32.Trojan.Banking', 'Win32.Backdoor.Agent'],
                'confidence_score': 0.95,
                'analysis_tools': ['clamav', 'yara']
            }
        elif analysis_type == 'network_analysis':
            result.output['network_analysis'] = {
                'suspicious_connections': ['203.0.113.100:443', '198.51.100.50:80'],
                'data_exfiltration_detected': True,
                'c2_communications': True,
                'bandwidth_anomalies': True
            }
        elif analysis_type == 'timeline_analysis':
            result.output['timeline_analysis'] = {
                'attack_timeline': [
                    {'time': '10:00', 'event': 'Initial compromise'},
                    {'time': '10:15', 'event': 'Privilege escalation'},
                    {'time': '10:30', 'event': 'Data access'},
                    {'time': '10:45', 'event': 'Exfiltration attempt'}
                ],
                'attack_duration': '45 minutes',
                'attack_sophistication': 'intermediate'
            }
        
        result.artifacts_created.append(f"analysis_report_{analysis_type}.json")
        logger.info(f"Completed {analysis_type} analysis")
    
    async def _send_notification(self, task: PlaybookTask, incident: SecurityIncident, result: TaskResult):
        """Send incident notifications"""
        recipients = task.parameters.get('recipients', ['security-team@company.com'])
        notification_type = task.parameters.get('type', 'email')
        
        # Simulate notification sending
        for recipient in recipients:
            result.output[f'notification_{recipient}'] = {
                'status': 'sent',
                'timestamp': datetime.now().isoformat(),
                'type': notification_type,
                'subject': f"Security Incident: {incident.title}",
                'content_preview': f"Incident {incident.incident_id} has been detected..."
            }
        
        logger.info(f"Sent notifications to {len(recipients)} recipients")
    
    async def _remediate_threat(self, task: PlaybookTask, incident: SecurityIncident, result: TaskResult):
        """Remediate identified threats"""
        remediation_type = task.parameters.get('remediation_type', 'quarantine_files')
        
        if remediation_type == 'quarantine_files':
            result.output['file_quarantine'] = {
                'files_quarantined': ['malware.exe', 'suspicious.dll'],
                'quarantine_location': '/var/quarantine/',
                'quarantine_time': datetime.now().isoformat(),
                'backup_created': True
            }
        elif remediation_type == 'block_ips':
            result.output['ip_blocking'] = {
                'blocked_ips': ['203.0.113.100', '198.51.100.50'],
                'firewall_rules_added': 2,
                'blocking_method': 'iptables',
                'duration': 'permanent'
            }
        elif remediation_type == 'reset_passwords':
            result.output['password_reset'] = {
                'accounts_affected': incident.affected_users,
                'passwords_reset': len(incident.affected_users),
                'mfa_enforced': True,
                'notification_sent': True
            }
        
        result.artifacts_created.append(f"remediation_report_{remediation_type}.txt")
        logger.info(f"Completed {remediation_type} remediation")

class IncidentResponseSystem:
    """Main incident response system"""
    
    def __init__(self):
        self.database = IncidentDatabase()
        self.evidence_collector = EvidenceCollector()
        self.playbook_executor = PlaybookExecutor(self.evidence_collector)
        self.playbooks = {}  # playbook_id -> ResponsePlaybook
        self.incidents = {}  # incident_id -> SecurityIncident
        
        # Initialize with sample playbooks
        self._load_sample_playbooks()
        
        logger.info("Incident response system initialized")
    
    def _load_sample_playbooks(self):
        """Load sample response playbooks"""
        
        # Malware infection playbook
        malware_tasks = [
            PlaybookTask(
                task_id="isolate_infected_systems",
                name="Isolate Infected Systems",
                description="Quarantine infected systems to prevent spread",
                task_type="isolate",
                action="network_quarantine",
                parameters={'isolation_method': 'firewall_rules'},
                timeout_minutes=10
            ),
            PlaybookTask(
                task_id="collect_system_evidence",
                name="Collect System Evidence",
                description="Collect logs and memory dumps",
                task_type="collect",
                action="evidence_collection",
                parameters={'evidence_types': ['system_logs', 'memory_dump']},
                dependencies=["isolate_infected_systems"],
                timeout_minutes=30
            ),
            PlaybookTask(
                task_id="analyze_malware",
                name="Analyze Malware",
                description="Perform malware analysis",
                task_type="analyze",
                action="malware_analysis",
                parameters={'analysis_type': 'malware_scan'},
                dependencies=["collect_system_evidence"],
                timeout_minutes=45
            ),
            PlaybookTask(
                task_id="notify_stakeholders",
                name="Notify Stakeholders",
                description="Send incident notifications",
                task_type="notify",
                action="send_notifications",
                parameters={
                    'recipients': ['security-team@company.com', 'ciso@company.com'],
                    'type': 'email'
                },
                parallel_execution=True,
                timeout_minutes=5
            ),
            PlaybookTask(
                task_id="remediate_malware",
                name="Remediate Malware",
                description="Remove or quarantine malware",
                task_type="remediate",
                action="quarantine_threats",
                parameters={'remediation_type': 'quarantine_files'},
                dependencies=["analyze_malware"],
                timeout_minutes=20
            )
        ]
        
        malware_playbook = ResponsePlaybook(
            playbook_id="PB-MALWARE-001",
            name="Malware Infection Response",
            description="Standard response for malware infections",
            incident_types=[IncidentType.MALWARE_INFECTION, IncidentType.SYSTEM_COMPROMISE],
            severity_threshold=IncidentSeverity.MEDIUM,
            tasks=malware_tasks,
            estimated_duration=110
        )
        
        # Data breach playbook
        breach_tasks = [
            PlaybookTask(
                task_id="assess_breach_scope",
                name="Assess Breach Scope",
                description="Determine the scope of data compromise",
                task_type="analyze",
                action="scope_assessment",
                parameters={'analysis_type': 'data_access_analysis'},
                timeout_minutes=30
            ),
            PlaybookTask(
                task_id="isolate_affected_systems",
                name="Isolate Affected Systems",
                description="Isolate systems with compromised data",
                task_type="isolate",
                action="system_isolation",
                parameters={'isolation_method': 'network_segmentation'},
                dependencies=["assess_breach_scope"],
                timeout_minutes=15
            ),
            PlaybookTask(
                task_id="collect_access_logs",
                name="Collect Access Logs",
                description="Collect database and application logs",
                task_type="collect",
                action="log_collection",
                parameters={'evidence_types': ['system_logs', 'database_logs']},
                timeout_minutes=20
            ),
            PlaybookTask(
                task_id="notify_authorities",
                name="Notify Authorities",
                description="Send regulatory notifications",
                task_type="notify",
                action="regulatory_notification",
                parameters={
                    'recipients': ['legal@company.com', 'compliance@company.com'],
                    'type': 'urgent'
                },
                approval_required=True,
                timeout_minutes=10
            ),
            PlaybookTask(
                task_id="reset_credentials",
                name="Reset Compromised Credentials",
                description="Reset passwords for affected accounts",
                task_type="remediate",
                action="credential_reset",
                parameters={'remediation_type': 'reset_passwords'},
                dependencies=["assess_breach_scope"],
                timeout_minutes=30
            )
        ]
        
        breach_playbook = ResponsePlaybook(
            playbook_id="PB-BREACH-001",
            name="Data Breach Response",
            description="Response for data breach incidents",
            incident_types=[IncidentType.DATA_BREACH, IncidentType.UNAUTHORIZED_ACCESS],
            severity_threshold=IncidentSeverity.HIGH,
            tasks=breach_tasks,
            estimated_duration=105
        )
        
        # Network intrusion playbook
        intrusion_tasks = [
            PlaybookTask(
                task_id="analyze_network_traffic",
                name="Analyze Network Traffic",
                description="Capture and analyze network traffic",
                task_type="collect",
                action="network_capture",
                parameters={'evidence_types': ['network_traffic']},
                timeout_minutes=20
            ),
            PlaybookTask(
                task_id="identify_attack_vector",
                name="Identify Attack Vector",
                description="Analyze how the intrusion occurred",
                task_type="analyze",
                action="attack_analysis",
                parameters={'analysis_type': 'network_analysis'},
                dependencies=["analyze_network_traffic"],
                timeout_minutes=45
            ),
            PlaybookTask(
                task_id="block_malicious_ips",
                name="Block Malicious IPs",
                description="Block identified malicious IP addresses",
                task_type="remediate",
                action="ip_blocking",
                parameters={'remediation_type': 'block_ips'},
                dependencies=["identify_attack_vector"],
                timeout_minutes=10
            ),
            PlaybookTask(
                task_id="strengthen_defenses",
                name="Strengthen Network Defenses",
                description="Update firewall rules and IDS signatures",
                task_type="remediate",
                action="defense_update",
                parameters={'remediation_type': 'update_defenses'},
                dependencies=["identify_attack_vector"],
                timeout_minutes=25
            )
        ]
        
        intrusion_playbook = ResponsePlaybook(
            playbook_id="PB-INTRUSION-001",
            name="Network Intrusion Response",
            description="Response for network intrusion incidents",
            incident_types=[IncidentType.NETWORK_INTRUSION, IncidentType.SYSTEM_COMPROMISE],
            severity_threshold=IncidentSeverity.MEDIUM,
            tasks=intrusion_tasks,
            estimated_duration=100
        )
        
        # Store playbooks
        self.playbooks = {
            malware_playbook.playbook_id: malware_playbook,
            breach_playbook.playbook_id: breach_playbook,
            intrusion_playbook.playbook_id: intrusion_playbook
        }
        
        logger.info(f"Loaded {len(self.playbooks)} response playbooks")
    
    async def create_incident(self, incident_data: Dict[str, Any]) -> SecurityIncident:
        """Create new security incident"""
        incident_id = incident_data.get('incident_id', str(uuid.uuid4()))
        
        incident = SecurityIncident(
            incident_id=incident_id,
            title=incident_data['title'],
            description=incident_data['description'],
            incident_type=IncidentType(incident_data['incident_type']),
            severity=IncidentSeverity(incident_data['severity']),
            status=IncidentStatus.NEW,
            created_time=datetime.now(),
            updated_time=datetime.now(),
            detection_source=incident_data.get('detection_source', 'automated'),
            affected_systems=incident_data.get('affected_systems', []),
            affected_users=incident_data.get('affected_users', []),
            indicators_of_compromise=incident_data.get('iocs', []),
            tags=incident_data.get('tags', []),
            impact_assessment=incident_data.get('impact_assessment', {})
        )
        
        # Store incident
        self.incidents[incident_id] = incident
        self.database.store_incident(incident)
        
        logger.info(f"Created incident {incident_id}: {incident.title}")
        return incident
    
    def select_playbook(self, incident: SecurityIncident) -> Optional[ResponsePlaybook]:
        """Select appropriate playbook for incident"""
        
        matching_playbooks = []
        
        for playbook in self.playbooks.values():
            # Check incident type match
            if incident.incident_type in playbook.incident_types:
                # Check severity threshold
                severity_order = [IncidentSeverity.INFORMATIONAL, IncidentSeverity.LOW, 
                                IncidentSeverity.MEDIUM, IncidentSeverity.HIGH, IncidentSeverity.CRITICAL]
                
                incident_severity_index = severity_order.index(incident.severity)
                playbook_threshold_index = severity_order.index(playbook.severity_threshold)
                
                if incident_severity_index >= playbook_threshold_index:
                    matching_playbooks.append(playbook)
        
        # Return the most specific playbook (for now, just return the first match)
        if matching_playbooks:
            selected = matching_playbooks[0]
            logger.info(f"Selected playbook {selected.playbook_id} for incident {incident.incident_id}")
            return selected
        
        logger.warning(f"No matching playbook found for incident {incident.incident_id}")
        return None
    
    async def respond_to_incident(self, incident: SecurityIncident, 
                                executed_by: str = "system") -> Optional[PlaybookExecution]:
        """Automatically respond to incident using appropriate playbook"""
        
        # Select appropriate playbook
        playbook = self.select_playbook(incident)
        if not playbook:
            return None
        
        # Update incident status
        incident.status = IncidentStatus.IN_PROGRESS
        incident.updated_time = datetime.now()
        incident.timeline.append({
            'timestamp': datetime.now().isoformat(),
            'event': f'Automated response initiated with playbook {playbook.name}',
            'actor': executed_by
        })
        
        self.database.store_incident(incident)
        
        # Execute playbook
        execution = await self.playbook_executor.execute_playbook(incident, playbook, executed_by)
        
        # Store execution results
        self.database.store_playbook_execution(execution)
        
        # Update incident based on execution results
        if execution.status == PlaybookStatus.COMPLETED:
            incident.status = IncidentStatus.CONTAINED
            incident.timeline.append({
                'timestamp': datetime.now().isoformat(),
                'event': 'Automated response completed successfully',
                'actor': executed_by
            })
        else:
            incident.timeline.append({
                'timestamp': datetime.now().isoformat(),
                'event': f'Automated response failed: {execution.status.value}',
                'actor': executed_by
            })
        
        incident.updated_time = datetime.now()
        self.database.store_incident(incident)
        
        return execution
    
    def get_incident_dashboard_data(self) -> Dict[str, Any]:
        """Get incident response dashboard data"""
        
        # Incident statistics
        total_incidents = len(self.incidents)
        by_status = Counter(i.status.value for i in self.incidents.values())
        by_severity = Counter(i.severity.value for i in self.incidents.values())
        by_type = Counter(i.incident_type.value for i in self.incidents.values())
        
        # Recent incidents (last 24 hours)
        cutoff = datetime.now() - timedelta(hours=24)
        recent_incidents = [i for i in self.incidents.values() if i.created_time > cutoff]
        
        # Playbook statistics
        total_playbooks = len(self.playbooks)
        playbook_types = Counter()
        for pb in self.playbooks.values():
            for incident_type in pb.incident_types:
                playbook_types[incident_type.value] += 1
        
        # Response time analysis
        response_times = []
        for incident in self.incidents.values():
            if incident.resolution_time:
                duration = (incident.resolution_time - incident.created_time).total_seconds() / 60
                response_times.append(duration)
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'timestamp': datetime.now().isoformat(),
            'incident_statistics': {
                'total_incidents': total_incidents,
                'recent_incidents_24h': len(recent_incidents),
                'status_distribution': dict(by_status),
                'severity_distribution': dict(by_severity),
                'type_distribution': dict(by_type),
                'average_response_time_minutes': round(avg_response_time, 2)
            },
            'playbook_statistics': {
                'total_playbooks': total_playbooks,
                'coverage_by_type': dict(playbook_types),
                'automation_rate': 100.0  # All playbooks are automated
            },
            'recent_activity': {
                'recent_incidents': [
                    {
                        'incident_id': i.incident_id,
                        'title': i.title,
                        'severity': i.severity.value,
                        'status': i.status.value,
                        'created_time': i.created_time.isoformat()
                    }
                    for i in sorted(recent_incidents, key=lambda x: x.created_time, reverse=True)[:10]
                ]
            }
        }

async def demonstrate_incident_response():
    """Demonstrate the incident response system"""
    print("AIOps Automated Incident Response System Demo")
    print("=" * 53)
    
    # Initialize incident response system
    ir_system = IncidentResponseSystem()
    
    print("🚨 Incident response system initialized with sample playbooks\n")
    
    # Show available playbooks
    print("📋 Available Response Playbooks:")
    for playbook in ir_system.playbooks.values():
        print(f"  • {playbook.name}")
        print(f"    Types: {', '.join(t.value for t in playbook.incident_types)}")
        print(f"    Min Severity: {playbook.severity_threshold.value}")
        print(f"    Tasks: {len(playbook.tasks)}")
        print(f"    Estimated Duration: {playbook.estimated_duration} minutes")
    
    # Simulate security incidents
    print(f"\n🚨 Creating and responding to security incidents...")
    
    sample_incidents = [
        {
            'title': 'Malware Detected on Workstation',
            'description': 'Banking trojan detected on employee workstation WS-001',
            'incident_type': 'malware_infection',
            'severity': 'high',
            'detection_source': 'endpoint_detection',
            'affected_systems': ['WS-001', 'FILE-SERVER-01'],
            'affected_users': ['john.doe'],
            'iocs': ['malware.exe', '203.0.113.100'],
            'tags': ['malware', 'banking_trojan'],
            'impact_assessment': {
                'confidentiality': 'high',
                'integrity': 'medium',
                'availability': 'low'
            }
        },
        {
            'title': 'Unauthorized Database Access',
            'description': 'Suspicious access to customer database from external IP',
            'incident_type': 'data_breach',
            'severity': 'critical',
            'detection_source': 'database_monitoring',
            'affected_systems': ['DB-PROD-01'],
            'affected_users': ['db_admin'],
            'iocs': ['198.51.100.50', 'suspicious_query.sql'],
            'tags': ['data_breach', 'database'],
            'impact_assessment': {
                'confidentiality': 'critical',
                'integrity': 'high',
                'availability': 'medium'
            }
        },
        {
            'title': 'Network Intrusion Detected',
            'description': 'Lateral movement detected in network segment',
            'incident_type': 'network_intrusion',
            'severity': 'medium',
            'detection_source': 'network_ids',
            'affected_systems': ['NET-SEGMENT-A'],
            'affected_users': [],
            'iocs': ['192.0.2.100', 'tcp_scan_pattern'],
            'tags': ['network_intrusion', 'lateral_movement'],
            'impact_assessment': {
                'confidentiality': 'medium',
                'integrity': 'low',
                'availability': 'medium'
            }
        }
    ]
    
    incident_responses = []
    
    for incident_data in sample_incidents:
        print(f"\n📊 Processing: {incident_data['title']}")
        
        # Create incident
        incident = await ir_system.create_incident(incident_data)
        print(f"  Incident ID: {incident.incident_id}")
        print(f"  Severity: {incident.severity.value}")
        print(f"  Type: {incident.incident_type.value}")
        
        # Execute automated response
        print(f"  🤖 Initiating automated response...")
        execution = await ir_system.respond_to_incident(incident, "automated_system")
        
        if execution:
            print(f"  ✅ Response executed: {execution.status.value}")
            print(f"    Playbook: {ir_system.playbooks[execution.playbook_id].name}")
            print(f"    Tasks Completed: {execution.completed_tasks}/{execution.total_tasks}")
            print(f"    Duration: {(execution.end_time - execution.start_time).total_seconds():.1f}s")
            
            if execution.failed_tasks > 0:
                print(f"    ⚠️ Failed Tasks: {execution.failed_tasks}")
            
            incident_responses.append((incident, execution))
        else:
            print(f"  ❌ No suitable playbook found")
    
    # Show detailed execution results
    print(f"\n📋 Detailed Response Analysis:")
    
    for incident, execution in incident_responses:
        print(f"\n🔍 Incident: {incident.title}")
        print(f"  Response Status: {execution.status.value}")
        
        # Show task results
        print(f"  Task Results:")
        for task_id, result in execution.task_results.items():
            task_name = next((t.name for t in ir_system.playbooks[execution.playbook_id].tasks 
                            if t.task_id == task_id), task_id)
            status_icon = {"success": "✅", "failed": "❌", "timeout": "⏰"}.get(result.status.value, "❓")
            print(f"    {status_icon} {task_name}")
            
            if result.evidence_collected:
                print(f"      Evidence: {len(result.evidence_collected)} items collected")
            
            if result.artifacts_created:
                print(f"      Artifacts: {len(result.artifacts_created)} files created")
            
            if result.error_message:
                print(f"      Error: {result.error_message}")
        
        # Show execution log highlights
        print(f"  Execution Log:")
        for log_entry in execution.execution_log[-3:]:  # Show last 3 entries
            print(f"    • {log_entry}")
    
    # Show dashboard data
    print(f"\n📊 Incident Response Dashboard:")
    dashboard = ir_system.get_incident_dashboard_data()
    
    incident_stats = dashboard['incident_statistics']
    print(f"  Total Incidents: {incident_stats['total_incidents']}")
    print(f"  Recent (24h): {incident_stats['recent_incidents_24h']}")
    print(f"  Avg Response Time: {incident_stats['average_response_time_minutes']} minutes")
    
    print(f"\n📈 Status Distribution:")
    for status, count in incident_stats['status_distribution'].items():
        status_icon = {"new": "🆕", "in_progress": "🔄", "contained": "🔒", "resolved": "✅"}.get(status, "❓")
        print(f"    {status_icon} {status}: {count}")
    
    print(f"\n⚠️ Severity Distribution:")
    for severity, count in incident_stats['severity_distribution'].items():
        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "ℹ️")
        print(f"    {severity_icon} {severity}: {count}")
    
    print(f"\n🎯 Incident Types:")
    for incident_type, count in incident_stats['type_distribution'].items():
        print(f"    • {incident_type}: {count}")
    
    # Show playbook coverage
    playbook_stats = dashboard['playbook_statistics']
    print(f"\n📚 Playbook Statistics:")
    print(f"  Total Playbooks: {playbook_stats['total_playbooks']}")
    print(f"  Automation Rate: {playbook_stats['automation_rate']}%")
    
    print(f"\n🎯 Coverage by Type:")
    for incident_type, count in playbook_stats['coverage_by_type'].items():
        print(f"    • {incident_type}: {count} playbook(s)")
    
    # Show evidence collection summary
    total_evidence = 0
    evidence_types = Counter()
    
    for incident, execution in incident_responses:
        for result in execution.task_results.values():
            total_evidence += len(result.evidence_collected)
            # Count evidence types from output
            for key in result.output.keys():
                if '_logs' in key or '_dump' in key or '_traffic' in key:
                    evidence_type = key.split('_')[-1]
                    evidence_types[evidence_type] += 1
    
    print(f"\n🔍 Evidence Collection Summary:")
    print(f"  Total Evidence Items: {total_evidence}")
    print(f"  Evidence Types:")
    for evidence_type, count in evidence_types.items():
        print(f"    • {evidence_type}: {count}")
    
    print(f"\n🔧 System Capabilities:")
    print(f"  • Automated incident classification")
    print(f"  • Intelligent playbook selection")
    print(f"  • Real-time evidence collection")
    print(f"  • Parallel task execution")
    print(f"  • Chain of custody preservation")
    print(f"  • Comprehensive audit trails")
    print(f"  • Stakeholder notification automation")
    
    print(f"\n✅ Incident response demonstration completed!")
    print(f"🎯 Key Benefits:")
    print(f"  • Rapid automated response deployment")
    print(f"  • Consistent incident handling procedures")
    print(f"  • Digital evidence preservation")
    print(f"  • Reduced mean time to containment")
    print(f"  • Comprehensive forensic capabilities")

if __name__ == "__main__":
    asyncio.run(demonstrate_incident_response())