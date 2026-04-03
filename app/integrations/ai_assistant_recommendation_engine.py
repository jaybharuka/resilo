#!/usr/bin/env python3
"""
AIOps Bot - AI Assistant & Recommendation Engine
Conversational AI interface, intelligent recommendations, and natural language operations
"""

import asyncio
import json
import re
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from collections import defaultdict, deque
import statistics
import sqlite3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RecommendationType(Enum):
    PERFORMANCE = "performance"
    COST_OPTIMIZATION = "cost_optimization"
    SECURITY = "security"
    AUTOMATION = "automation"
    CAPACITY_PLANNING = "capacity_planning"
    TROUBLESHOOTING = "troubleshooting"

class RecommendationPriority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class ConversationContext(Enum):
    GENERAL = "general"
    INCIDENT = "incident"
    MONITORING = "monitoring"
    DEPLOYMENT = "deployment"
    OPTIMIZATION = "optimization"
    SECURITY = "security"

@dataclass
class Recommendation:
    """AI-generated recommendation"""
    recommendation_id: str
    title: str
    description: str
    recommendation_type: RecommendationType
    priority: RecommendationPriority
    confidence: float
    potential_impact: str
    estimated_savings: Optional[float]
    implementation_steps: List[str]
    risk_assessment: str
    data_sources: List[str]
    created_at: datetime
    expires_at: Optional[datetime]

@dataclass
class ConversationMessage:
    """Conversation message between user and AI assistant"""
    message_id: str
    user_input: str
    ai_response: str
    context: ConversationContext
    intent: str
    entities: Dict[str, Any]
    confidence: float
    timestamp: datetime
    follow_up_suggestions: List[str]

@dataclass
class UserProfile:
    """User profile for personalized interactions"""
    user_id: str
    name: str
    role: str  # admin, operator, analyst, etc.
    preferences: Dict[str, Any]
    interaction_history: List[str]
    expertise_level: str  # beginner, intermediate, expert
    favorite_topics: List[str]
    notification_preferences: Dict[str, bool]

