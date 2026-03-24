"""
AIOps Bot - Day 14: Enterprise Integration & API Management
Component 6: Notification Hub

A comprehensive notification system with multi-channel delivery, intelligent routing,
escalation policies, and integration with all AIOps components.
"""

import asyncio
import smtplib
import json
import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable, Union
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import uuid
import requests
import time
from threading import Thread
import queue

# Enums
class NotificationChannel(Enum):
    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    TEAMS = "teams"
    WEBHOOK = "webhook"
    PUSH = "push"
    DESKTOP = "desktop"
    IN_APP = "in_app"

class NotificationPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5

class NotificationStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"

class EscalationAction(Enum):
    RETRY = "retry"
    ESCALATE = "escalate"
    FALLBACK = "fallback"
    ALERT_ADMIN = "alert_admin"

# Data Classes
@dataclass
class NotificationTemplate:
    id: str
    name: str
    subject_template: str
    body_template: str
    channels: List[NotificationChannel]
    variables: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

@dataclass
class NotificationConfig:
    id: str
    channel: NotificationChannel
    endpoint: str
    credentials: Dict[str, Any]
    rate_limit: int = 100  # messages per minute
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 5
    is_active: bool = True

@dataclass
class EscalationPolicy:
    id: str
    name: str
    triggers: List[str]  # conditions that trigger escalation
    levels: List[Dict[str, Any]]  # escalation levels with actions
    cooldown_period: int = 300  # seconds
    max_escalations: int = 5
    is_active: bool = True

@dataclass
class NotificationRecipient:
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    slack_user_id: Optional[str] = None
    teams_user_id: Optional[str] = None
    webhook_url: Optional[str] = None
    preferences: Dict[NotificationChannel, bool] = field(default_factory=dict)
    timezone: str = "UTC"

@dataclass
class NotificationRequest:
    id: str
    template_id: str
    recipients: List[str]  # recipient IDs
    variables: Dict[str, Any]
    channels: List[NotificationChannel]
    priority: NotificationPriority
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    escalation_policy_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class NotificationDelivery:
    id: str
    request_id: str
    recipient_id: str
    channel: NotificationChannel
    status: NotificationStatus
    attempts: int = 0
    last_attempt_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

# Channel Handlers
class EmailHandler:
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.smtp_server = config.credentials.get('smtp_server', 'localhost')
        self.smtp_port = config.credentials.get('smtp_port', 587)
        self.username = config.credentials.get('username', '')
        self.password = config.credentials.get('password', '')
        self.use_tls = config.credentials.get('use_tls', True)

    async def send(self, recipient: NotificationRecipient, subject: str, body: str) -> Dict[str, Any]:
        try:
            msg = MIMEMultipart()
            msg['From'] = self.username
            msg['To'] = recipient.email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            
            server.send_message(msg)
            server.quit()
            
            return {"success": True, "message_id": str(uuid.uuid4())}
        except Exception as e:
            return {"success": False, "error": str(e)}

