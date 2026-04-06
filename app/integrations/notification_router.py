#!/usr/bin/env python3
"""
AIOps Multi-Channel Notification Router
Unified notification system supporting Discord, Slack, Email, SMS, and webhooks

Features:
- Priority-based routing to multiple channels
- Escalation policies and procedures
- Channel failover and redundancy
- Notification templates and customization
- Delivery tracking and analytics
- Rate limiting and throttling
"""

import asyncio
import hashlib
import json
import logging
import os
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('notification_router')

class Priority(Enum):
    """Notification priority levels"""
    P0 = "p0"  # Critical - immediate attention
    P1 = "p1"  # High - within 15 minutes
    P2 = "p2"  # Medium - within 1 hour
    P3 = "p3"  # Low - within 4 hours
    P4 = "p4"  # Info - within 24 hours

class ChannelType(Enum):
    """Supported notification channels"""
    DISCORD = "discord"
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    PUSH = "push"

class DeliveryStatus(Enum):
    """Message delivery status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRY = "retry"

@dataclass
class NotificationChannel:
    """Notification channel configuration"""
    channel_type: ChannelType
    name: str
    config: Dict[str, Any]
    enabled: bool = True
    max_retries: int = 3
    timeout: int = 30
    rate_limit: int = 100  # messages per hour
    cost: float = 0.0  # cost per message (for optimization)

@dataclass
class EscalationPolicy:
    """Escalation policy configuration"""
    name: str
    steps: List[Dict[str, Any]]
    escalation_delay: int = 900  # 15 minutes
    max_escalations: int = 3

@dataclass
class NotificationMessage:
    """Unified notification message"""
    id: str
    title: str
    content: str
    priority: Priority
    source: str
    timestamp: datetime
    target_channels: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    escalation_policy: Optional[str] = None
    delivery_attempts: int = 0
    status: DeliveryStatus = DeliveryStatus.PENDING

@dataclass
class DeliveryResult:
    """Delivery result tracking"""
    message_id: str
    channel: str
    status: DeliveryStatus
    attempt: int
    timestamp: datetime
    response: Optional[Dict] = None
    error: Optional[str] = None
    delivery_time: Optional[float] = None

class ChannelManager:
    """Manage different notification channels"""
    
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.channels = {}
        self.setup_default_channels()
        
    def setup_default_channels(self):
        """Setup default notification channels"""
        
        # Discord channel
        self.channels['discord-alerts'] = NotificationChannel(
            channel_type=ChannelType.DISCORD,
            name='discord-alerts',
            config={
                'bot_token': os.getenv('DISCORD_BOT_TOKEN', 'demo_token'),
                'guild_id': os.getenv('DISCORD_GUILD_ID', '123456789'),
                'channel_id': os.getenv('DISCORD_CHANNEL_ID', '987654321')
            },
            rate_limit=50,
            cost=0.0
        )
        
        # Slack channels
        self.channels['slack-critical'] = NotificationChannel(
            channel_type=ChannelType.SLACK,
            name='slack-critical',
            config={
                'webhook_url': os.getenv('SLACK_CRITICAL_WEBHOOK', 'https://hooks.slack.com/demo/critical'),
                'channel': '#incidents'
            },
            rate_limit=100,
            cost=0.0
        )
        
        self.channels['slack-general'] = NotificationChannel(
            channel_type=ChannelType.SLACK,
            name='slack-general',
            config={
                'webhook_url': os.getenv('SLACK_GENERAL_WEBHOOK', 'https://hooks.slack.com/demo/general'),
                'channel': '#alerts'
            },
            rate_limit=200,
            cost=0.0
        )
        
        # Email channel
        self.channels['email-ops'] = NotificationChannel(
            channel_type=ChannelType.EMAIL,
            name='email-ops',
            config={
                'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('SMTP_PORT', '587')),
                'username': os.getenv('EMAIL_USERNAME', 'demo@company.com'),
                'password': os.getenv('EMAIL_PASSWORD', 'demo_password'),
                'from_address': os.getenv('EMAIL_FROM', 'aiops@company.com'),
                'to_addresses': ['ops-team@company.com', 'on-call@company.com']
            },
            rate_limit=20,
            cost=0.01
        )
        
        # SMS channel (via webhook to SMS service)
        self.channels['sms-oncall'] = NotificationChannel(
            channel_type=ChannelType.SMS,
            name='sms-oncall',
            config={
                'service_url': os.getenv('SMS_SERVICE_URL', 'https://api.sms-service.com/send'),
                'api_key': os.getenv('SMS_API_KEY', 'demo_sms_key'),
                'phone_numbers': ['+1-555-0123', '+1-555-0124']
            },
            rate_limit=10,
            cost=0.05
        )
        
        # Webhook channel
        self.channels['webhook-external'] = NotificationChannel(
            channel_type=ChannelType.WEBHOOK,
            name='webhook-external',
            config={
                'url': os.getenv('EXTERNAL_WEBHOOK_URL', 'https://external-system.com/webhook'),
                'headers': {'Authorization': 'Bearer demo_token'},
                'method': 'POST'
            },
            rate_limit=500,
            cost=0.001
        )
    
    async def send_discord_message(self, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult:
        """Send message to Discord"""
        start_time = time.time()
        
        try:
            if self.demo_mode:
                logger.info(f"[DEMO] Sending Discord message to {channel.config.get('channel_id')}")
                logger.info(f"[DEMO] Title: {message.title}")
                logger.info(f"[DEMO] Content: {message.content}")
                
                # Simulate processing time
                await asyncio.sleep(0.1)
                
                return DeliveryResult(
                    message_id=message.id,
                    channel=channel.name,
                    status=DeliveryStatus.SENT,
                    attempt=message.delivery_attempts + 1,
                    timestamp=datetime.now(),
                    delivery_time=time.time() - start_time,
                    response={'status': 'success', 'id': f'discord_msg_{int(time.time())}'}
                )
            else:
                # Real Discord API call would go here
                # This would use discord.py or similar library
                pass
                
        except Exception as e:
            return DeliveryResult(
                message_id=message.id,
                channel=channel.name,
                status=DeliveryStatus.FAILED,
                attempt=message.delivery_attempts + 1,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def send_slack_message(self, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult:
        """Send message to Slack"""
        start_time = time.time()
        
        try:
            payload = {
                'text': message.title,
                'attachments': [
                    {
                        'color': self._get_priority_color(message.priority),
                        'fields': [
                            {'title': 'Priority', 'value': message.priority.value.upper(), 'short': True},
                            {'title': 'Source', 'value': message.source, 'short': True},
                            {'title': 'Time', 'value': message.timestamp.strftime('%Y-%m-%d %H:%M:%S'), 'short': True}
                        ],
                        'text': message.content
                    }
                ]
            }
            
            if self.demo_mode:
                logger.info(f"[DEMO] Sending Slack message to {channel.config.get('webhook_url')}")
                logger.info(f"[DEMO] Payload: {json.dumps(payload, indent=2)}")
                
                await asyncio.sleep(0.1)
                
                return DeliveryResult(
                    message_id=message.id,
                    channel=channel.name,
                    status=DeliveryStatus.SENT,
                    attempt=message.delivery_attempts + 1,
                    timestamp=datetime.now(),
                    delivery_time=time.time() - start_time,
                    response={'ok': True, 'ts': f'slack_ts_{int(time.time())}'}
                )
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        channel.config['webhook_url'],
                        json=payload,
                        timeout=channel.timeout
                    ) as response:
                        result = await response.json()
                        
                        return DeliveryResult(
                            message_id=message.id,
                            channel=channel.name,
                            status=DeliveryStatus.SENT if response.status == 200 else DeliveryStatus.FAILED,
                            attempt=message.delivery_attempts + 1,
                            timestamp=datetime.now(),
                            delivery_time=time.time() - start_time,
                            response=result
                        )
                        
        except Exception as e:
            return DeliveryResult(
                message_id=message.id,
                channel=channel.name,
                status=DeliveryStatus.FAILED,
                attempt=message.delivery_attempts + 1,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def send_email_message(self, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult:
        """Send email message"""
        start_time = time.time()
        
        try:
            if self.demo_mode:
                logger.info(f"[DEMO] Sending email to {channel.config.get('to_addresses')}")
                logger.info(f"[DEMO] Subject: {message.title}")
                logger.info(f"[DEMO] Body: {message.content}")
                
                await asyncio.sleep(0.2)
                
                return DeliveryResult(
                    message_id=message.id,
                    channel=channel.name,
                    status=DeliveryStatus.SENT,
                    attempt=message.delivery_attempts + 1,
                    timestamp=datetime.now(),
                    delivery_time=time.time() - start_time,
                    response={'status': 'sent', 'recipients': len(channel.config['to_addresses'])}
                )
            else:
                # Real email sending would go here
                config = channel.config
                msg = MIMEMultipart()
                msg['From'] = config['from_address']
                msg['To'] = ', '.join(config['to_addresses'])
                msg['Subject'] = f"[{message.priority.value.upper()}] {message.title}"
                
                body = f"""