class NaturalLanguageProcessor:
    """Natural Language Processing for AI Assistant"""
    
    def __init__(self):
        """Initialize NLP processor"""
        self.intent_patterns = self._initialize_intent_patterns()
        self.entity_patterns = self._initialize_entity_patterns()
        self.response_templates = self._initialize_response_templates()
        
        logger.info("Natural Language Processor initialized")
    
    def _initialize_intent_patterns(self) -> Dict[str, List[str]]:
        """Initialize intent recognition patterns"""
        return {
            "status_check": [
                r"what.*(status|health)",
                r"how.*(system|infrastructure|services)",
                r"show me.*(dashboard|overview|summary)",
                r"(check|verify).*(status|health)"
            ],
            "incident_report": [
                r"(alert|incident|problem|issue|error)",
                r"something.*(wrong|broken|down)",
                r"(report|create).*(incident|ticket)",
                r"we have.*(problem|issue)"
            ],
            "performance_query": [
                r"(performance|latency|response time|throughput)",
                r"how fast.*(running|responding)",
                r"(slow|sluggish|performance issues)",
                r"(cpu|memory|disk|network).*(usage|utilization)"
            ],
            "cost_inquiry": [
                r"(cost|expense|budget|billing|money)",
                r"how much.*(spending|costing)",
                r"(save|reduce).*(cost|money)",
                r"(optimization|optimize).*(cost|spending)"
            ],
            "deployment_request": [
                r"(deploy|deployment|release)",
                r"(install|setup|configure)",
                r"(start|launch|run).*(service|application)",
                r"(provision|create).*(resource|instance)"
            ],
            "security_concern": [
                r"(security|vulnerability|threat|attack)",
                r"(breach|intrusion|unauthorized)",
                r"(suspicious|anomaly|unusual).*(activity|behavior)",
                r"(compliance|audit|regulation)"
            ],
            "automation_request": [
                r"(automate|automation|automatic)",
                r"(schedule|recurring|periodic)",
                r"can you.*(do|handle|manage)",
                r"(trigger|execute|run).*(automatically|auto)"
            ],
            "recommendation_request": [
                r"(recommend|suggest|advice|guidance)",
                r"what should.*(do|we do)",
                r"(best practice|optimization|improvement)",
                r"how to.*(improve|optimize|enhance)"
            ],
            "help_request": [
                r"(help|support|assistance)",
                r"how.*(do|can|to)",
                r"(explain|clarify|understand)",
                r"(tutorial|guide|documentation)"
            ]
        }
    
    def _initialize_entity_patterns(self) -> Dict[str, List[str]]:
        """Initialize entity extraction patterns"""
        return {
            "service_name": [
                r"(nginx|apache|mysql|postgres|redis|kafka|elasticsearch)",
                r"(kubernetes|docker|jenkins|grafana|prometheus)",
                r"(application|service|microservice|api)"
            ],
            "metric_type": [
                r"(cpu|memory|ram|disk|storage|network|bandwidth)",
                r"(latency|response time|throughput|requests per second)",
                r"(availability|uptime|downtime|error rate)"
            ],
            "time_period": [
                r"(last|past|previous)\s+(hour|day|week|month|year)",
                r"(today|yesterday|this week|last week)",
                r"(\d+)\s+(minutes?|hours?|days?|weeks?|months?)"
            ],
            "severity_level": [
                r"(critical|high|medium|low|info)",
                r"(urgent|important|normal)",
                r"(severe|moderate|minor)"
            ],
            "location": [
                r"(us-east|us-west|eu-central|asia-pacific)",
                r"(production|staging|development|test)",
                r"(datacenter|region|zone|cluster)"
            ]
        }
    
    def _initialize_response_templates(self) -> Dict[str, List[str]]:
        """Initialize response templates for different intents"""
        return {
            "status_check": [
                "Let me check the current system status for you...",
                "I'll pull up the latest health dashboard...",
                "Here's the current infrastructure overview...",
                "Let me gather the system status information..."
            ],
            "incident_report": [
                "I understand there's an incident. Let me help you with that...",
                "I'll create an incident report and start the investigation...",
                "Let me check for any related alerts or anomalies...",
                "I'm analyzing the situation and will provide recommendations..."
            ],
            "performance_query": [
                "Let me analyze the performance metrics for you...",
                "I'll check the latest performance data...",
                "Here's what I found regarding system performance...",
                "Let me examine the performance trends..."
            ],
            "cost_inquiry": [
                "I'll analyze the cost and billing information...",
                "Let me check the current spending patterns...",
                "Here's the cost analysis you requested...",
                "I'll provide cost optimization recommendations..."
            ],
            "deployment_request": [
                "I can help you with the deployment process...",
                "Let me guide you through the deployment steps...",
                "I'll check the deployment requirements and resources...",
                "Here's the deployment plan I've prepared..."
            ],
            "security_concern": [
                "I take security concerns very seriously. Let me investigate...",
                "I'll check for security threats and vulnerabilities...",
                "Let me analyze the security posture and compliance status...",
                "I'm scanning for any security-related issues..."
            ],
            "automation_request": [
                "I can help you automate that process...",
                "Let me create an automation workflow for you...",
                "I'll set up the automation according to your requirements...",
                "Here's how we can automate this task..."
            ],
            "recommendation_request": [
                "Based on the current data, here are my recommendations...",
                "I've analyzed the situation and have several suggestions...",
                "Let me provide some optimization recommendations...",
                "Here are the best practices I recommend..."
            ],
            "help_request": [
                "I'm here to help! Let me explain that for you...",
                "I'll provide detailed guidance on this topic...",
                "Here's what you need to know...",
                "Let me walk you through this step by step..."
            ]
        }
    
    async def process_input(self, user_input: str, context: ConversationContext = ConversationContext.GENERAL) -> Dict[str, Any]:
        """Process user input and extract intent and entities"""
        try:
            # Clean and normalize input
            cleaned_input = self._clean_input(user_input)
            
            # Extract intent
            intent, intent_confidence = self._extract_intent(cleaned_input)
            
            # Extract entities
            entities = self._extract_entities(cleaned_input)
            
            # Determine context if not provided
            if context == ConversationContext.GENERAL:
                context = self._determine_context(intent, entities)
            
            return {
                "intent": intent,
                "intent_confidence": intent_confidence,
                "entities": entities,
                "context": context,
                "cleaned_input": cleaned_input
            }
            
        except Exception as e:
            logger.error(f"Failed to process input: {e}")
            return {
                "intent": "unknown",
                "intent_confidence": 0.0,
                "entities": {},
                "context": ConversationContext.GENERAL,
                "cleaned_input": user_input
            }
    
    def _clean_input(self, text: str) -> str:
        """Clean and normalize input text"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove special characters (keep alphanumeric and common punctuation)
        text = re.sub(r'[^\w\s\-\.\?\!]', '', text)
        
        return text
    
    def _extract_intent(self, text: str) -> Tuple[str, float]:
        """Extract intent from text using pattern matching"""
        intent_scores = {}
        
        for intent, patterns in self.intent_patterns.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    score += 1
            
            if score > 0:
                # Normalize score based on number of patterns
                intent_scores[intent] = score / len(patterns)
        
        if intent_scores:
            # Return intent with highest score
            best_intent = max(intent_scores, key=intent_scores.get)
            confidence = intent_scores[best_intent]
            return best_intent, confidence
        else:
            return "unknown", 0.0
    
    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract entities from text using pattern matching"""
        entities = {}
        
        for entity_type, patterns in self.entity_patterns.items():
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, text, re.IGNORECASE)
                matches.extend(found)
            
            if matches:
                entities[entity_type] = list(set(matches))  # Remove duplicates
        
        return entities
    
    def _determine_context(self, intent: str, entities: Dict[str, List[str]]) -> ConversationContext:
        """Determine conversation context based on intent and entities"""
        if intent in ["incident_report", "security_concern"]:
            return ConversationContext.INCIDENT
        elif intent in ["performance_query", "status_check"]:
            return ConversationContext.MONITORING
        elif intent in ["deployment_request"]:
            return ConversationContext.DEPLOYMENT
        elif intent in ["cost_inquiry", "recommendation_request"]:
            return ConversationContext.OPTIMIZATION
        elif intent in ["security_concern"]:
            return ConversationContext.SECURITY
        else:
            return ConversationContext.GENERAL