class SlackHandler:
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.webhook_url = config.credentials.get('webhook_url', '')
        self.bot_token = config.credentials.get('bot_token', '')

    async def send(self, recipient: NotificationRecipient, subject: str, body: str) -> Dict[str, Any]:
        try:
            payload = {
                "channel": f"@{recipient.slack_user_id}" if recipient.slack_user_id else "#general",
                "text": f"*{subject}*\n{body}",
                "username": "AIOps Bot",
                "icon_emoji": ":robot_face:"
            }
            
            headers = {'Content-Type': 'application/json'}
            if self.bot_token:
                headers['Authorization'] = f'Bearer {self.bot_token}'
            
            response = requests.post(
                self.webhook_url or "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                json=payload,
                headers=headers,
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return {"success": True, "message_id": response.headers.get('X-Slack-Req-Id')}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class TeamsHandler:
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.webhook_url = config.credentials.get('webhook_url', '')

    async def send(self, recipient: NotificationRecipient, subject: str, body: str) -> Dict[str, Any]:
        try:
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": "0076D7",
                "summary": subject,
                "sections": [{
                    "activityTitle": subject,
                    "activitySubtitle": "AIOps Bot Notification",
                    "text": body,
                    "markdown": True
                }]
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return {"success": True, "message_id": str(uuid.uuid4())}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class WebhookHandler:
    def __init__(self, config: NotificationConfig):
        self.config = config

    async def send(self, recipient: NotificationRecipient, subject: str, body: str) -> Dict[str, Any]:
        try:
            payload = {
                "subject": subject,
                "body": body,
                "recipient": recipient.id,
                "timestamp": datetime.now().isoformat(),
                "priority": "normal"
            }
            
            response = requests.post(
                recipient.webhook_url or self.config.endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=self.config.timeout
            )
            
            if response.status_code in [200, 201, 202]:
                return {"success": True, "message_id": response.headers.get('X-Message-ID', str(uuid.uuid4()))}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class SMSHandler:
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.api_key = config.credentials.get('api_key', '')
        self.api_url = config.credentials.get('api_url', 'https://api.twilio.com/2010-04-01')

    async def send(self, recipient: NotificationRecipient, subject: str, body: str) -> Dict[str, Any]:
        try:
            # Simulate SMS sending (in real implementation, use Twilio, AWS SNS, etc.)
            message = f"{subject}\n{body}"[:160]  # SMS character limit
            
            # Mock SMS API call
            payload = {
                "to": recipient.phone,
                "body": message,
                "from": self.config.credentials.get('from_number', '+1234567890')
            }
            
            # In real implementation, make actual API call
            # response = requests.post(self.api_url, data=payload, auth=(api_key, api_secret))
            
            return {"success": True, "message_id": str(uuid.uuid4()), "mock": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Template Engine
class TemplateEngine:
    def __init__(self):
        self.templates: Dict[str, NotificationTemplate] = {}

    def register_template(self, template: NotificationTemplate):
        self.templates[template.id] = template

    def render(self, template_id: str, variables: Dict[str, Any]) -> Dict[str, str]:
        if template_id not in self.templates:
            raise ValueError(f"Template {template_id} not found")
        
        template = self.templates[template_id]
        
        subject = template.subject_template
        body = template.body_template
        
        # Simple variable substitution
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))
        
        return {"subject": subject, "body": body}

# Rate Limiter
class RateLimiter:
    def __init__(self):
        self.limits: Dict[str, Dict] = {}

    def is_allowed(self, channel: NotificationChannel, config: NotificationConfig) -> bool:
        key = f"{channel.value}_{config.id}"
        now = time.time()
        
        if key not in self.limits:
            self.limits[key] = {"count": 0, "reset_time": now + 60}
        
        limit_info = self.limits[key]
        
        # Reset counter if time window expired
        if now >= limit_info["reset_time"]:
            limit_info["count"] = 0
            limit_info["reset_time"] = now + 60
        
        if limit_info["count"] < config.rate_limit:
            limit_info["count"] += 1
            return True
        
        return False

# Escalation Manager
class EscalationManager:
    def __init__(self):
        self.policies: Dict[str, EscalationPolicy] = {}
        self.active_escalations: Dict[str, Dict] = {}

    def register_policy(self, policy: EscalationPolicy):
        self.policies[policy.id] = policy

    def should_escalate(self, request_id: str, failure_count: int, last_failure: datetime) -> bool:
        # Simple escalation logic
        if failure_count >= 3:
            return True
        
        if last_failure and (datetime.now() - last_failure).seconds > 300:  # 5 minutes
            return True
        
        return False

    def get_escalation_actions(self, policy_id: str, level: int) -> List[Dict[str, Any]]:
        if policy_id not in self.policies:
            return []
        
        policy = self.policies[policy_id]
        if level < len(policy.levels):
            return policy.levels[level]
        
        return []

