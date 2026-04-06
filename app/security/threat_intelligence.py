#!/usr/bin/env python3
"""
AIOps Threat Intelligence Integration System
Advanced threat intelligence integration with IOC matching, threat correlation, and automated response

Features:
- Multi-source threat intelligence feeds integration
- Indicators of Compromise (IOC) matching and correlation
- Threat actor profiling and campaign tracking
- Automated threat hunting and detection
- Threat intelligence sharing and collaboration
- Real-time threat landscape analysis
"""

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import re
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('threat_intelligence')

class IOCType(Enum):
    """Types of Indicators of Compromise"""
    IP_ADDRESS = "ip_address"
    DOMAIN = "domain"
    URL = "url"
    FILE_HASH = "file_hash"
    EMAIL = "email"
    REGISTRY_KEY = "registry_key"
    MUTEX = "mutex"
    USER_AGENT = "user_agent"
    SSL_CERTIFICATE = "ssl_certificate"
    ASN = "asn"

class ThreatType(Enum):
    """Types of threats"""
    MALWARE = "malware"
    PHISHING = "phishing"
    BOTNET = "botnet"
    APT = "apt"
    RANSOMWARE = "ransomware"
    CREDENTIAL_THEFT = "credential_theft"
    DATA_EXFILTRATION = "data_exfiltration"
    INSIDER_THREAT = "insider_threat"
    SUPPLY_CHAIN = "supply_chain"
    CRYPTOCURRENCY_MINING = "cryptocurrency_mining"

class ThreatSeverity(Enum):
    """Threat severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

class FeedType(Enum):
    """Threat intelligence feed types"""
    COMMERCIAL = "commercial"
    OPEN_SOURCE = "open_source"
    GOVERNMENT = "government"
    INDUSTRY = "industry"
    INTERNAL = "internal"
    COMMUNITY = "community"

class ConfidenceLevel(Enum):
    """Confidence levels for threat intelligence"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

@dataclass
class IOC:
    """Indicator of Compromise"""
    ioc_id: str
    ioc_type: IOCType
    value: str
    threat_types: List[ThreatType]
    severity: ThreatSeverity
    confidence: ConfidenceLevel
    first_seen: datetime
    last_seen: datetime
    source: str
    description: str
    tags: List[str] = field(default_factory=list)
    tlp: str = "WHITE"  # Traffic Light Protocol
    kill_chain_phases: List[str] = field(default_factory=list)
    mitre_techniques: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    false_positive: bool = False

@dataclass
class ThreatActor:
    """Threat actor profile"""
    actor_id: str
    name: str
    aliases: List[str]
    group_type: str  # APT, criminal, hacktivist, etc.
    origin_country: Optional[str]
    motivation: List[str]  # financial, espionage, disruption, etc.
    sophistication: str  # novice, intermediate, expert, strategic
    first_observed: datetime
    last_activity: datetime
    target_sectors: List[str]
    target_countries: List[str]
    techniques: List[str]  # MITRE ATT&CK techniques
    malware_families: List[str]
    campaigns: List[str]
    description: str
    is_active: bool = True

@dataclass
class ThreatCampaign:
    """Threat campaign information"""
    campaign_id: str
    name: str
    threat_actor: Optional[str]
    start_date: datetime
    end_date: Optional[datetime]
    description: str
    objectives: List[str]
    target_sectors: List[str]
    target_countries: List[str]
    techniques: List[str]
    iocs: List[str]  # IOC IDs
    malware_families: List[str]
    attribution_confidence: ConfidenceLevel
    is_active: bool = True

@dataclass
class ThreatIntelligenceFeed:
    """Threat intelligence feed configuration"""
    feed_id: str
    name: str
    feed_type: FeedType
    url: Optional[str]
    api_key: Optional[str]
    update_frequency_hours: int
    data_format: str  # json, xml, csv, stix
    is_active: bool
    last_updated: Optional[datetime]
    ioc_count: int = 0
    reliability_score: float = 0.0  # 0-100

@dataclass
class ThreatMatch:
    """Threat match result"""
    match_id: str
    ioc_id: str
    matched_value: str
    source_event: Dict[str, Any]
    match_timestamp: datetime
    severity: ThreatSeverity
    confidence: ConfidenceLevel
    threat_types: List[ThreatType]
    context: Dict[str, Any]
    false_positive: bool = False
    investigated: bool = False