class RecommendationEngine:
    """AI-powered recommendation engine"""
    
    def __init__(self):
        """Initialize recommendation engine"""
        self.recommendations: List[Recommendation] = []
        self.recommendation_history = deque(maxlen=1000)
        self.user_feedback = defaultdict(list)
        self.recommendation_rules = self._initialize_recommendation_rules()
        
        logger.info("Recommendation Engine initialized")
    
    def _initialize_recommendation_rules(self) -> Dict[str, Any]:
        """Initialize recommendation rules and patterns"""
        return {
            "performance_thresholds": {
                "cpu_utilization": {"warning": 70, "critical": 85},
                "memory_utilization": {"warning": 80, "critical": 90},
                "disk_utilization": {"warning": 75, "critical": 90},
                "response_time": {"warning": 1000, "critical": 3000}  # milliseconds
            },
            "cost_optimization_rules": {
                "idle_resource_threshold": 10,  # percentage
                "oversized_resource_ratio": 0.5,  # utilization ratio
                "spot_instance_savings": 0.7  # 70% savings potential
            },
            "security_rules": {
                "failed_login_threshold": 5,
                "vulnerability_age_days": 30,
                "patch_compliance_threshold": 90  # percentage
            },
            "automation_triggers": {
                "recurring_manual_tasks": 3,  # number of repetitions
                "incident_pattern_threshold": 2,  # similar incidents
                "deployment_frequency": 5  # deployments per week
            }
        }
    
    async def generate_recommendations(self, system_data: Dict[str, Any], user_profile: Optional[UserProfile] = None) -> List[Recommendation]:
        """Generate intelligent recommendations based on system data"""
        try:
            recommendations = []
            
            # Performance recommendations
            perf_recommendations = await self._generate_performance_recommendations(system_data)
            recommendations.extend(perf_recommendations)
            
            # Cost optimization recommendations
            cost_recommendations = await self._generate_cost_recommendations(system_data)
            recommendations.extend(cost_recommendations)
            
            # Security recommendations
            security_recommendations = await self._generate_security_recommendations(system_data)
            recommendations.extend(security_recommendations)
            
            # Automation recommendations
            automation_recommendations = await self._generate_automation_recommendations(system_data)
            recommendations.extend(automation_recommendations)
            
            # Capacity planning recommendations
            capacity_recommendations = await self._generate_capacity_recommendations(system_data)
            recommendations.extend(capacity_recommendations)
            
            # Personalize recommendations based on user profile
            if user_profile:
                recommendations = self._personalize_recommendations(recommendations, user_profile)
            
            # Sort by priority and confidence
            recommendations.sort(key=lambda r: (r.priority.value, -r.confidence))
            
            # Store recommendations
            self.recommendations.extend(recommendations)
            
            logger.info(f"Generated {len(recommendations)} recommendations")
            return recommendations
            
        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            return []
    
    async def _generate_performance_recommendations(self, system_data: Dict[str, Any]) -> List[Recommendation]:
        """Generate performance-related recommendations"""
        recommendations = []
        
        try:
            # Check CPU utilization
            cpu_usage = system_data.get("cpu_utilization", 0)
            if cpu_usage > self.recommendation_rules["performance_thresholds"]["cpu_utilization"]["critical"]:
                recommendations.append(Recommendation(
                    recommendation_id=f"perf-cpu-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Critical CPU Utilization Detected",
                    description=f"CPU utilization is at {cpu_usage}%, which exceeds the critical threshold of 85%",
                    recommendation_type=RecommendationType.PERFORMANCE,
                    priority=RecommendationPriority.CRITICAL,
                    confidence=0.95,
                    potential_impact="High risk of performance degradation and service disruption",
                    estimated_savings=None,
                    implementation_steps=[
                        "Scale out CPU-intensive services horizontally",
                        "Optimize application algorithms and database queries",
                        "Consider upgrading to higher-performance instances",
                        "Implement CPU-based auto-scaling policies"
                    ],
                    risk_assessment="High risk if not addressed immediately",
                    data_sources=["System Metrics"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=1)
                ))
            
            # Check memory utilization
            memory_usage = system_data.get("memory_utilization", 0)
            if memory_usage > self.recommendation_rules["performance_thresholds"]["memory_utilization"]["warning"]:
                priority = RecommendationPriority.CRITICAL if memory_usage > 90 else RecommendationPriority.HIGH
                recommendations.append(Recommendation(
                    recommendation_id=f"perf-mem-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="High Memory Utilization",
                    description=f"Memory utilization is at {memory_usage}%, approaching capacity limits",
                    recommendation_type=RecommendationType.PERFORMANCE,
                    priority=priority,
                    confidence=0.90,
                    potential_impact="Risk of out-of-memory errors and application crashes",
                    estimated_savings=None,
                    implementation_steps=[
                        "Identify memory-intensive processes and optimize",
                        "Implement memory caching strategies",
                        "Consider increasing available memory",
                        "Review and tune garbage collection settings"
                    ],
                    risk_assessment="Medium to high risk depending on growth rate",
                    data_sources=["System Metrics"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=4)
                ))
            
            # Check response time
            response_time = system_data.get("average_response_time", 0)
            if response_time > self.recommendation_rules["performance_thresholds"]["response_time"]["warning"]:
                recommendations.append(Recommendation(
                    recommendation_id=f"perf-latency-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Elevated Response Times",
                    description=f"Average response time is {response_time}ms, above acceptable thresholds",
                    recommendation_type=RecommendationType.PERFORMANCE,
                    priority=RecommendationPriority.HIGH,
                    confidence=0.85,
                    potential_impact="Poor user experience and potential SLA violations",
                    estimated_savings=None,
                    implementation_steps=[
                        "Analyze slow queries and optimize database performance",
                        "Implement caching for frequently accessed data",
                        "Review network latency and CDN configuration",
                        "Consider load balancing optimization"
                    ],
                    risk_assessment="Medium risk with customer impact potential",
                    data_sources=["Application Metrics"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=6)
                ))
            
        except Exception as e:
            logger.error(f"Failed to generate performance recommendations: {e}")
        
        return recommendations
    
    async def _generate_cost_recommendations(self, system_data: Dict[str, Any]) -> List[Recommendation]:
        """Generate cost optimization recommendations"""
        recommendations = []
        
        try:
            # Check for idle resources
            idle_resources = system_data.get("idle_resources", [])
            if idle_resources:
                total_savings = sum([r.get("monthly_cost", 0) for r in idle_resources])
                recommendations.append(Recommendation(
                    recommendation_id=f"cost-idle-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Idle Resources Detected",
                    description=f"Found {len(idle_resources)} idle resources with low utilization",
                    recommendation_type=RecommendationType.COST_OPTIMIZATION,
                    priority=RecommendationPriority.MEDIUM,
                    confidence=0.88,
                    potential_impact="Significant cost savings opportunity",
                    estimated_savings=total_savings,
                    implementation_steps=[
                        "Review utilization patterns for identified resources",
                        "Shut down or downsize underutilized instances",
                        "Implement auto-scaling policies to prevent over-provisioning",
                        "Consider spot instances for batch workloads"
                    ],
                    risk_assessment="Low risk with proper validation",
                    data_sources=["Resource Utilization", "Billing Data"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=7)
                ))
            
            # Check for rightsizing opportunities
            oversized_resources = system_data.get("oversized_resources", [])
            if oversized_resources:
                estimated_savings = sum([r.get("potential_savings", 0) for r in oversized_resources])
                recommendations.append(Recommendation(
                    recommendation_id=f"cost-rightsize-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Resource Rightsizing Opportunity",
                    description=f"Found {len(oversized_resources)} resources that can be rightsized",
                    recommendation_type=RecommendationType.COST_OPTIMIZATION,
                    priority=RecommendationPriority.MEDIUM,
                    confidence=0.82,
                    potential_impact="Cost reduction through optimal resource allocation",
                    estimated_savings=estimated_savings,
                    implementation_steps=[
                        "Analyze historical utilization patterns",
                        "Test performance with smaller instance sizes",
                        "Implement gradual rightsizing with monitoring",
                        "Set up alerts for performance degradation"
                    ],
                    risk_assessment="Medium risk - requires performance validation",
                    data_sources=["Resource Utilization", "Performance Metrics"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=14)
                ))
            
        except Exception as e:
            logger.error(f"Failed to generate cost recommendations: {e}")
        
        return recommendations
    
    async def _generate_security_recommendations(self, system_data: Dict[str, Any]) -> List[Recommendation]:
        """Generate security-related recommendations"""
        recommendations = []
        
        try:
            # Check security posture score
            security_score = system_data.get("security_posture_score", 100)
            if security_score < 80:
                recommendations.append(Recommendation(
                    recommendation_id=f"sec-posture-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Security Posture Improvement Needed",
                    description=f"Security posture score is {security_score}/100, below recommended threshold",
                    recommendation_type=RecommendationType.SECURITY,
                    priority=RecommendationPriority.HIGH,
                    confidence=0.92,
                    potential_impact="Increased vulnerability to security threats",
                    estimated_savings=None,
                    implementation_steps=[
                        "Conduct comprehensive security assessment",
                        "Update and patch all systems to latest versions",
                        "Review and strengthen access controls",
                        "Implement additional security monitoring",
                        "Enhance security training for personnel"
                    ],
                    risk_assessment="High risk - potential for security incidents",
                    data_sources=["Security Monitoring"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=3)
                ))
            
            # Check for unpatched vulnerabilities
            vulnerabilities = system_data.get("open_vulnerabilities", [])
            critical_vulns = [v for v in vulnerabilities if v.get("severity") == "critical"]
            if critical_vulns:
                recommendations.append(Recommendation(
                    recommendation_id=f"sec-vuln-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Critical Vulnerabilities Require Immediate Attention",
                    description=f"Found {len(critical_vulns)} critical vulnerabilities that need patching",
                    recommendation_type=RecommendationType.SECURITY,
                    priority=RecommendationPriority.CRITICAL,
                    confidence=0.95,
                    potential_impact="High risk of exploitation and security breaches",
                    estimated_savings=None,
                    implementation_steps=[
                        "Prioritize patching of critical vulnerabilities",
                        "Test patches in staging environment first",
                        "Schedule maintenance windows for production patching",
                        "Implement vulnerability scanning automation"
                    ],
                    risk_assessment="Critical risk - immediate action required",
                    data_sources=["Vulnerability Scans"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=24)
                ))
            
        except Exception as e:
            logger.error(f"Failed to generate security recommendations: {e}")
        
        return recommendations
    
    async def _generate_automation_recommendations(self, system_data: Dict[str, Any]) -> List[Recommendation]:
        """Generate automation recommendations"""
        recommendations = []
        
        try:
            # Check for automation opportunities
            manual_tasks = system_data.get("frequent_manual_tasks", [])
            if manual_tasks:
                time_savings = sum([t.get("time_per_execution", 0) * t.get("frequency_per_week", 0) for t in manual_tasks])
                recommendations.append(Recommendation(
                    recommendation_id=f"auto-tasks-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Automation Opportunities Identified",
                    description=f"Found {len(manual_tasks)} frequently performed manual tasks suitable for automation",
                    recommendation_type=RecommendationType.AUTOMATION,
                    priority=RecommendationPriority.MEDIUM,
                    confidence=0.80,
                    potential_impact="Reduced manual effort and improved reliability",
                    estimated_savings=time_savings * 50,  # Estimate $50/hour saved
                    implementation_steps=[
                        "Analyze and document manual task workflows",
                        "Develop automation scripts and tools",
                        "Test automation in controlled environment",
                        "Gradually implement automation with monitoring",
                        "Train team on new automated processes"
                    ],
                    risk_assessment="Low risk with proper testing and rollback procedures",
                    data_sources=["Operational Logs", "Task Analysis"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=30)
                ))
            
            # Check incident response automation
            incident_patterns = system_data.get("incident_patterns", [])
            automatable_patterns = [p for p in incident_patterns if p.get("frequency", 0) >= 2]
            if automatable_patterns:
                recommendations.append(Recommendation(
                    recommendation_id=f"auto-incident-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Incident Response Automation Opportunity",
                    description=f"Identified {len(automatable_patterns)} recurring incident patterns suitable for automated response",
                    recommendation_type=RecommendationType.AUTOMATION,
                    priority=RecommendationPriority.HIGH,
                    confidence=0.85,
                    potential_impact="Faster incident resolution and reduced MTTR",
                    estimated_savings=None,
                    implementation_steps=[
                        "Create automated playbooks for common incidents",
                        "Implement intelligent alerting and escalation",
                        "Develop self-healing capabilities",
                        "Set up monitoring for automated actions"
                    ],
                    risk_assessment="Medium risk - requires careful testing",
                    data_sources=["Incident Management"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=21)
                ))
            
        except Exception as e:
            logger.error(f"Failed to generate automation recommendations: {e}")
        
        return recommendations
    
    async def _generate_capacity_recommendations(self, system_data: Dict[str, Any]) -> List[Recommendation]:
        """Generate capacity planning recommendations"""
        recommendations = []
        
        try:
            # Check growth trends
            growth_rate = system_data.get("resource_growth_rate", 0)
            if growth_rate > 20:  # 20% growth rate
                recommendations.append(Recommendation(
                    recommendation_id=f"capacity-growth-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Capacity Planning Required for High Growth",
                    description=f"Resource usage is growing at {growth_rate}% rate, requiring proactive capacity planning",
                    recommendation_type=RecommendationType.CAPACITY_PLANNING,
                    priority=RecommendationPriority.HIGH,
                    confidence=0.87,
                    potential_impact="Prevent performance degradation and service disruptions",
                    estimated_savings=None,
                    implementation_steps=[
                        "Analyze current growth trends and projections",
                        "Plan infrastructure scaling for next 6 months",
                        "Implement predictive auto-scaling",
                        "Review and optimize resource allocation",
                        "Set up capacity monitoring and alerting"
                    ],
                    risk_assessment="Medium risk if growth continues without planning",
                    data_sources=["Usage Trends", "Growth Analytics"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=14)
                ))
            
            # Check for capacity bottlenecks
            bottlenecks = system_data.get("capacity_bottlenecks", [])
            if bottlenecks:
                recommendations.append(Recommendation(
                    recommendation_id=f"capacity-bottleneck-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    title="Capacity Bottlenecks Detected",
                    description=f"Identified {len(bottlenecks)} potential capacity bottlenecks",
                    recommendation_type=RecommendationType.CAPACITY_PLANNING,
                    priority=RecommendationPriority.MEDIUM,
                    confidence=0.83,
                    potential_impact="Proactive resolution of performance constraints",
                    estimated_savings=None,
                    implementation_steps=[
                        "Analyze bottleneck root causes",
                        "Plan capacity expansion for constrained resources",
                        "Implement load balancing improvements",
                        "Optimize resource distribution"
                    ],
                    risk_assessment="Medium risk if bottlenecks persist",
                    data_sources=["Performance Analysis"],
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=10)
                ))
            
        except Exception as e:
            logger.error(f"Failed to generate capacity recommendations: {e}")
        
        return recommendations
    
    def _personalize_recommendations(self, recommendations: List[Recommendation], user_profile: UserProfile) -> List[Recommendation]:
        """Personalize recommendations based on user profile"""
        try:
            personalized = []
            
            for rec in recommendations:
                # Adjust based on user expertise level
                if user_profile.expertise_level == "beginner":
                    # Add more detailed steps for beginners
                    if len(rec.implementation_steps) < 3:
                        rec.implementation_steps.append("Consult with senior team members")
                        rec.implementation_steps.append("Follow detailed documentation")
                elif user_profile.expertise_level == "expert":
                    # Reduce verbosity for experts
                    rec.implementation_steps = rec.implementation_steps[:3]
                
                # Filter by user interests
                if user_profile.favorite_topics:
                    if any(topic in rec.recommendation_type.value for topic in user_profile.favorite_topics):
                        rec.confidence += 0.05  # Slight boost for relevant topics
                
                # Adjust based on role
                if user_profile.role == "analyst" and rec.recommendation_type in [RecommendationType.PERFORMANCE, RecommendationType.CAPACITY_PLANNING]:
                    rec.priority = RecommendationPriority.HIGH if rec.priority == RecommendationPriority.MEDIUM else rec.priority
                elif user_profile.role == "admin" and rec.recommendation_type == RecommendationType.SECURITY:
                    rec.priority = RecommendationPriority.HIGH if rec.priority == RecommendationPriority.MEDIUM else rec.priority
                
                personalized.append(rec)
            
            return personalized
            
        except Exception as e:
            logger.error(f"Failed to personalize recommendations: {e}")
            return recommendations