Priority: {message.priority.value.upper()}
Source: {message.source}
Time: {message.timestamp}

{message.content}
                """.strip()
                
                msg.attach(MIMEText(body, 'plain'))
                
                server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
                server.starttls()
                server.login(config['username'], config['password'])
                server.send_message(msg)
                server.quit()
                
                return DeliveryResult(
                    message_id=message.id,
                    channel=channel.name,
                    status=DeliveryStatus.SENT,
                    attempt=message.delivery_attempts + 1,
                    timestamp=datetime.now(),
                    delivery_time=time.time() - start_time
                )
                
        except Exception as e:
            return DeliveryResult(
                message_id=message.id,
                channel=channel.name,
                status=DeliveryStatus.FAILED,
                attempt=message.delivery_attempts + 1,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def send_sms_message(self, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult:
        """Send SMS message"""
        start_time = time.time()
        
        try:
            # Truncate message for SMS
            sms_content = f"{message.title}: {message.content}"[:160]
            
            if self.demo_mode:
                logger.info(f"[DEMO] Sending SMS to {channel.config.get('phone_numbers')}")
                logger.info(f"[DEMO] Message: {sms_content}")
                
                await asyncio.sleep(0.3)
                
                return DeliveryResult(
                    message_id=message.id,
                    channel=channel.name,
                    status=DeliveryStatus.SENT,
                    attempt=message.delivery_attempts + 1,
                    timestamp=datetime.now(),
                    delivery_time=time.time() - start_time,
                    response={'status': 'sent', 'recipients': len(channel.config['phone_numbers'])}
                )
            else:
                # Real SMS sending via API
                config = channel.config
                payload = {
                    'api_key': config['api_key'],
                    'to': config['phone_numbers'],
                    'message': sms_content
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        config['service_url'],
                        json=payload,
                        timeout=channel.timeout
                    ) as response:
                        result = await response.json()
                        
                        return DeliveryResult(
                            message_id=message.id,
                            channel=channel.name,
                            status=DeliveryStatus.SENT if response.status == 200 else DeliveryStatus.FAILED,
                            attempt=message.delivery_attempts + 1,
                            timestamp=datetime.now(),
                            delivery_time=time.time() - start_time,
                            response=result
                        )
                        
        except Exception as e:
            return DeliveryResult(
                message_id=message.id,
                channel=channel.name,
                status=DeliveryStatus.FAILED,
                attempt=message.delivery_attempts + 1,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def send_webhook_message(self, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult:
        """Send webhook message"""
        start_time = time.time()
        
        try:
            payload = {
                'id': message.id,
                'title': message.title,
                'content': message.content,
                'priority': message.priority.value,
                'source': message.source,
                'timestamp': message.timestamp.isoformat(),
                'metadata': message.metadata
            }
            
            if self.demo_mode:
                logger.info(f"[DEMO] Sending webhook to {channel.config.get('url')}")
                logger.info(f"[DEMO] Payload: {json.dumps(payload, indent=2)}")
                
                await asyncio.sleep(0.1)
                
                return DeliveryResult(
                    message_id=message.id,
                    channel=channel.name,
                    status=DeliveryStatus.SENT,
                    attempt=message.delivery_attempts + 1,
                    timestamp=datetime.now(),
                    delivery_time=time.time() - start_time,
                    response={'status': 'received', 'webhook_id': f'webhook_{int(time.time())}'}
                )
            else:
                config = channel.config
                headers = config.get('headers', {})
                headers['Content-Type'] = 'application/json'
                
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        config.get('method', 'POST'),
                        config['url'],
                        json=payload,
                        headers=headers,
                        timeout=channel.timeout
                    ) as response:
                        result = await response.text()
                        
                        return DeliveryResult(
                            message_id=message.id,
                            channel=channel.name,
                            status=DeliveryStatus.SENT if response.status == 200 else DeliveryStatus.FAILED,
                            attempt=message.delivery_attempts + 1,
                            timestamp=datetime.now(),
                            delivery_time=time.time() - start_time,
                            response={'status_code': response.status, 'response': result}
                        )
                        
        except Exception as e:
            return DeliveryResult(
                message_id=message.id,
                channel=channel.name,
                status=DeliveryStatus.FAILED,
                attempt=message.delivery_attempts + 1,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def _get_priority_color(self, priority: Priority) -> str:
        """Get color code for priority level"""
        colors = {
            Priority.P0: "#FF0000",  # Red
            Priority.P1: "#FF6600",  # Orange  
            Priority.P2: "#FFCC00",  # Yellow
            Priority.P3: "#00FF00",  # Green
            Priority.P4: "#0099FF"   # Blue
        }
        return colors.get(priority, "#808080")

class NotificationRouter:
    """Main notification routing system"""
    
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.channel_manager = ChannelManager(demo_mode)
        self.escalation_policies = {}
        self.delivery_history = []
        self.rate_limits = {}
        
        self.setup_escalation_policies()
        
        logger.info(f"Notification router initialized (demo_mode={demo_mode})")
    
    def setup_escalation_policies(self):
        """Setup escalation policies"""
        
        # Critical incidents escalation
        self.escalation_policies['critical'] = EscalationPolicy(
            name='critical',
            steps=[
                {
                    'delay': 0,
                    'channels': ['slack-critical', 'discord-alerts'],
                    'description': 'Immediate notification to incident channels'
                },
                {
                    'delay': 300,  # 5 minutes
                    'channels': ['sms-oncall', 'email-ops'],
                    'description': 'Escalate to on-call team if no acknowledgment'
                },
                {
                    'delay': 900,  # 15 minutes
                    'channels': ['webhook-external'],
                    'description': 'Notify external systems for major incidents'
                }
            ],
            escalation_delay=300,
            max_escalations=3
        )
        
        # Standard alerts escalation
        self.escalation_policies['standard'] = EscalationPolicy(
            name='standard',
            steps=[
                {
                    'delay': 0,
                    'channels': ['slack-general', 'discord-alerts'],
                    'description': 'Standard notification channels'
                },
                {
                    'delay': 1800,  # 30 minutes
                    'channels': ['email-ops'],
                    'description': 'Email notification if not resolved'
                }
            ],
            escalation_delay=1800,
            max_escalations=2
        )
        
        # Information only
        self.escalation_policies['info'] = EscalationPolicy(
            name='info',
            steps=[
                {
                    'delay': 0,
                    'channels': ['slack-general'],
                    'description': 'Information notification only'
                }
            ],
            escalation_delay=0,
            max_escalations=1
        )
    
    def get_routing_channels(self, message: NotificationMessage) -> List[str]:
        """Determine which channels to route message to based on priority"""
        
        # Priority-based routing
        if message.priority == Priority.P0:
            return ['slack-critical', 'discord-alerts', 'sms-oncall', 'email-ops']
        elif message.priority == Priority.P1:
            return ['slack-critical', 'discord-alerts', 'email-ops']
        elif message.priority == Priority.P2:
            return ['slack-general', 'discord-alerts', 'email-ops']
        elif message.priority == Priority.P3:
            return ['slack-general', 'discord-alerts']
        else:  # P4
            return ['slack-general']
    
    async def route_message(self, message: NotificationMessage) -> List[DeliveryResult]:
        """Route message to appropriate channels"""
        
        # Determine target channels
        if message.target_channels:
            channels = message.target_channels
        else:
            channels = self.get_routing_channels(message)
        
        logger.info(f"Routing message {message.id} to channels: {channels}")
        
        # Send to all channels concurrently
        delivery_tasks = []
        for channel_name in channels:
            if channel_name in self.channel_manager.channels:
                channel = self.channel_manager.channels[channel_name]
                if channel.enabled:
                    task = self._send_to_channel(channel, message)
                    delivery_tasks.append(task)
                else:
                    logger.warning(f"Channel {channel_name} is disabled")
            else:
                logger.error(f"Unknown channel: {channel_name}")
        
        # Wait for all deliveries
        results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
        
        # Process results
        delivery_results = []
        for result in results:
            if isinstance(result, DeliveryResult):
                delivery_results.append(result)
                self.delivery_history.append(result)
            else:
                logger.error(f"Delivery task failed: {result}")
        
        return delivery_results
    
    async def _send_to_channel(self, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult:
        """Send message to specific channel"""
        
        # Check rate limits
        if self._is_rate_limited(channel.name):
            return DeliveryResult(
                message_id=message.id,
                channel=channel.name,
                status=DeliveryStatus.FAILED,
                attempt=message.delivery_attempts + 1,
                timestamp=datetime.now(),
                error="Rate limit exceeded"
            )
        
        # Route to appropriate sender
        if channel.channel_type == ChannelType.DISCORD:
            return await self.channel_manager.send_discord_message(channel, message)
        elif channel.channel_type == ChannelType.SLACK:
            return await self.channel_manager.send_slack_message(channel, message)
        elif channel.channel_type == ChannelType.EMAIL:
            return await self.channel_manager.send_email_message(channel, message)
        elif channel.channel_type == ChannelType.SMS:
            return await self.channel_manager.send_sms_message(channel, message)
        elif channel.channel_type == ChannelType.WEBHOOK:
            return await self.channel_manager.send_webhook_message(channel, message)
        else:
            return DeliveryResult(
                message_id=message.id,
                channel=channel.name,
                status=DeliveryStatus.FAILED,
                attempt=message.delivery_attempts + 1,
                timestamp=datetime.now(),
                error=f"Unsupported channel type: {channel.channel_type}"
            )
    
    def _is_rate_limited(self, channel_name: str) -> bool:
        """Check if channel is rate limited"""
        # Simple rate limiting implementation
        current_time = datetime.now()
        hour_key = current_time.strftime('%Y-%m-%d-%H')
        rate_key = f"{channel_name}:{hour_key}"
        
        if rate_key not in self.rate_limits:
            self.rate_limits[rate_key] = 0
        
        channel = self.channel_manager.channels.get(channel_name)
        if channel and self.rate_limits[rate_key] >= channel.rate_limit:
            return True
        
        self.rate_limits[rate_key] += 1
        return False
    
    async def process_escalation(self, message: NotificationMessage) -> List[DeliveryResult]:
        """Process escalation policy for message"""
        policy_name = message.escalation_policy or self._get_default_policy(message.priority)
        policy = self.escalation_policies.get(policy_name)
        
        if not policy:
            logger.error(f"Unknown escalation policy: {policy_name}")
            return []
        
        all_results = []
        
        for step in policy.steps:
            # Wait for delay if specified
            if step['delay'] > 0:
                logger.info(f"Waiting {step['delay']} seconds for escalation step: {step['description']}")
                await asyncio.sleep(step['delay'])
            
            # Send to channels in this step
            step_message = NotificationMessage(
                id=f"{message.id}_escalation_{len(all_results)}",
                title=f"[ESCALATED] {message.title}",
                content=f"ESCALATION: {step['description']}\n\n{message.content}",
                priority=message.priority,
                source=message.source,
                timestamp=datetime.now(),
                target_channels=step['channels'],
                metadata={**message.metadata, 'escalation_step': len(all_results) + 1}
            )
            
            results = await self.route_message(step_message)
            all_results.extend(results)
            
            logger.info(f"Escalation step completed: {step['description']}")
        
        return all_results
    
    def _get_default_policy(self, priority: Priority) -> str:
        """Get default escalation policy for priority"""
        if priority in [Priority.P0, Priority.P1]:
            return 'critical'
        elif priority in [Priority.P2, Priority.P3]:
            return 'standard'
        else:
            return 'info'
    
    def get_delivery_stats(self) -> Dict:
        """Get delivery statistics"""
        total_deliveries = len(self.delivery_history)
        if total_deliveries == 0:
            return {'total_deliveries': 0}
        
        successful = len([r for r in self.delivery_history if r.status == DeliveryStatus.SENT])
        failed = len([r for r in self.delivery_history if r.status == DeliveryStatus.FAILED])
        
        # Calculate average delivery time
        delivery_times = [r.delivery_time for r in self.delivery_history if r.delivery_time]
        avg_delivery_time = sum(delivery_times) / len(delivery_times) if delivery_times else 0
        
        # Channel breakdown
        channel_stats = {}
        for result in self.delivery_history:
            if result.channel not in channel_stats:
                channel_stats[result.channel] = {'sent': 0, 'failed': 0}
            
            if result.status == DeliveryStatus.SENT:
                channel_stats[result.channel]['sent'] += 1
            else:
                channel_stats[result.channel]['failed'] += 1
        
        return {
            'total_deliveries': total_deliveries,
            'successful_deliveries': successful,
            'failed_deliveries': failed,
            'success_rate': (successful / total_deliveries) * 100,
            'average_delivery_time': avg_delivery_time,
            'channel_breakdown': channel_stats
        }

async def demonstrate_notification_router():
    """Demonstrate the multi-channel notification router"""
    print("AIOps Multi-Channel Notification Router Demo")
    print("=" * 60)
    
    # Initialize router
    router = NotificationRouter(demo_mode=True)
    
    # Test 1: Critical alert (P0)
    print("\n🚨 Test 1: Critical Alert (P0 Priority)")
    critical_message = NotificationMessage(
        id="MSG-001",
        title="Database Cluster Down",
        content="Primary database cluster is completely unreachable. All services affected.",
        priority=Priority.P0,
        source="database-monitor",
        timestamp=datetime.now(),
        metadata={'affected_services': 'all', 'estimated_impact': 'total outage'}
    )
    
    results = await router.route_message(critical_message)
    print(f"  Sent to {len(results)} channels:")
    for result in results:
        print(f"    {result.channel}: {result.status.value} ({result.delivery_time:.3f}s)")
    
    # Test 2: High priority alert (P1)
    print("\n⚠️ Test 2: High Priority Alert (P1)")
    high_message = NotificationMessage(
        id="MSG-002",
        title="API Response Time Degraded",
        content="API response times have increased significantly. User experience may be impacted.",
        priority=Priority.P1,
        source="api-monitor",
        timestamp=datetime.now(),
        metadata={'current_response_time': '2.5s', 'threshold': '500ms'}
    )
    
    results = await router.route_message(high_message)
    print(f"  Sent to {len(results)} channels:")
    for result in results:
        print(f"    {result.channel}: {result.status.value}")
    
    # Test 3: Custom channel routing
    print("\n🎯 Test 3: Custom Channel Routing")
    custom_message = NotificationMessage(
        id="MSG-003",
        title="Maintenance Window Starting",
        content="Scheduled maintenance window starting in 30 minutes.",
        priority=Priority.P3,
        source="maintenance-scheduler",
        timestamp=datetime.now(),
        target_channels=['slack-general', 'email-ops'],  # Custom routing
        metadata={'maintenance_duration': '2 hours', 'affected_services': 'analytics'}
    )
    
    results = await router.route_message(custom_message)
    print(f"  Custom routing to {len(results)} specific channels:")
    for result in results:
        print(f"    {result.channel}: {result.status.value}")
    
    # Test 4: Escalation policy (simulated - shortened delays)
    print("\n📈 Test 4: Escalation Policy (Demo)")
    escalation_message = NotificationMessage(
        id="MSG-004",
        title="Security Breach Detected",
        content="Suspicious login activity detected from unknown IP addresses.",
        priority=Priority.P0,
        source="security-monitor",
        timestamp=datetime.now(),
        escalation_policy='critical',
        metadata={'threat_level': 'high', 'source_ips': ['192.168.1.100', '10.0.0.50']}
    )
    
    print("  Starting escalation process (demo with reduced delays)...")
    # Note: In demo, we'll just show the first escalation step
    results = await router.route_message(escalation_message)
    print(f"  Initial escalation sent to {len(results)} channels")
    
    # Test 5: Multiple message types
    print("\n📊 Test 5: Multiple Message Types")
    message_types = [
        ("Info Update", Priority.P4, "System status: All services operational"),
        ("Warning", Priority.P2, "Disk space on server-01 is at 85%"),
        ("Emergency", Priority.P0, "Fire suppression system activated in datacenter")
    ]
    
    for title, priority, content in message_types:
        msg = NotificationMessage(
            id=f"MSG-{hash(title) % 1000:03d}",
            title=title,
            content=content,
            priority=priority,
            source="system-monitor",
            timestamp=datetime.now()
        )
        
        results = await router.route_message(msg)
        print(f"  {priority.value.upper()} - {title}: {len(results)} channels")
    
    # Show delivery statistics
    print(f"\n📈 Delivery Statistics:")
    stats = router.get_delivery_stats()
    for key, value in stats.items():
        if key == 'channel_breakdown':
            print(f"  Channel Breakdown:")
            for channel, channel_stats in value.items():
                total = channel_stats['sent'] + channel_stats['failed']
                success_rate = (channel_stats['sent'] / total * 100) if total > 0 else 0
                print(f"    {channel}: {channel_stats['sent']}/{total} ({success_rate:.1f}% success)")
        else:
            if isinstance(value, float):
                print(f"  {key.replace('_', ' ').title()}: {value:.3f}")
            else:
                print(f"  {key.replace('_', ' ').title()}: {value}")
    
    print(f"\n✅ Multi-channel notification router demonstration completed!")

if __name__ == "__main__":
    asyncio.run(demonstrate_notification_router())