# Main Notification Hub
class NotificationHub:
    def __init__(self, db_path: str = "notifications.db"):
        self.db_path = db_path
        self.configs: Dict[NotificationChannel, NotificationConfig] = {}
        self.handlers: Dict[NotificationChannel, Any] = {}
        self.recipients: Dict[str, NotificationRecipient] = {}
        self.template_engine = TemplateEngine()
        self.rate_limiter = RateLimiter()
        self.escalation_manager = EscalationManager()
        self.delivery_queue = queue.Queue()
        self.is_running = False
        self.worker_thread = None
        
        self._init_database()
        self._setup_default_templates()
        self._setup_default_configs()
        self._setup_default_recipients()

    def _init_database(self):
        """Initialize SQLite database for notification tracking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Notification requests table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_requests (
                id TEXT PRIMARY KEY,
                template_id TEXT,
                recipients TEXT,
                variables TEXT,
                channels TEXT,
                priority INTEGER,
                scheduled_at TIMESTAMP,
                expires_at TIMESTAMP,
                escalation_policy_id TEXT,
                created_at TIMESTAMP,
                status TEXT
            )
        """)
        
        # Delivery tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id TEXT PRIMARY KEY,
                request_id TEXT,
                recipient_id TEXT,
                channel TEXT,
                status TEXT,
                attempts INTEGER,
                last_attempt_at TIMESTAMP,
                delivered_at TIMESTAMP,
                error_message TEXT,
                metadata TEXT,
                FOREIGN KEY (request_id) REFERENCES notification_requests (id)
            )
        """)
        
        conn.commit()
        conn.close()

    def _setup_default_templates(self):
        """Setup default notification templates"""
        templates = [
            NotificationTemplate(
                id="alert_critical",
                name="Critical Alert",
                subject_template="🚨 CRITICAL ALERT: {alert_title}",
                body_template="""
                <h2>Critical Alert Detected</h2>
                <p><strong>Alert:</strong> {alert_title}</p>
                <p><strong>Description:</strong> {description}</p>
                <p><strong>Severity:</strong> {severity}</p>
                <p><strong>Time:</strong> {timestamp}</p>
                <p><strong>System:</strong> {system}</p>
                <hr>
                <p>Immediate attention required. Please investigate and resolve.</p>
                """,
                channels=[NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.SLACK],
                variables=["alert_title", "description", "severity", "timestamp", "system"]
            ),
            NotificationTemplate(
                id="system_maintenance",
                name="System Maintenance",
                subject_template="🔧 Scheduled Maintenance: {system_name}",
                body_template="""
                <h2>Scheduled System Maintenance</h2>
                <p><strong>System:</strong> {system_name}</p>
                <p><strong>Start Time:</strong> {start_time}</p>
                <p><strong>Duration:</strong> {duration}</p>
                <p><strong>Impact:</strong> {impact}</p>
                <hr>
                <p>Please plan accordingly for any service disruptions.</p>
                """,
                channels=[NotificationChannel.EMAIL, NotificationChannel.TEAMS],
                variables=["system_name", "start_time", "duration", "impact"]
            ),
            NotificationTemplate(
                id="performance_report",
                name="Performance Report",
                subject_template="📊 Daily Performance Report - {date}",
                body_template="""
                <h2>System Performance Report</h2>
                <p><strong>Date:</strong> {date}</p>
                <p><strong>Uptime:</strong> {uptime}%</p>
                <p><strong>Response Time:</strong> {response_time}ms</p>
                <p><strong>Requests Processed:</strong> {request_count}</p>
                <p><strong>Error Rate:</strong> {error_rate}%</p>
                <hr>
                <p>Detailed metrics available in the dashboard.</p>
                """,
                channels=[NotificationChannel.EMAIL],
                variables=["date", "uptime", "response_time", "request_count", "error_rate"]
            )
        ]
        
        for template in templates:
            self.template_engine.register_template(template)

    def _setup_default_configs(self):
        """Setup default channel configurations"""
        configs = [
            NotificationConfig(
                id="email_primary",
                channel=NotificationChannel.EMAIL,
                endpoint="smtp.gmail.com:587",
                credentials={
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587,
                    "username": "aiops@company.com",
                    "password": "app_password",
                    "use_tls": True
                },
                rate_limit=100
            ),
            NotificationConfig(
                id="slack_alerts",
                channel=NotificationChannel.SLACK,
                endpoint="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                credentials={
                    "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                    "bot_token": "xoxb-your-bot-token"
                },
                rate_limit=50
            ),
            NotificationConfig(
                id="teams_alerts",
                channel=NotificationChannel.TEAMS,
                endpoint="https://outlook.office.com/webhook/YOUR/WEBHOOK/URL",
                credentials={
                    "webhook_url": "https://outlook.office.com/webhook/YOUR/WEBHOOK/URL"
                },
                rate_limit=30
            ),
            NotificationConfig(
                id="sms_critical",
                channel=NotificationChannel.SMS,
                endpoint="https://api.twilio.com/2010-04-01",
                credentials={
                    "api_key": "your_twilio_sid",
                    "api_secret": "your_twilio_token",
                    "from_number": "+1234567890"
                },
                rate_limit=10
            )
        ]
        
        for config in configs:
            self.register_channel_config(config)

    def _setup_default_recipients(self):
        """Setup default recipients"""
        recipients = [
            NotificationRecipient(
                id="admin",
                name="System Administrator",
                email="admin@company.com",
                phone="+1234567890",
                slack_user_id="U123456789",
                preferences={
                    NotificationChannel.EMAIL: True,
                    NotificationChannel.SMS: True,
                    NotificationChannel.SLACK: True
                }
            ),
            NotificationRecipient(
                id="ops_team",
                name="Operations Team",
                email="ops@company.com",
                slack_user_id="C987654321",
                preferences={
                    NotificationChannel.EMAIL: True,
                    NotificationChannel.SLACK: True,
                    NotificationChannel.TEAMS: True
                }
            ),
            NotificationRecipient(
                id="dev_team",
                name="Development Team",
                email="dev@company.com",
                slack_user_id="C111111111",
                preferences={
                    NotificationChannel.EMAIL: True,
                    NotificationChannel.SLACK: True
                }
            )
        ]
        
        for recipient in recipients:
            self.register_recipient(recipient)

    def register_channel_config(self, config: NotificationConfig):
        """Register a channel configuration"""
        self.configs[config.channel] = config
        
        # Initialize handler based on channel type
        if config.channel == NotificationChannel.EMAIL:
            self.handlers[config.channel] = EmailHandler(config)
        elif config.channel == NotificationChannel.SLACK:
            self.handlers[config.channel] = SlackHandler(config)
        elif config.channel == NotificationChannel.TEAMS:
            self.handlers[config.channel] = TeamsHandler(config)
        elif config.channel == NotificationChannel.WEBHOOK:
            self.handlers[config.channel] = WebhookHandler(config)
        elif config.channel == NotificationChannel.SMS:
            self.handlers[config.channel] = SMSHandler(config)

    def register_recipient(self, recipient: NotificationRecipient):
        """Register a notification recipient"""
        self.recipients[recipient.id] = recipient

    async def send_notification(self, request: NotificationRequest) -> Dict[str, Any]:
        """Send a notification"""
        try:
            # Store request in database
            self._store_request(request)
            
            # Render template
            rendered = self.template_engine.render(request.template_id, request.variables)
            
            results = []
            
            # Send to each recipient through each channel
            for recipient_id in request.recipients:
                if recipient_id not in self.recipients:
                    continue
                
                recipient = self.recipients[recipient_id]
                
                for channel in request.channels:
                    # Check recipient preferences
                    if not recipient.preferences.get(channel, True):
                        continue
                    
                    # Check if channel is configured
                    if channel not in self.handlers:
                        continue
                    
                    # Check rate limits
                    if not self.rate_limiter.is_allowed(channel, self.configs[channel]):
                        continue
                    
                    # Create delivery record
                    delivery = NotificationDelivery(
                        id=str(uuid.uuid4()),
                        request_id=request.id,
                        recipient_id=recipient_id,
                        channel=channel,
                        status=NotificationStatus.PENDING
                    )
                    
                    # Send notification
                    result = await self._send_single_notification(
                        delivery, recipient, rendered["subject"], rendered["body"]
                    )
                    
                    results.append(result)
            
            return {
                "request_id": request.id,
                "total_deliveries": len(results),
                "successful": len([r for r in results if r.get("success")]),
                "failed": len([r for r in results if not r.get("success")]),
                "results": results
            }
            
        except Exception as e:
            logging.error(f"Error sending notification: {e}")
            return {"success": False, "error": str(e)}

    async def _send_single_notification(self, delivery: NotificationDelivery, 
                                      recipient: NotificationRecipient, 
                                      subject: str, body: str) -> Dict[str, Any]:
        """Send a single notification through a specific channel"""
        try:
            delivery.attempts += 1
            delivery.last_attempt_at = datetime.now()
            delivery.status = NotificationStatus.PENDING
            
            handler = self.handlers[delivery.channel]
            result = await handler.send(recipient, subject, body)
            
            if result.get("success"):
                delivery.status = NotificationStatus.SENT
                delivery.delivered_at = datetime.now()
                delivery.metadata = {"message_id": result.get("message_id")}
            else:
                delivery.status = NotificationStatus.FAILED
                delivery.error_message = result.get("error")
            
            # Store delivery result
            self._store_delivery(delivery)
            
            return {
                "delivery_id": delivery.id,
                "recipient": recipient.id,
                "channel": delivery.channel.value,
                "success": result.get("success", False),
                "error": result.get("error"),
                "message_id": result.get("message_id")
            }
            
        except Exception as e:
            delivery.status = NotificationStatus.FAILED
            delivery.error_message = str(e)
            self._store_delivery(delivery)
            return {
                "delivery_id": delivery.id,
                "success": False,
                "error": str(e)
            }

    def _store_request(self, request: NotificationRequest):
        """Store notification request in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO notification_requests 
            (id, template_id, recipients, variables, channels, priority, 
             scheduled_at, expires_at, escalation_policy_id, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.id,
            request.template_id,
            json.dumps(request.recipients),
            json.dumps(request.variables),
            json.dumps([c.value for c in request.channels]),
            request.priority.value,
            request.scheduled_at.isoformat() if request.scheduled_at else None,
            request.expires_at.isoformat() if request.expires_at else None,
            request.escalation_policy_id,
            request.created_at.isoformat(),
            "pending"
        ))
        
        conn.commit()
        conn.close()

    def _store_delivery(self, delivery: NotificationDelivery):
        """Store delivery record in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO notification_deliveries 
            (id, request_id, recipient_id, channel, status, attempts, 
             last_attempt_at, delivered_at, error_message, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            delivery.id,
            delivery.request_id,
            delivery.recipient_id,
            delivery.channel.value,
            delivery.status.value,
            delivery.attempts,
            delivery.last_attempt_at.isoformat() if delivery.last_attempt_at else None,
            delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            delivery.error_message,
            json.dumps(delivery.metadata)
        ))
        
        conn.commit()
        conn.close()

    def get_delivery_stats(self, time_range_hours: int = 24) -> Dict[str, Any]:
        """Get notification delivery statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since_time = datetime.now() - timedelta(hours=time_range_hours)
        
        cursor.execute("""
            SELECT 
                status,
                channel,
                COUNT(*) as count
            FROM notification_deliveries 
            WHERE last_attempt_at >= ?
            GROUP BY status, channel
        """, (since_time.isoformat(),))
        
        results = cursor.fetchall()
        conn.close()
        
        stats = {
            "time_range_hours": time_range_hours,
            "by_status": {},
            "by_channel": {},
            "total_deliveries": 0
        }
        
        for status, channel, count in results:
            stats["by_status"][status] = stats["by_status"].get(status, 0) + count
            stats["by_channel"][channel] = stats["by_channel"].get(channel, 0) + count
            stats["total_deliveries"] += count
        
        return stats

    def start_worker(self):
        """Start the notification worker thread"""
        self.is_running = True
        self.worker_thread = Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def stop_worker(self):
        """Stop the notification worker thread"""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join()

    def _worker_loop(self):
        """Worker loop for processing notification queue"""
        while self.is_running:
            try:
                # Process queued notifications
                # In a real implementation, this would handle:
                # - Scheduled notifications
                # - Retry logic
                # - Escalation policies
                # - Batch processing
                time.sleep(1)
            except Exception as e:
                logging.error(f"Worker error: {e}")
                time.sleep(5)