class AIAssistant:
    """Main AI Assistant with conversational interface"""
    
    def __init__(self, db_path: str = "aiops_assistant.db"):
        """Initialize AI Assistant"""
        self.db_path = db_path
        self.nlp = NaturalLanguageProcessor()
        self.recommendation_engine = RecommendationEngine()
        self.conversation_history: deque = deque(maxlen=100)
        self.user_profiles: Dict[str, UserProfile] = {}
        self.system_data: Dict[str, Any] = {}
        
        # Initialize database
        self._init_database()
        
        # Initialize sample user profiles
        self._initialize_sample_users()
        
        logger.info("AI Assistant initialized")
    
    def _init_database(self):
        """Apply schema migrations for the AI assistant SQLite database."""
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _migrations_dir = _os.path.join(
            _here, "..", "..", "migrations", "sqlite", "ai_recommendations"
        )
        try:
            from app.core.sqlite_migrator import run_sqlite_migrations
            run_sqlite_migrations(self.db_path, _migrations_dir)
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
    
    def _initialize_sample_users(self):
        """Initialize sample user profiles"""
        sample_users = [
            UserProfile(
                user_id="admin001",
                name="Alice Administrator",
                role="admin",
                preferences={"notification_urgency": "high", "detail_level": "comprehensive"},
                interaction_history=[],
                expertise_level="expert",
                favorite_topics=["security", "automation"],
                notification_preferences={"email": True, "slack": True, "sms": False}
            ),
            UserProfile(
                user_id="ops001",
                name="Bob Operator",
                role="operator",
                preferences={"notification_urgency": "medium", "detail_level": "summary"},
                interaction_history=[],
                expertise_level="intermediate",
                favorite_topics=["performance", "monitoring"],
                notification_preferences={"email": True, "slack": True, "sms": True}
            ),
            UserProfile(
                user_id="analyst001",
                name="Carol Analyst",
                role="analyst",
                preferences={"notification_urgency": "low", "detail_level": "detailed"},
                interaction_history=[],
                expertise_level="intermediate",
                favorite_topics=["cost_optimization", "capacity_planning"],
                notification_preferences={"email": True, "slack": False, "sms": False}
            )
        ]
        
        for user in sample_users:
            self.user_profiles[user.user_id] = user
    
    async def process_conversation(self, user_input: str, user_id: str = "anonymous") -> ConversationMessage:
        """Process a conversation with the AI assistant"""
        try:
            # Get user profile
            user_profile = self.user_profiles.get(user_id)
            
            # Process natural language input
            nlp_result = await self.nlp.process_input(user_input)
            
            # Generate AI response
            ai_response = await self._generate_response(nlp_result, user_profile)
            
            # Generate follow-up suggestions
            follow_ups = self._generate_follow_up_suggestions(nlp_result["intent"], nlp_result["context"])
            
            # Create conversation message
            message = ConversationMessage(
                message_id=f"msg-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}",
                user_input=user_input,
                ai_response=ai_response,
                context=nlp_result["context"],
                intent=nlp_result["intent"],
                entities=nlp_result["entities"],
                confidence=nlp_result["intent_confidence"],
                timestamp=datetime.now(),
                follow_up_suggestions=follow_ups
            )
            
            # Store conversation
            self.conversation_history.append(message)
            await self._save_conversation_to_db(message, user_id)
            
            # Update user interaction history
            if user_profile:
                user_profile.interaction_history.append(message.message_id)
                user_profile.interaction_history = user_profile.interaction_history[-20:]  # Keep last 20
            
            logger.info(f"Processed conversation for user {user_id}: {nlp_result['intent']}")
            return message
            
        except Exception as e:
            logger.error(f"Failed to process conversation: {e}")
            return ConversationMessage(
                message_id=f"error-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                user_input=user_input,
                ai_response="I apologize, but I encountered an error processing your request. Please try again.",
                context=ConversationContext.GENERAL,
                intent="error",
                entities={},
                confidence=0.0,
                timestamp=datetime.now(),
                follow_up_suggestions=["Try rephrasing your question", "Check system status", "Contact support"]
            )
    
    async def _generate_response(self, nlp_result: Dict[str, Any], user_profile: Optional[UserProfile]) -> str:
        """Generate AI response based on NLP results"""
        try:
            intent = nlp_result["intent"]
            entities = nlp_result["entities"]
            context = nlp_result["context"]
            
            # Get base response template
            if intent in self.nlp.response_templates:
                base_response = random.choice(self.nlp.response_templates[intent])
            else:
                base_response = "I understand your request. Let me help you with that..."
            
            # Generate specific response based on intent
            if intent == "status_check":
                response = await self._generate_status_response(entities)
            elif intent == "incident_report":
                response = await self._generate_incident_response(entities)
            elif intent == "performance_query":
                response = await self._generate_performance_response(entities)
            elif intent == "cost_inquiry":
                response = await self._generate_cost_response(entities)
            elif intent == "security_concern":
                response = await self._generate_security_response(entities)
            elif intent == "recommendation_request":
                response = await self._generate_recommendation_response(user_profile)
            elif intent == "help_request":
                response = await self._generate_help_response(entities)
            else:
                response = await self._generate_general_response(nlp_result)
            
            return f"{base_response}\n\n{response}"
            
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return "I apologize, but I'm having trouble generating a response. Please try again."
    
    async def _generate_status_response(self, entities: Dict[str, Any]) -> str:
        """Generate status check response"""
        # Simulate system status check
        status_data = {
            "overall_health": "Good",
            "services_online": 15,
            "services_total": 16,
            "cpu_usage": 45.2,
            "memory_usage": 67.8,
            "disk_usage": 34.5,
            "active_alerts": 2,
            "recent_incidents": 0
        }
        
        response = f"🟢 **System Status Overview**\n"
        response += f"Overall Health: {status_data['overall_health']}\n"
        response += f"Services: {status_data['services_online']}/{status_data['services_total']} online\n"
        response += f"Resource Usage:\n"
        response += f"  • CPU: {status_data['cpu_usage']:.1f}%\n"
        response += f"  • Memory: {status_data['memory_usage']:.1f}%\n"
        response += f"  • Disk: {status_data['disk_usage']:.1f}%\n"
        response += f"Active Alerts: {status_data['active_alerts']}\n"
        response += f"Recent Incidents: {status_data['recent_incidents']}"
        
        return response
    
    async def _generate_incident_response(self, entities: Dict[str, Any]) -> str:
        """Generate incident response"""
        incident_id = f"INC-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        
        response = f"🚨 **Incident Response Initiated**\n"
        response += f"Incident ID: {incident_id}\n"
        response += f"Priority: High\n"
        response += f"Status: Investigating\n\n"
        response += f"I'm analyzing the situation and will:\n"
        response += f"1. Check related system metrics and logs\n"
        response += f"2. Identify potential root causes\n"
        response += f"3. Suggest immediate remediation steps\n"
        response += f"4. Monitor for similar patterns\n\n"
        response += f"I'll keep you updated on the investigation progress."
        
        return response
    
    async def _generate_performance_response(self, entities: Dict[str, Any]) -> str:
        """Generate performance query response"""
        # Simulate performance data
        perf_data = {
            "avg_response_time": 245,
            "throughput": 1250,
            "error_rate": 0.02,
            "cpu_trend": "stable",
            "memory_trend": "increasing",
            "top_slowest_endpoints": [
                "/api/analytics (850ms)",
                "/api/reports (620ms)",
                "/api/search (410ms)"
            ]
        }
        
        response = f"📊 **Performance Analysis**\n"
        response += f"Average Response Time: {perf_data['avg_response_time']}ms\n"
        response += f"Throughput: {perf_data['throughput']} requests/minute\n"
        response += f"Error Rate: {perf_data['error_rate']:.2%}\n\n"
        response += f"Resource Trends:\n"
        response += f"  • CPU: {perf_data['cpu_trend']}\n"
        response += f"  • Memory: {perf_data['memory_trend']}\n\n"
        response += f"Slowest Endpoints:\n"
        for endpoint in perf_data['top_slowest_endpoints']:
            response += f"  • {endpoint}\n"
        
        return response
    
    async def _generate_cost_response(self, entities: Dict[str, Any]) -> str:
        """Generate cost inquiry response"""
        # Simulate cost data
        cost_data = {
            "current_monthly": 12450.75,
            "projected_monthly": 13200.00,
            "last_month": 11890.50,
            "top_cost_centers": [
                "Compute Instances: $4,200",
                "Data Storage: $2,800",
                "Network Transfer: $1,450",
                "Load Balancing: $950"
            ],
            "optimization_potential": 2100.00
        }
        
        response = f"💰 **Cost Analysis**\n"
        response += f"Current Month: ${cost_data['current_monthly']:,.2f}\n"
        response += f"Projected: ${cost_data['projected_monthly']:,.2f}\n"
        response += f"Last Month: ${cost_data['last_month']:,.2f}\n\n"
        response += f"Top Cost Centers:\n"
        for cost_center in cost_data['top_cost_centers']:
            response += f"  • {cost_center}\n"
        response += f"\n💡 Optimization Potential: ${cost_data['optimization_potential']:,.2f}/month"
        
        return response
    
    async def _generate_security_response(self, entities: Dict[str, Any]) -> str:
        """Generate security concern response"""
        # Simulate security data
        security_data = {
            "security_score": 81,
            "open_vulnerabilities": 7,
            "critical_vulnerabilities": 1,
            "failed_logins_24h": 23,
            "compliance_status": "Good",
            "recent_threats": [
                "Suspicious login attempts from IP 192.168.1.100",
                "Outdated SSL certificate on api.example.com",
                "Unusual network traffic detected"
            ]
        }
        
        response = f"🔒 **Security Status**\n"
        response += f"Security Score: {security_data['security_score']}/100\n"
        response += f"Open Vulnerabilities: {security_data['open_vulnerabilities']} ({security_data['critical_vulnerabilities']} critical)\n"
        response += f"Failed Logins (24h): {security_data['failed_logins_24h']}\n"
        response += f"Compliance Status: {security_data['compliance_status']}\n\n"
        response += f"Recent Security Events:\n"
        for threat in security_data['recent_threats']:
            response += f"  ⚠️ {threat}\n"
        
        return response
    
    async def _generate_recommendation_response(self, user_profile: Optional[UserProfile]) -> str:
        """Generate recommendation response"""
        # Generate sample system data for recommendations
        sample_system_data = {
            "cpu_utilization": 78,
            "memory_utilization": 85,
            "security_posture_score": 75,
            "idle_resources": [{"name": "test-server-001", "monthly_cost": 450}],
            "frequent_manual_tasks": [{"name": "log_rotation", "time_per_execution": 30, "frequency_per_week": 5}]
        }
        
        recommendations = await self.recommendation_engine.generate_recommendations(sample_system_data, user_profile)
        
        if recommendations:
            response = f"💡 **AI Recommendations**\n\n"
            for i, rec in enumerate(recommendations[:3], 1):  # Show top 3
                priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
                response += f"{i}. {priority_emoji.get(rec.priority.value, '•')} **{rec.title}**\n"
                response += f"   {rec.description}\n"
                response += f"   Priority: {rec.priority.value.title()} | Confidence: {rec.confidence:.0%}\n\n"
            
            if len(recommendations) > 3:
                response += f"...and {len(recommendations) - 3} more recommendations available."
        else:
            response = "No specific recommendations at this time. Your systems are performing well!"
        
        return response
    
    async def _generate_help_response(self, entities: Dict[str, Any]) -> str:
        """Generate help response"""
        response = f"🤖 **AI Assistant Help**\n\n"
        response += f"I can help you with:\n"
        response += f"• **System Status**: Check health, performance, and availability\n"
        response += f"• **Incident Management**: Report issues and get resolution guidance\n"
        response += f"• **Performance Analysis**: Monitor metrics and identify bottlenecks\n"
        response += f"• **Cost Optimization**: Analyze spending and find savings\n"
        response += f"• **Security Monitoring**: Review threats and compliance\n"
        response += f"• **Automation**: Suggest and implement process automation\n"
        response += f"• **Recommendations**: Provide AI-powered insights and suggestions\n\n"
        response += f"Just ask me in natural language! For example:\n"
        response += f"• \"What's the current system status?\"\n"
        response += f"• \"I'm seeing high CPU usage\"\n"
        response += f"• \"How can we reduce costs?\"\n"
        response += f"• \"Show me security alerts\""
        
        return response
    
    async def _generate_general_response(self, nlp_result: Dict[str, Any]) -> str:
        """Generate general response for unknown intents"""
        response = f"I'm not entirely sure what you're asking about, but I'm here to help with AIOps operations.\n\n"
        response += f"Could you please clarify if you're asking about:\n"
        response += f"• System status or performance\n"
        response += f"• An incident or issue\n"
        response += f"• Cost or resource optimization\n"
        response += f"• Security concerns\n"
        response += f"• Automation opportunities\n\n"
        response += f"Or you can ask me for general help to see all my capabilities."
        
        return response
    
    def _generate_follow_up_suggestions(self, intent: str, context: ConversationContext) -> List[str]:
        """Generate follow-up suggestions based on intent and context"""
        suggestions = []
        
        if intent == "status_check":
            suggestions = [
                "Show me performance trends",
                "Check for any alerts",
                "Generate health report"
            ]
        elif intent == "incident_report":
            suggestions = [
                "What's the impact assessment?",
                "Show related incidents",
                "Start automated remediation"
            ]
        elif intent == "performance_query":
            suggestions = [
                "Analyze performance trends",
                "Check resource utilization",
                "Suggest optimizations"
            ]
        elif intent == "cost_inquiry":
            suggestions = [
                "Find cost optimization opportunities",
                "Show spending trends",
                "Compare with last month"
            ]
        elif intent == "security_concern":
            suggestions = [
                "Run security scan",
                "Check compliance status",
                "Review recent threats"
            ]
        elif intent == "recommendation_request":
            suggestions = [
                "Show implementation details",
                "Calculate ROI",
                "Schedule implementation"
            ]
        else:
            suggestions = [
                "Show system overview",
                "Get recommendations",
                "Check for alerts"
            ]
        
        return suggestions[:3]  # Return top 3 suggestions
    
    async def _save_conversation_to_db(self, message: ConversationMessage, user_id: str):
        """Save conversation to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO conversations 
                (message_id, user_input, ai_response, context, intent, confidence, timestamp, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message.message_id, message.user_input, message.ai_response,
                message.context.value, message.intent, message.confidence,
                message.timestamp.isoformat(), user_id
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to save conversation to database: {e}")
    
    async def get_conversation_summary(self, user_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Get conversation summary for user or all users"""
        try:
            recent_conversations = list(self.conversation_history)[-limit:]
            
            if user_id:
                # Filter by user if user_id provided (simplified for demo)
                pass  # In real implementation, filter conversations by user_id
            
            summary = {
                "total_conversations": len(recent_conversations),
                "intents_distribution": defaultdict(int),
                "contexts_distribution": defaultdict(int),
                "average_confidence": 0.0,
                "recent_topics": [],
                "user_satisfaction_indicators": {
                    "follow_up_rate": 0.65,
                    "resolution_rate": 0.82,
                    "escalation_rate": 0.08
                }
            }
            
            confidences = []
            
            for conv in recent_conversations:
                summary["intents_distribution"][conv.intent] += 1
                summary["contexts_distribution"][conv.context.value] += 1
                confidences.append(conv.confidence)
                
                # Extract topics from entities (simplified)
                for entity_type, entities in conv.entities.items():
                    summary["recent_topics"].extend(entities)
            
            if confidences:
                summary["average_confidence"] = statistics.mean(confidences)
            
            # Remove duplicates and limit recent topics
            summary["recent_topics"] = list(set(summary["recent_topics"]))[:10]
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get conversation summary: {e}")
            return {}