class IOCMatcher:
    """IOC matching engine"""
    
    def __init__(self):
        self.iocs = {}  # ioc_id -> IOC
        self.ip_iocs = set()
        self.domain_iocs = set()
        self.hash_iocs = set()
        self.url_patterns = []
        
        logger.info("IOC matcher initialized")
    
    def add_ioc(self, ioc: IOC):
        """Add IOC to matcher"""
        self.iocs[ioc.ioc_id] = ioc
        
        # Add to type-specific collections for fast matching
        if ioc.ioc_type == IOCType.IP_ADDRESS:
            self.ip_iocs.add(ioc.value)
        elif ioc.ioc_type == IOCType.DOMAIN:
            self.domain_iocs.add(ioc.value.lower())
        elif ioc.ioc_type == IOCType.FILE_HASH:
            self.hash_iocs.add(ioc.value.lower())
        elif ioc.ioc_type == IOCType.URL:
            self.url_patterns.append((ioc.ioc_id, re.compile(re.escape(ioc.value), re.IGNORECASE)))
        
        logger.debug(f"Added IOC {ioc.ioc_id}: {ioc.value}")
    
    def match_ip_address(self, ip: str) -> List[str]:
        """Match IP address against IOCs"""
        matches = []
        
        # Direct match
        if ip in self.ip_iocs:
            matches.extend([ioc_id for ioc_id, ioc in self.iocs.items() 
                          if ioc.ioc_type == IOCType.IP_ADDRESS and ioc.value == ip])
        
        # CIDR range matching
        try:
            ip_obj = ipaddress.ip_address(ip)
            for ioc_id, ioc in self.iocs.items():
                if ioc.ioc_type == IOCType.IP_ADDRESS and '/' in ioc.value:
                    try:
                        if ip_obj in ipaddress.ip_network(ioc.value, strict=False):
                            matches.append(ioc_id)
                    except ValueError:
                        continue
        except ValueError:
            pass
        
        return matches
    
    def match_domain(self, domain: str) -> List[str]:
        """Match domain against IOCs"""
        matches = []
        domain_lower = domain.lower()
        
        # Direct match
        if domain_lower in self.domain_iocs:
            matches.extend([ioc_id for ioc_id, ioc in self.iocs.items() 
                          if ioc.ioc_type == IOCType.DOMAIN and ioc.value.lower() == domain_lower])
        
        # Subdomain matching
        for ioc_id, ioc in self.iocs.items():
            if ioc.ioc_type == IOCType.DOMAIN:
                ioc_domain = ioc.value.lower()
                if domain_lower.endswith('.' + ioc_domain) or ioc_domain.endswith('.' + domain_lower):
                    matches.append(ioc_id)
        
        return matches
    
    def match_file_hash(self, file_hash: str) -> List[str]:
        """Match file hash against IOCs"""
        hash_lower = file_hash.lower()
        if hash_lower in self.hash_iocs:
            return [ioc_id for ioc_id, ioc in self.iocs.items() 
                   if ioc.ioc_type == IOCType.FILE_HASH and ioc.value.lower() == hash_lower]
        return []
    
    def match_url(self, url: str) -> List[str]:
        """Match URL against IOCs"""
        matches = []
        
        for ioc_id, pattern in self.url_patterns:
            if pattern.search(url):
                matches.append(ioc_id)
        
        return matches
    
    def match_event(self, event_data: Dict[str, Any]) -> List[ThreatMatch]:
        """Match event data against all IOCs"""
        matches = []
        match_timestamp = datetime.now()
        
        # Extract potential IOCs from event
        potential_ips = self._extract_ips(event_data)
        potential_domains = self._extract_domains(event_data)
        potential_hashes = self._extract_hashes(event_data)
        potential_urls = self._extract_urls(event_data)
        
        # Match IPs
        for ip in potential_ips:
            ioc_ids = self.match_ip_address(ip)
            for ioc_id in ioc_ids:
                ioc = self.iocs[ioc_id]
                match = ThreatMatch(
                    match_id=str(uuid.uuid4()),
                    ioc_id=ioc_id,
                    matched_value=ip,
                    source_event=event_data,
                    match_timestamp=match_timestamp,
                    severity=ioc.severity,
                    confidence=ioc.confidence,
                    threat_types=ioc.threat_types,
                    context={'matched_type': 'ip_address', 'ioc_value': ioc.value}
                )
                matches.append(match)
        
        # Match domains
        for domain in potential_domains:
            ioc_ids = self.match_domain(domain)
            for ioc_id in ioc_ids:
                ioc = self.iocs[ioc_id]
                match = ThreatMatch(
                    match_id=str(uuid.uuid4()),
                    ioc_id=ioc_id,
                    matched_value=domain,
                    source_event=event_data,
                    match_timestamp=match_timestamp,
                    severity=ioc.severity,
                    confidence=ioc.confidence,
                    threat_types=ioc.threat_types,
                    context={'matched_type': 'domain', 'ioc_value': ioc.value}
                )
                matches.append(match)
        
        # Match hashes
        for file_hash in potential_hashes:
            ioc_ids = self.match_file_hash(file_hash)
            for ioc_id in ioc_ids:
                ioc = self.iocs[ioc_id]
                match = ThreatMatch(
                    match_id=str(uuid.uuid4()),
                    ioc_id=ioc_id,
                    matched_value=file_hash,
                    source_event=event_data,
                    match_timestamp=match_timestamp,
                    severity=ioc.severity,
                    confidence=ioc.confidence,
                    threat_types=ioc.threat_types,
                    context={'matched_type': 'file_hash', 'ioc_value': ioc.value}
                )
                matches.append(match)
        
        # Match URLs
        for url in potential_urls:
            ioc_ids = self.match_url(url)
            for ioc_id in ioc_ids:
                ioc = self.iocs[ioc_id]
                match = ThreatMatch(
                    match_id=str(uuid.uuid4()),
                    ioc_id=ioc_id,
                    matched_value=url,
                    source_event=event_data,
                    match_timestamp=match_timestamp,
                    severity=ioc.severity,
                    confidence=ioc.confidence,
                    threat_types=ioc.threat_types,
                    context={'matched_type': 'url', 'ioc_value': ioc.value}
                )
                matches.append(match)
        
        return matches
    
    def _extract_ips(self, data: Dict[str, Any]) -> Set[str]:
        """Extract IP addresses from event data"""
        ips = set()
        ip_pattern = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
        
        # Convert data to string and extract IPs
        data_str = json.dumps(data, default=str)
        found_ips = ip_pattern.findall(data_str)
        
        for ip in found_ips:
            try:
                # Validate IP address
                ipaddress.ip_address(ip)
                # Filter out private/reserved IPs for external threat matching
                ip_obj = ipaddress.ip_address(ip)
                if not (ip_obj.is_private or ip_obj.is_reserved or ip_obj.is_loopback):
                    ips.add(ip)
            except ValueError:
                continue
        
        return ips
    
    def _extract_domains(self, data: Dict[str, Any]) -> Set[str]:
        """Extract domains from event data"""
        domains = set()
        domain_pattern = re.compile(r'\b[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}\b')
        
        data_str = json.dumps(data, default=str)
        found_domains = domain_pattern.findall(data_str)
        
        for domain_match in found_domains:
            if isinstance(domain_match, tuple):
                domain = domain_match[0] if domain_match else ""
            else:
                domain = domain_match
            
            if domain and '.' in domain:
                domains.add(domain.lower())
        
        return domains
    
    def _extract_hashes(self, data: Dict[str, Any]) -> Set[str]:
        """Extract file hashes from event data"""
        hashes = set()
        # MD5, SHA1, SHA256 patterns
        hash_patterns = [
            re.compile(r'\b[a-fA-F0-9]{32}\b'),  # MD5
            re.compile(r'\b[a-fA-F0-9]{40}\b'),  # SHA1
            re.compile(r'\b[a-fA-F0-9]{64}\b'),  # SHA256
        ]
        
        data_str = json.dumps(data, default=str)
        
        for pattern in hash_patterns:
            found_hashes = pattern.findall(data_str)
            hashes.update(h.lower() for h in found_hashes)
        
        return hashes
    
    def _extract_urls(self, data: Dict[str, Any]) -> Set[str]:
        """Extract URLs from event data"""
        urls = set()
        url_pattern = re.compile(r'https?://[^\s<>"]+', re.IGNORECASE)
        
        data_str = json.dumps(data, default=str)
        found_urls = url_pattern.findall(data_str)
        
        urls.update(found_urls)
        
        return urls