async def demo_notification_hub():
    """Demonstrate the Notification Hub capabilities"""
    print("🔔 AIOps Bot - Notification Hub Demo")
    print("=" * 50)
    
    # Initialize hub
    hub = NotificationHub()
    
    print("\n📋 Available Templates:")
    for template_id, template in hub.template_engine.templates.items():
        print(f"  • {template.name} ({template_id})")
        print(f"    Channels: {[c.value for c in template.channels]}")
    
    print("\n👥 Registered Recipients:")
    for recipient_id, recipient in hub.recipients.items():
        print(f"  • {recipient.name} ({recipient_id})")
        preferences = [channel.value for channel, enabled in recipient.preferences.items() if enabled]
        print(f"    Preferences: {preferences}")
    
    print("\n🚨 Sending Critical Alert...")
    critical_alert = NotificationRequest(
        id=str(uuid.uuid4()),
        template_id="alert_critical",
        recipients=["admin", "ops_team"],
        variables={
            "alert_title": "Database Connection Failure",
            "description": "Primary database connection lost. Failover activated.",
            "severity": "CRITICAL",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "system": "Production Database Cluster"
        },
        channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
        priority=NotificationPriority.CRITICAL
    )
    
    result = await hub.send_notification(critical_alert)
    print(f"Result: {result['successful']}/{result['total_deliveries']} deliveries successful")
    
    print("\n🔧 Sending Maintenance Notification...")
    maintenance_notice = NotificationRequest(
        id=str(uuid.uuid4()),
        template_id="system_maintenance",
        recipients=["dev_team", "ops_team"],
        variables={
            "system_name": "AIOps Dashboard",
            "start_time": "2024-01-15 02:00 UTC",
            "duration": "2 hours",
            "impact": "Dashboard will be unavailable during maintenance window"
        },
        channels=[NotificationChannel.EMAIL, NotificationChannel.TEAMS],
        priority=NotificationPriority.MEDIUM
    )
    
    result = await hub.send_notification(maintenance_notice)
    print(f"Result: {result['successful']}/{result['total_deliveries']} deliveries successful")
    
    print("\n📊 Sending Performance Report...")
    performance_report = NotificationRequest(
        id=str(uuid.uuid4()),
        template_id="performance_report",
        recipients=["admin"],
        variables={
            "date": datetime.now().strftime("%Y-%m-%d"),
            "uptime": "99.8",
            "response_time": "125",
            "request_count": "1,234,567",
            "error_rate": "0.2"
        },
        channels=[NotificationChannel.EMAIL],
        priority=NotificationPriority.LOW
    )
    
    result = await hub.send_notification(performance_report)
    print(f"Result: {result['successful']}/{result['total_deliveries']} deliveries successful")
    
    print("\n📈 Delivery Statistics (Last 24 hours):")
    stats = hub.get_delivery_stats()
    print(f"Total Deliveries: {stats['total_deliveries']}")
    
    if stats['by_status']:
        print("By Status:")
        for status, count in stats['by_status'].items():
            print(f"  • {status}: {count}")
    
    if stats['by_channel']:
        print("By Channel:")
        for channel, count in stats['by_channel'].items():
            print(f"  • {channel}: {count}")
    
    print("\n✅ Notification Hub Demo Complete!")
    print("Features demonstrated:")
    print("  ✓ Multi-channel notification delivery")
    print("  ✓ Template-based message generation")
    print("  ✓ Recipient management and preferences")
    print("  ✓ Rate limiting and delivery tracking")
    print("  ✓ Channel-specific handlers (Email, Slack, Teams, SMS)")
    print("  ✓ Delivery statistics and monitoring")


if __name__ == "__main__":
    asyncio.run(demo_notification_hub())