async def demo_ai_assistant():
    """Demonstrate AI Assistant & Recommendation Engine capabilities"""
    print("🤖 AIOps AI Assistant & Recommendation Engine Demo")
    print("=" * 60)
    
    # Initialize AI Assistant
    assistant = AIAssistant()
    
    print("\n👥 User Profiles:")
    for user_id, profile in assistant.user_profiles.items():
        print(f"  🧑‍💼 {profile.name} ({profile.role})")
        print(f"     Expertise: {profile.expertise_level} | Topics: {', '.join(profile.favorite_topics)}")
    
    print("\n🗣️ Sample Conversations:")
    
    # Sample conversations
    conversations = [
        ("admin001", "What's the current system status?"),
        ("ops001", "I'm seeing high CPU usage on our servers"),
        ("analyst001", "How can we reduce our cloud costs?"),
        ("admin001", "We have a security alert - unusual login activity"),
        ("ops001", "Can you give me some recommendations for performance optimization?"),
        ("analyst001", "Help me understand the automation capabilities")
    ]
    
    for user_id, user_input in conversations:
        print(f"\n👤 **{assistant.user_profiles[user_id].name}**: {user_input}")
        
        # Process conversation
        message = await assistant.process_conversation(user_input, user_id)
        
        print(f"🤖 **AI Assistant**: {message.ai_response}")
        print(f"   📊 Intent: {message.intent} (confidence: {message.confidence:.0%})")
        print(f"   🏷️ Context: {message.context.value}")
        
        if message.entities:
            entities_str = ", ".join([f"{k}: {v}" for k, v in message.entities.items()])
            print(f"   🔍 Entities: {entities_str}")
        
        if message.follow_up_suggestions:
            print(f"   💡 Suggestions: {', '.join(message.follow_up_suggestions)}")
        
        # Small delay for demo effect
        await asyncio.sleep(0.5)
    
    print("\n📈 Recommendation Engine Demo:")
    
    # Generate recommendations for different scenarios
    sample_system_data = {
        "cpu_utilization": 88,
        "memory_utilization": 92,
        "security_posture_score": 74,
        "idle_resources": [
            {"name": "dev-server-001", "monthly_cost": 320},
            {"name": "test-server-002", "monthly_cost": 450}
        ],
        "oversized_resources": [
            {"name": "prod-server-001", "potential_savings": 600}
        ],
        "frequent_manual_tasks": [
            {"name": "backup_rotation", "time_per_execution": 45, "frequency_per_week": 7},
            {"name": "log_analysis", "time_per_execution": 60, "frequency_per_week": 3}
        ],
        "open_vulnerabilities": [
            {"severity": "critical", "age_days": 15},
            {"severity": "high", "age_days": 45}
        ],
        "resource_growth_rate": 25,
        "capacity_bottlenecks": [
            {"resource": "database_connections", "utilization": 95}
        ]
    }
    
    # Generate recommendations for admin user
    admin_profile = assistant.user_profiles["admin001"]
    recommendations = await assistant.recommendation_engine.generate_recommendations(sample_system_data, admin_profile)
    
    print(f"\n🎯 Generated {len(recommendations)} recommendations:")
    
    for i, rec in enumerate(recommendations, 1):
        priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
        type_emoji = {
            "performance": "⚡",
            "cost_optimization": "💰",
            "security": "🔒",
            "automation": "🤖",
            "capacity_planning": "📊",
            "troubleshooting": "🔧"
        }
        
        print(f"\n{i}. {priority_emoji.get(rec.priority.value, '•')} {type_emoji.get(rec.recommendation_type.value, '💡')} **{rec.title}**")
        print(f"   {rec.description}")
        print(f"   Priority: {rec.priority.value.title()} | Confidence: {rec.confidence:.0%}")
        print(f"   Impact: {rec.potential_impact}")
        
        if rec.estimated_savings:
            print(f"   💰 Potential Savings: ${rec.estimated_savings:,.2f}")
        
        print(f"   📋 Implementation Steps:")
        for j, step in enumerate(rec.implementation_steps[:3], 1):
            print(f"      {j}. {step}")
        
        if len(rec.implementation_steps) > 3:
            print(f"      ...and {len(rec.implementation_steps) - 3} more steps")
    
    print("\n📊 Conversation Analytics:")
    conversation_summary = await assistant.get_conversation_summary()
    
    print(f"  💬 Total Conversations: {conversation_summary['total_conversations']}")
    print(f"  🎯 Average Confidence: {conversation_summary['average_confidence']:.0%}")
    
    if conversation_summary['intents_distribution']:
        print(f"  🧠 Top Intents:")
        sorted_intents = sorted(conversation_summary['intents_distribution'].items(), key=lambda x: x[1], reverse=True)
        for intent, count in sorted_intents[:3]:
            print(f"     • {intent}: {count} conversations")
    
    if conversation_summary['recent_topics']:
        print(f"  🏷️ Recent Topics: {', '.join(conversation_summary['recent_topics'][:5])}")
    
    satisfaction = conversation_summary.get('user_satisfaction_indicators', {})
    print(f"  😊 User Satisfaction Metrics:")
    print(f"     • Follow-up Rate: {satisfaction.get('follow_up_rate', 0):.0%}")
    print(f"     • Resolution Rate: {satisfaction.get('resolution_rate', 0):.0%}")
    print(f"     • Escalation Rate: {satisfaction.get('escalation_rate', 0):.0%}")
    
    print("\n🏆 AI Assistant & Recommendation Engine demonstration complete!")
    print("✨ Conversational AI and intelligent recommendations fully operational!")

if __name__ == "__main__":
    asyncio.run(demo_ai_assistant())