class ThreatIntelligenceManager:
    """Threat intelligence management system"""
    
    def __init__(self):
        self.feeds = {}  # feed_id -> ThreatIntelligenceFeed
        self.ioc_matcher = IOCMatcher()
        self.threat_actors = {}  # actor_id -> ThreatActor
        self.campaigns = {}  # campaign_id -> ThreatCampaign
        self.matches = []  # ThreatMatch objects
        
        # Initialize with sample data
        self._load_sample_threat_data()
        
        logger.info("Threat intelligence manager initialized")
    
    def _load_sample_threat_data(self):
        """Load sample threat intelligence data"""
        
        # Sample IOCs
        sample_iocs = [
            IOC(
                ioc_id="IOC-001",
                ioc_type=IOCType.IP_ADDRESS,
                value="192.0.2.100",
                threat_types=[ThreatType.MALWARE, ThreatType.BOTNET],
                severity=ThreatSeverity.HIGH,
                confidence=ConfidenceLevel.HIGH,
                first_seen=datetime.now() - timedelta(days=30),
                last_seen=datetime.now() - timedelta(days=1),
                source="threat_feed_alpha",
                description="C2 server for banking trojan",
                tags=["banking", "trojan", "c2"],
                kill_chain_phases=["command-and-control"],
                mitre_techniques=["T1071.001"]
            ),
            IOC(
                ioc_id="IOC-002",
                ioc_type=IOCType.DOMAIN,
                value="malicious-example.com",
                threat_types=[ThreatType.PHISHING],
                severity=ThreatSeverity.MEDIUM,
                confidence=ConfidenceLevel.MEDIUM,
                first_seen=datetime.now() - timedelta(days=15),
                last_seen=datetime.now() - timedelta(hours=6),
                source="phishing_feed",
                description="Phishing domain impersonating bank",
                tags=["phishing", "banking", "credential-theft"],
                kill_chain_phases=["delivery"],
                mitre_techniques=["T1566.002"]
            ),
            IOC(
                ioc_id="IOC-003",
                ioc_type=IOCType.FILE_HASH,
                value="a1b2c3d4e5f6789012345678901234567890abcdefabcdefabcdefabcdefabcd",
                threat_types=[ThreatType.RANSOMWARE],
                severity=ThreatSeverity.CRITICAL,
                confidence=ConfidenceLevel.HIGH,
                first_seen=datetime.now() - timedelta(days=7),
                last_seen=datetime.now() - timedelta(hours=2),
                source="malware_analysis",
                description="Ransomware payload hash",
                tags=["ransomware", "encryption", "payment"],
                kill_chain_phases=["exploitation"],
                mitre_techniques=["T1486"]
            ),
            IOC(
                ioc_id="IOC-004",
                ioc_type=IOCType.URL,
                value="http://suspicious-downloads.example/payload.exe",
                threat_types=[ThreatType.MALWARE],
                severity=ThreatSeverity.HIGH,
                confidence=ConfidenceLevel.MEDIUM,
                first_seen=datetime.now() - timedelta(days=5),
                last_seen=datetime.now() - timedelta(hours=12),
                source="url_analysis",
                description="Malware download URL",
                tags=["malware", "download", "executable"],
                kill_chain_phases=["delivery"],
                mitre_techniques=["T1204.002"]
            ),
            IOC(
                ioc_id="IOC-005",
                ioc_type=IOCType.EMAIL,
                value="admin@fake-bank.example",
                threat_types=[ThreatType.PHISHING],
                severity=ThreatSeverity.MEDIUM,
                confidence=ConfidenceLevel.HIGH,
                first_seen=datetime.now() - timedelta(days=20),
                last_seen=datetime.now() - timedelta(hours=8),
                source="email_analysis",
                description="Phishing email sender",
                tags=["phishing", "email", "social-engineering"],
                kill_chain_phases=["delivery"],
                mitre_techniques=["T1566.001"]
            )
        ]
        
        # Add IOCs to matcher
        for ioc in sample_iocs:
            self.ioc_matcher.add_ioc(ioc)
        
        # Sample threat actors
        sample_actors = [
            ThreatActor(
                actor_id="ACTOR-001",
                name="APT-Banking",
                aliases=["BankingTrojanGroup", "FinancialThreat"],
                group_type="APT",
                origin_country="Unknown",
                motivation=["financial"],
                sophistication="expert",
                first_observed=datetime.now() - timedelta(days=365),
                last_activity=datetime.now() - timedelta(days=1),
                target_sectors=["financial", "retail"],
                target_countries=["US", "EU", "CA"],
                techniques=["T1071.001", "T1055", "T1083"],
                malware_families=["banking_trojan_v1", "stealer_v2"],
                campaigns=["CAMPAIGN-001"],
                description="Advanced persistent threat group targeting financial institutions"
            ),
            ThreatActor(
                actor_id="ACTOR-002",
                name="RansomCorp",
                aliases=["CryptoLock", "DataEncryptor"],
                group_type="criminal",
                origin_country="Eastern Europe",
                motivation=["financial"],
                sophistication="intermediate",
                first_observed=datetime.now() - timedelta(days=180),
                last_activity=datetime.now() - timedelta(hours=6),
                target_sectors=["healthcare", "education", "manufacturing"],
                target_countries=["US", "CA", "AU"],
                techniques=["T1486", "T1082", "T1016"],
                malware_families=["ransomware_v3"],
                campaigns=["CAMPAIGN-002"],
                description="Ransomware-as-a-Service operation"
            )
        ]
        
        for actor in sample_actors:
            self.threat_actors[actor.actor_id] = actor
        
        # Sample campaigns
        sample_campaigns = [
            ThreatCampaign(
                campaign_id="CAMPAIGN-001",
                name="Operation BankDrain",
                threat_actor="ACTOR-001",
                start_date=datetime.now() - timedelta(days=60),
                end_date=None,
                description="Targeted banking trojan campaign",
                objectives=["credential_theft", "financial_fraud"],
                target_sectors=["financial"],
                target_countries=["US", "CA"],
                techniques=["T1071.001", "T1055"],
                iocs=["IOC-001", "IOC-002"],
                malware_families=["banking_trojan_v1"],
                attribution_confidence=ConfidenceLevel.HIGH
            ),
            ThreatCampaign(
                campaign_id="CAMPAIGN-002",
                name="CryptoLock2025",
                threat_actor="ACTOR-002",
                start_date=datetime.now() - timedelta(days=30),
                end_date=None,
                description="Large-scale ransomware campaign",
                objectives=["financial_gain", "disruption"],
                target_sectors=["healthcare", "education"],
                target_countries=["US", "EU"],
                techniques=["T1486", "T1082"],
                iocs=["IOC-003", "IOC-004"],
                malware_families=["ransomware_v3"],
                attribution_confidence=ConfidenceLevel.MEDIUM
            )
        ]
        
        for campaign in sample_campaigns:
            self.campaigns[campaign.campaign_id] = campaign
        
        # Sample feeds
        sample_feeds = [
            ThreatIntelligenceFeed(
                feed_id="FEED-001",
                name="AlphaThreat Intelligence",
                feed_type=FeedType.COMMERCIAL,
                url="https://api.alphathreats.com/v1/iocs",
                api_key="demo_key_123",
                update_frequency_hours=6,
                data_format="json",
                is_active=True,
                last_updated=datetime.now() - timedelta(hours=2),
                ioc_count=1250,
                reliability_score=95.0
            ),
            ThreatIntelligenceFeed(
                feed_id="FEED-002",
                name="Open Threat Exchange",
                feed_type=FeedType.OPEN_SOURCE,
                url="https://otx.alienvault.com/api/v1/indicators",
                api_key=None,
                update_frequency_hours=12,
                data_format="json",
                is_active=True,
                last_updated=datetime.now() - timedelta(hours=8),
                ioc_count=850,
                reliability_score=78.0
            ),
            ThreatIntelligenceFeed(
                feed_id="FEED-003",
                name="Government Threat Feed",
                feed_type=FeedType.GOVERNMENT,
                url="https://feeds.gov.example/threats.xml",
                api_key="classified",
                update_frequency_hours=24,
                data_format="xml",
                is_active=True,
                last_updated=datetime.now() - timedelta(hours=18),
                ioc_count=420,
                reliability_score=98.0
            )
        ]
        
        for feed in sample_feeds:
            self.feeds[feed.feed_id] = feed
        
        logger.info(f"Loaded sample threat data: {len(sample_iocs)} IOCs, {len(sample_actors)} actors, {len(sample_campaigns)} campaigns, {len(sample_feeds)} feeds")
    
    async def process_security_event(self, event_data: Dict[str, Any]) -> List[ThreatMatch]:
        """Process security event for threat intelligence matches"""
        matches = self.ioc_matcher.match_event(event_data)
        
        # Add matches to collection
        self.matches.extend(matches)
        
        # Log matches
        for match in matches:
            logger.warning(f"Threat intelligence match: {match.matched_value} ({match.severity.value})")
        
        return matches
    
    def enrich_with_threat_context(self, match: ThreatMatch) -> Dict[str, Any]:
        """Enrich threat match with additional context"""
        ioc = self.ioc_matcher.iocs.get(match.ioc_id)
        if not ioc:
            return {}
        
        enrichment = {
            'ioc_details': {
                'type': ioc.ioc_type.value,
                'value': ioc.value,
                'description': ioc.description,
                'tags': ioc.tags,
                'kill_chain_phases': ioc.kill_chain_phases,
                'mitre_techniques': ioc.mitre_techniques,
                'first_seen': ioc.first_seen.isoformat(),
                'last_seen': ioc.last_seen.isoformat(),
                'source': ioc.source
            }
        }
        
        # Find related campaigns
        related_campaigns = []
        for campaign in self.campaigns.values():
            if match.ioc_id in campaign.iocs:
                related_campaigns.append({
                    'campaign_id': campaign.campaign_id,
                    'name': campaign.name,
                    'threat_actor': campaign.threat_actor,
                    'objectives': campaign.objectives,
                    'attribution_confidence': campaign.attribution_confidence.value
                })
        
        if related_campaigns:
            enrichment['related_campaigns'] = related_campaigns
        
        # Find threat actor information
        threat_actors = []
        for campaign in related_campaigns:
            if campaign['threat_actor'] and campaign['threat_actor'] in self.threat_actors:
                actor = self.threat_actors[campaign['threat_actor']]
                threat_actors.append({
                    'actor_id': actor.actor_id,
                    'name': actor.name,
                    'aliases': actor.aliases,
                    'group_type': actor.group_type,
                    'sophistication': actor.sophistication,
                    'motivation': actor.motivation,
                    'target_sectors': actor.target_sectors
                })
        
        if threat_actors:
            enrichment['threat_actors'] = threat_actors
        
        return enrichment
    
    def get_threat_landscape_summary(self) -> Dict[str, Any]:
        """Get comprehensive threat landscape summary"""
        
        # IOC statistics
        ioc_stats = {
            'total_iocs': len(self.ioc_matcher.iocs),
            'by_type': {},
            'by_severity': {},
            'by_threat_type': {}
        }
        
        for ioc in self.ioc_matcher.iocs.values():
            # By IOC type
            ioc_type = ioc.ioc_type.value
            ioc_stats['by_type'][ioc_type] = ioc_stats['by_type'].get(ioc_type, 0) + 1
            
            # By severity
            severity = ioc.severity.value
            ioc_stats['by_severity'][severity] = ioc_stats['by_severity'].get(severity, 0) + 1
            
            # By threat type
            for threat_type in ioc.threat_types:
                threat_val = threat_type.value
                ioc_stats['by_threat_type'][threat_val] = ioc_stats['by_threat_type'].get(threat_val, 0) + 1
        
        # Match statistics
        match_stats = {
            'total_matches': len(self.matches),
            'by_severity': {},
            'recent_matches': []
        }
        
        for match in self.matches:
            severity = match.severity.value
            match_stats['by_severity'][severity] = match_stats['by_severity'].get(severity, 0) + 1
        
        # Recent matches (last 10)
        recent_matches = sorted(self.matches, key=lambda m: m.match_timestamp, reverse=True)[:10]
        match_stats['recent_matches'] = [
            {
                'match_id': m.match_id,
                'matched_value': m.matched_value,
                'severity': m.severity.value,
                'threat_types': [t.value for t in m.threat_types],
                'timestamp': m.match_timestamp.isoformat()
            }
            for m in recent_matches
        ]
        
        # Actor statistics
        actor_stats = {
            'total_actors': len(self.threat_actors),
            'by_sophistication': {},
            'by_group_type': {},
            'active_actors': len([a for a in self.threat_actors.values() if a.is_active])
        }
        
        for actor in self.threat_actors.values():
            # By sophistication
            soph = actor.sophistication
            actor_stats['by_sophistication'][soph] = actor_stats['by_sophistication'].get(soph, 0) + 1
            
            # By group type
            group_type = actor.group_type
            actor_stats['by_group_type'][group_type] = actor_stats['by_group_type'].get(group_type, 0) + 1
        
        # Campaign statistics
        campaign_stats = {
            'total_campaigns': len(self.campaigns),
            'active_campaigns': len([c for c in self.campaigns.values() if c.is_active]),
            'by_attribution_confidence': {}
        }
        
        for campaign in self.campaigns.values():
            confidence = campaign.attribution_confidence.value
            campaign_stats['by_attribution_confidence'][confidence] = campaign_stats['by_attribution_confidence'].get(confidence, 0) + 1
        
        # Feed statistics
        feed_stats = {
            'total_feeds': len(self.feeds),
            'active_feeds': len([f for f in self.feeds.values() if f.is_active]),
            'by_type': {},
            'total_ioc_count': sum(f.ioc_count for f in self.feeds.values()),
            'avg_reliability': sum(f.reliability_score for f in self.feeds.values()) / len(self.feeds) if self.feeds else 0
        }
        
        for feed in self.feeds.values():
            feed_type = feed.feed_type.value
            feed_stats['by_type'][feed_type] = feed_stats['by_type'].get(feed_type, 0) + 1
        
        return {
            'summary_timestamp': datetime.now().isoformat(),
            'ioc_statistics': ioc_stats,
            'match_statistics': match_stats,
            'actor_statistics': actor_stats,
            'campaign_statistics': campaign_stats,
            'feed_statistics': feed_stats,
            'top_threats': self._get_top_threats(),
            'trending_indicators': self._get_trending_indicators()
        }
    
    def _get_top_threats(self) -> List[Dict[str, Any]]:
        """Get top threats based on recent activity"""
        threat_scores = defaultdict(float)
        
        # Score based on recent matches
        recent_cutoff = datetime.now() - timedelta(days=7)
        for match in self.matches:
            if match.match_timestamp > recent_cutoff:
                for threat_type in match.threat_types:
                    severity_multiplier = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}.get(match.severity.value, 1)
                    threat_scores[threat_type.value] += severity_multiplier
        
        # Sort by score and return top 5
        top_threats = sorted(threat_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return [
            {
                'threat_type': threat_type,
                'score': score,
                'related_iocs': len([ioc for ioc in self.ioc_matcher.iocs.values() 
                                   if ThreatType(threat_type) in ioc.threat_types])
            }
            for threat_type, score in top_threats
        ]
    
    def _get_trending_indicators(self) -> List[Dict[str, Any]]:
        """Get trending indicators based on recent matches"""
        indicator_counts = defaultdict(int)
        
        recent_cutoff = datetime.now() - timedelta(hours=24)
        for match in self.matches:
            if match.match_timestamp > recent_cutoff:
                indicator_counts[match.matched_value] += 1
        
        # Sort by count and return top 10
        trending = sorted(indicator_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        trending_indicators = []
        for indicator, count in trending:
            # Find IOC details
            ioc_details = None
            for ioc in self.ioc_matcher.iocs.values():
                if ioc.value == indicator:
                    ioc_details = {
                        'type': ioc.ioc_type.value,
                        'severity': ioc.severity.value,
                        'threat_types': [t.value for t in ioc.threat_types]
                    }
                    break
            
            trending_indicators.append({
                'indicator': indicator,
                'match_count': count,
                'details': ioc_details
            })
        
        return trending_indicators

async def demonstrate_threat_intelligence():
    """Demonstrate the threat intelligence integration system"""
    print("AIOps Threat Intelligence Integration System Demo")
    print("=" * 62)
    
    # Initialize threat intelligence manager
    ti_manager = ThreatIntelligenceManager()
    
    print("🔍 Threat intelligence system initialized with sample data\n")
    
    # Show initial statistics
    summary = ti_manager.get_threat_landscape_summary()
    
    print("📊 Threat Landscape Overview:")
    print(f"  IOCs: {summary['ioc_statistics']['total_iocs']}")
    print(f"  Threat Actors: {summary['actor_statistics']['total_actors']}")
    print(f"  Active Campaigns: {summary['campaign_statistics']['active_campaigns']}")
    print(f"  Intelligence Feeds: {summary['feed_statistics']['active_feeds']}")
    
    print(f"\n📈 IOC Distribution:")
    ioc_stats = summary['ioc_statistics']
    print(f"  By Type:")
    for ioc_type, count in ioc_stats['by_type'].items():
        print(f"    {ioc_type}: {count}")
    
    print(f"  By Severity:")
    for severity, count in ioc_stats['by_severity'].items():
        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "ℹ️")
        print(f"    {icon} {severity}: {count}")
    
    # Simulate security events for threat matching
    print(f"\n🚨 Processing security events for threat matching...")
    
    sample_events = [
        {
            'event_id': 'EVT-001',
            'timestamp': datetime.now().isoformat(),
            'event_type': 'network_connection',
            'source_ip': '10.0.0.100',
            'destination_ip': '192.0.2.100',  # This matches IOC-001
            'destination_port': 443,
            'protocol': 'TCP',
            'user_id': 'john.doe'
        },
        {
            'event_id': 'EVT-002',
            'timestamp': datetime.now().isoformat(),
            'event_type': 'dns_query',
            'query': 'malicious-example.com',  # This matches IOC-002
            'source_ip': '10.0.0.101',
            'user_id': 'jane.smith'
        },
        {
            'event_id': 'EVT-003',
            'timestamp': datetime.now().isoformat(),
            'event_type': 'file_scan',
            'file_path': '/tmp/suspicious.exe',
            'file_hash': 'a1b2c3d4e5f6789012345678901234567890abcdefabcdefabcdefabcdefabcd',  # Matches IOC-003
            'user_id': 'admin'
        },
        {
            'event_id': 'EVT-004',
            'timestamp': datetime.now().isoformat(),
            'event_type': 'web_request',
            'url': 'http://suspicious-downloads.example/payload.exe',  # Matches IOC-004
            'source_ip': '10.0.0.102',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        },
        {
            'event_id': 'EVT-005',
            'timestamp': datetime.now().isoformat(),
            'event_type': 'email_received',
            'sender': 'admin@fake-bank.example',  # Matches IOC-005
            'recipient': 'victim@company.com',
            'subject': 'Urgent: Verify your account'
        }
    ]
    
    all_matches = []
    
    for event in sample_events:
        print(f"  Processing event {event['event_id']}...")
        matches = await ti_manager.process_security_event(event)
        all_matches.extend(matches)
        
        if matches:
            print(f"    ⚠️ {len(matches)} threat(s) detected!")
            for match in matches:
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(match.severity.value, "ℹ️")
                print(f"      {severity_icon} {match.matched_value} ({match.severity.value})")
        else:
            print(f"    ✅ No threats detected")
    
    print(f"\n🎯 Threat Match Summary:")
    print(f"  Total Matches: {len(all_matches)}")
    
    if all_matches:
        match_by_severity = Counter(m.severity.value for m in all_matches)
        for severity, count in match_by_severity.items():
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "ℹ️")
            print(f"    {icon} {severity}: {count}")
        
        # Show detailed match information
        print(f"\n📋 Detailed Match Analysis:")
        for i, match in enumerate(all_matches[:3], 1):  # Show first 3 matches
            print(f"  Match {i}: {match.matched_value}")
            print(f"    Severity: {match.severity.value}")
            print(f"    Threat Types: {', '.join(t.value for t in match.threat_types)}")
            print(f"    Confidence: {match.confidence.value}")
            
            # Get enrichment data
            enrichment = ti_manager.enrich_with_threat_context(match)
            if 'related_campaigns' in enrichment:
                campaigns = enrichment['related_campaigns']
                print(f"    Related Campaigns: {', '.join(c['name'] for c in campaigns)}")
            
            if 'threat_actors' in enrichment:
                actors = enrichment['threat_actors']
                print(f"    Threat Actors: {', '.join(a['name'] for a in actors)}")
    
    # Show threat intelligence feeds
    print(f"\n📡 Threat Intelligence Feeds:")
    for feed in ti_manager.feeds.values():
        status_icon = "🟢" if feed.is_active else "🔴"
        print(f"  {status_icon} {feed.name} ({feed.feed_type.value})")
        print(f"      IOCs: {feed.ioc_count}, Reliability: {feed.reliability_score}%")
        print(f"      Last Updated: {feed.last_updated.strftime('%Y-%m-%d %H:%M') if feed.last_updated else 'Never'}")
    
    # Show threat actors and campaigns
    print(f"\n👥 Active Threat Actors:")
    for actor in ti_manager.threat_actors.values():
        if actor.is_active:
            print(f"  • {actor.name} ({actor.group_type})")
            print(f"    Sophistication: {actor.sophistication}")
            print(f"    Targets: {', '.join(actor.target_sectors)}")
            print(f"    Last Activity: {actor.last_activity.strftime('%Y-%m-%d')}")
    
    print(f"\n🎯 Active Campaigns:")
    for campaign in ti_manager.campaigns.values():
        if campaign.is_active:
            print(f"  • {campaign.name}")
            if campaign.threat_actor:
                actor_name = ti_manager.threat_actors.get(campaign.threat_actor, {}).name or "Unknown"
                print(f"    Actor: {actor_name}")
            print(f"    Objectives: {', '.join(campaign.objectives)}")
            print(f"    Attribution Confidence: {campaign.attribution_confidence.value}")
    
    # Get updated threat landscape
    updated_summary = ti_manager.get_threat_landscape_summary()
    
    print(f"\n📊 Updated Threat Intelligence Summary:")
    print(f"  Total Matches: {updated_summary['match_statistics']['total_matches']}")
    
    if updated_summary['match_statistics']['total_matches'] > 0:
        print(f"  Match Distribution:")
        for severity, count in updated_summary['match_statistics']['by_severity'].items():
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "ℹ️")
            print(f"    {icon} {severity}: {count}")
    
    # Show top threats
    top_threats = updated_summary['top_threats']
    if top_threats:
        print(f"\n🔥 Top Threats (Last 7 days):")
        for threat in top_threats[:3]:
            print(f"  • {threat['threat_type']} (Score: {threat['score']}, IOCs: {threat['related_iocs']})")
    
    # Show trending indicators
    trending = updated_summary['trending_indicators']
    if trending:
        print(f"\n📈 Trending Indicators (Last 24 hours):")
        for indicator in trending[:3]:
            print(f"  • {indicator['indicator']} ({indicator['match_count']} matches)")
            if indicator['details']:
                details = indicator['details']
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(details['severity'], "ℹ️")
                print(f"    {severity_icon} {details['type']} - {details['severity']}")
    
    print(f"\n🔧 System Capabilities:")
    print(f"  • Multi-source threat intelligence aggregation")
    print(f"  • Real-time IOC matching and correlation")
    print(f"  • Threat actor and campaign tracking")
    print(f"  • Contextual threat enrichment")
    print(f"  • MITRE ATT&CK framework integration")
    print(f"  • Automated threat hunting and detection")
    
    print(f"\n✅ Threat intelligence integration demonstration completed!")
    print(f"🎯 Key Benefits:")
    print(f"  • Proactive threat detection and early warning")
    print(f"  • Contextual threat intelligence enrichment")
    print(f"  • Automated indicator matching and correlation")
    print(f"  • Threat landscape visibility and analysis")
    print(f"  • Attribution and campaign tracking")

if __name__ == "__main__":
    asyncio.run(demonstrate_threat_intelligence())