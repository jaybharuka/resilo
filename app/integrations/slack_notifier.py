#!/usr/bin/env python3
"""
AIOps Slack Notification System
Comprehensive Slack integration with webhooks, channel routing, threading, and bot interactions

Features:
- Slack webhook integration with rich message formatting
- Multi-channel routing based on alert severity
- Thread management for related alerts
- Interactive buttons and slash commands
- Message templates and customization
- Delivery tracking and analytics
"""

import asyncio
import aiohttp
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('slack_notifier')

class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class MessageType(Enum):
    """Slack message types"""
    ALERT = "alert"
    INCIDENT = "incident"
    REPORT = "report"
    STATUS = "status"
    COMMAND_RESPONSE = "command_response"

@dataclass
class SlackChannel:
    """Slack channel configuration"""
    name: str
    webhook_url: str
    severity_filter: List[AlertSeverity] = field(default_factory=list)
    thread_alerts: bool = True
    mention_users: List[str] = field(default_factory=list)

@dataclass
class SlackMessage:
    """Slack message structure"""
    channel: str
    text: str
    blocks: List[Dict] = field(default_factory=list)
    attachments: List[Dict] = field(default_factory=list)
    thread_ts: Optional[str] = None
    username: Optional[str] = "AIOps Bot"
    icon_emoji: Optional[str] = ":robot_face:"

@dataclass
class AlertContext:
    """Alert context for Slack notifications"""
    alert_id: str
    title: str
    description: str
    severity: AlertSeverity
    source: str
    timestamp: datetime
    metrics: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

class SlackAPIClient:
    """Mock Slack API client for demo mode"""
    
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.sent_messages = []
        self.threads = {}
        
    async def send_webhook_message(self, webhook_url: str, message: Dict) -> Dict:
        """Send message via webhook"""
        if self.demo_mode:
            logger.info(f"[DEMO] Sending Slack webhook message to {webhook_url}")
            logger.info(f"[DEMO] Message: {json.dumps(message, indent=2)}")
            
            # Simulate successful response
            response = {
                'ok': True,
                'ts': f"{int(time.time())}.{len(self.sent_messages):06d}",
                'channel': message.get('channel', 'C1234567890'),
                'message': message
            }
            self.sent_messages.append(response)
            return response
        else:
            # Real webhook call
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message) as response:
                    return await response.json()
    
    async def update_message(self, channel: str, ts: str, message: Dict) -> Dict:
        """Update existing message"""
        if self.demo_mode:
            logger.info(f"[DEMO] Updating Slack message {ts} in {channel}")
            logger.info(f"[DEMO] Updated content: {json.dumps(message, indent=2)}")
            return {'ok': True, 'ts': ts}
        else:
            # Real API call would go here
            return {'ok': True, 'ts': ts}

class SlackMessageBuilder:
    """Build rich Slack messages with blocks and attachments"""
    
    @staticmethod
    def build_alert_message(alert: AlertContext, include_actions: bool = True) -> Dict:
        """Build alert message with rich formatting"""
        
        # Determine color based on severity
        severity_colors = {
            AlertSeverity.CRITICAL: "#FF0000",
            AlertSeverity.HIGH: "#FF6600", 
            AlertSeverity.MEDIUM: "#FFCC00",
            AlertSeverity.LOW: "#00FF00",
            AlertSeverity.INFO: "#0099FF"
        }
        
        # Build main message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 {alert.severity.value.upper()} Alert: {alert.title}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Alert ID:*\n{alert.alert_id}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Source:*\n{alert.source}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{alert.severity.value.title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{alert.description}"
                }
            }
        ]
        
        # Add metrics if available
        if alert.metrics:
            metrics_text = "\n".join([f"• {k}: {v}" for k, v in alert.metrics.items()])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Metrics:*\n{metrics_text}"
                }
            })
        
        # Add tags if available
        if alert.tags:
            tags_text = " ".join([f"`{tag}`" for tag in alert.tags])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Tags:* {tags_text}"
                }
            })
        
        # Add action buttons
        if include_actions:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Acknowledge"
                        },
                        "style": "primary",
                        "value": f"ack_{alert.alert_id}",
                        "action_id": "acknowledge_alert"
                    },
                    {
                        "type": "button", 
                        "text": {
                            "type": "plain_text",
                            "text": "Investigate"
                        },
                        "value": f"investigate_{alert.alert_id}",
                        "action_id": "investigate_alert"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Resolve"
                        },
                        "style": "danger",
                        "value": f"resolve_{alert.alert_id}",
                        "action_id": "resolve_alert"
                    }
                ]
            })
        
        return {
            "text": f"{alert.severity.value.upper()} Alert: {alert.title}",
            "blocks": blocks,
            "attachments": [
                {
                    "color": severity_colors[alert.severity],
                    "fallback": f"{alert.severity.value.upper()} Alert: {alert.title}"
                }
            ]
        }
    
    @staticmethod
    def build_status_message(title: str, status: str, details: Dict = None) -> Dict:
        """Build system status message"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 {title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Status:* {status}\n*Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            }
        ]
        
        if details:
            details_text = "\n".join([f"• {k}: {v}" for k, v in details.items()])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Details:*\n{details_text}"
                }
            })
        
        return {
            "text": title,
            "blocks": blocks
        }
    
    @staticmethod
    def build_report_message(title: str, summary: str, metrics: Dict = None) -> Dict:
        """Build analytics report message"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📈 {title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": summary
                }
            }
        ]
        
        if metrics:
            metrics_fields = []
            for key, value in metrics.items():
                metrics_fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:*\n{value}"
                })
            
            blocks.append({
                "type": "section",
                "fields": metrics_fields
            })
        
        return {
            "text": title,
            "blocks": blocks
        }

class SlackNotificationSystem:
    """Main Slack notification system"""
    
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.api_client = SlackAPIClient(demo_mode)
        self.message_builder = SlackMessageBuilder()
        
        # Channel configuration
        self.channels = {
            'alerts': SlackChannel(
                name='alerts',
                webhook_url=os.getenv('SLACK_ALERTS_WEBHOOK', 'https://hooks.slack.com/services/DEMO/ALERTS/WEBHOOK'),
                severity_filter=[AlertSeverity.HIGH, AlertSeverity.CRITICAL],
                thread_alerts=True,
                mention_users=['@here']
            ),
            'general': SlackChannel(
                name='general',
                webhook_url=os.getenv('SLACK_GENERAL_WEBHOOK', 'https://hooks.slack.com/services/DEMO/GENERAL/WEBHOOK'),
                severity_filter=[AlertSeverity.INFO, AlertSeverity.LOW, AlertSeverity.MEDIUM],
                thread_alerts=True
            ),
            'incidents': SlackChannel(
                name='incidents',
                webhook_url=os.getenv('SLACK_INCIDENTS_WEBHOOK', 'https://hooks.slack.com/services/DEMO/INCIDENTS/WEBHOOK'),
                severity_filter=[AlertSeverity.CRITICAL],
                thread_alerts=False,
                mention_users=['@channel']
            )
        }
        
        # Thread tracking
        self.alert_threads = {}
        self.delivery_stats = {
            'sent': 0,
            'failed': 0,
            'threads_created': 0
        }
        
        logger.info(f"Slack notification system initialized (demo_mode={demo_mode})")
    
    async def send_alert(self, alert: AlertContext) -> List[Dict]:
        """Send alert to appropriate Slack channels"""
        results = []
        
        for channel_name, channel in self.channels.items():
            # Check if alert severity matches channel filter
            if not channel.severity_filter or alert.severity in channel.severity_filter:
                try:
                    # Build message
                    message = self.message_builder.build_alert_message(alert)
                    
                    # Add mentions if configured
                    if channel.mention_users:
                        mentions = ' '.join(channel.mention_users)
                        message['text'] = f"{mentions} {message['text']}"
                    
                    # Check for existing thread
                    thread_key = f"{alert.source}_{alert.title}"
                    if channel.thread_alerts and thread_key in self.alert_threads:
                        message['thread_ts'] = self.alert_threads[thread_key]
                    
                    # Send message
                    response = await self.api_client.send_webhook_message(
                        channel.webhook_url, 
                        message
                    )
                    
                    # Track thread if new
                    if channel.thread_alerts and 'ts' in response and thread_key not in self.alert_threads:
                        self.alert_threads[thread_key] = response['ts']
                        self.delivery_stats['threads_created'] += 1
                    
                    self.delivery_stats['sent'] += 1
                    results.append({
                        'channel': channel_name,
                        'status': 'success',
                        'response': response
                    })
                    
                    logger.info(f"Sent alert {alert.alert_id} to Slack channel {channel_name}")
                    
                except Exception as e:
                    self.delivery_stats['failed'] += 1
                    results.append({
                        'channel': channel_name,
                        'status': 'error',
                        'error': str(e)
                    })
                    logger.error(f"Failed to send alert to {channel_name}: {e}")
        
        return results
    
    async def send_status_update(self, title: str, status: str, details: Dict = None, channel: str = 'general') -> Dict:
        """Send system status update"""
        try:
            message = self.message_builder.build_status_message(title, status, details)
            
            if channel in self.channels:
                response = await self.api_client.send_webhook_message(
                    self.channels[channel].webhook_url,
                    message
                )
                logger.info(f"Sent status update to {channel}")
                return {'status': 'success', 'response': response}
            else:
                raise ValueError(f"Unknown channel: {channel}")
                
        except Exception as e:
            logger.error(f"Failed to send status update: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def send_report(self, title: str, summary: str, metrics: Dict = None, channel: str = 'general') -> Dict:
        """Send analytics report"""
        try:
            message = self.message_builder.build_report_message(title, summary, metrics)
            
            if channel in self.channels:
                response = await self.api_client.send_webhook_message(
                    self.channels[channel].webhook_url,
                    message
                )
                logger.info(f"Sent report to {channel}")
                return {'status': 'success', 'response': response}
            else:
                raise ValueError(f"Unknown channel: {channel}")
                
        except Exception as e:
            logger.error(f"Failed to send report: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def handle_slash_command(self, command: str, user_id: str, channel_id: str, text: str) -> Dict:
        """Handle Slack slash commands"""
        try:
            if command == '/aiops-status':
                # Get system status
                status_details = {
                    'Services': '5/5 Running',
                    'CPU Usage': '45%',
                    'Memory Usage': '67%',
                    'Last Alert': '2 minutes ago'
                }
                
                message = self.message_builder.build_status_message(
                    "AIOps System Status",
                    "All systems operational",
                    status_details
                )
                
                return {
                    'response_type': 'in_channel',
                    'text': message['text'],
                    'blocks': message['blocks']
                }
            
            elif command == '/aiops-alerts':
                # Get recent alerts summary
                return {
                    'response_type': 'ephemeral',
                    'text': f"Recent alerts summary requested by <@{user_id}>",
                    'blocks': [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Recent Alerts (Last 24h):*\n• 3 Critical\n• 7 High\n• 12 Medium\n• 23 Low"
                            }
                        }
                    ]
                }
            
            elif command == '/aiops-help':
                return {
                    'response_type': 'ephemeral',
                    'text': "AIOps Slack Commands",
                    'blocks': [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Available Commands:*\n• `/aiops-status` - System status\n• `/aiops-alerts` - Recent alerts\n• `/aiops-metrics` - Performance metrics\n• `/aiops-help` - This help message"
                            }
                        }
                    ]
                }
            
            else:
                return {
                    'response_type': 'ephemeral',
                    'text': f"Unknown command: {command}. Use `/aiops-help` for available commands."
                }
                
        except Exception as e:
            logger.error(f"Error handling slash command {command}: {e}")
            return {
                'response_type': 'ephemeral',
                'text': f"Error processing command: {str(e)}"
            }
    
    def get_delivery_stats(self) -> Dict:
        """Get delivery statistics"""
        return {
            'messages_sent': self.delivery_stats['sent'],
            'messages_failed': self.delivery_stats['failed'],
            'success_rate': (self.delivery_stats['sent'] / max(1, self.delivery_stats['sent'] + self.delivery_stats['failed'])) * 100,
            'threads_created': self.delivery_stats['threads_created'],
            'active_threads': len(self.alert_threads)
        }

async def demonstrate_slack_system():
    """Demonstrate Slack notification system"""
    print("AIOps Slack Notification System Demo")
    print("=" * 50)
    
    # Initialize system
    slack_system = SlackNotificationSystem(demo_mode=True)
    
    # Test 1: Send critical alert
    print("\n🚨 Test 1: Critical Alert")
    critical_alert = AlertContext(
        alert_id="ALERT-001",
        title="Database Connection Failure",
        description="Primary database connection pool exhausted. Service degradation detected.",
        severity=AlertSeverity.CRITICAL,
        source="database-monitor",
        timestamp=datetime.now(),
        metrics={
            'connection_pool_usage': '100%',
            'response_time': '5.2s',
            'error_rate': '15%'
        },
        tags=['database', 'critical', 'production']
    )
    
    results = await slack_system.send_alert(critical_alert)
    for result in results:
        print(f"  Channel {result['channel']}: {result['status']}")
    
    # Test 2: Send status update
    print("\n📊 Test 2: Status Update")
    status_result = await slack_system.send_status_update(
        "System Maintenance",
        "Scheduled maintenance in progress",
        {
            'Start Time': '10:00 PM',
            'Expected Duration': '2 hours',
            'Affected Services': 'Analytics Engine'
        }
    )
    print(f"  Status update: {status_result['status']}")
    
    # Test 3: Send analytics report
    print("\n📈 Test 3: Analytics Report")
    report_result = await slack_system.send_report(
        "Daily Performance Report",
        "System performance summary for the last 24 hours",
        {
            'Avg Response Time': '245ms',
            'Total Requests': '1.2M',
            'Error Rate': '0.1%',
            'Uptime': '99.9%'
        }
    )
    print(f"  Report sent: {report_result['status']}")
    
    # Test 4: Slash commands
    print("\n💬 Test 4: Slash Commands")
    commands = ['/aiops-status', '/aiops-alerts', '/aiops-help']
    for cmd in commands:
        response = await slack_system.handle_slash_command(
            cmd, 'U123456', 'C123456', ''
        )
        print(f"  {cmd}: {response['response_type']}")
    
    # Test 5: Threading alerts
    print("\n🧵 Test 5: Threaded Alerts")
    related_alert = AlertContext(
        alert_id="ALERT-002",
        title="Database Connection Failure",  # Same title to trigger threading
        description="Connection pool recovery in progress.",
        severity=AlertSeverity.HIGH,
        source="database-monitor",  # Same source
        timestamp=datetime.now(),
        metrics={'recovery_progress': '60%'}
    )
    
    thread_results = await slack_system.send_alert(related_alert)
    print(f"  Threaded alert sent to {len(thread_results)} channels")
    
    # Show delivery statistics
    print(f"\n📊 Delivery Statistics:")
    stats = slack_system.get_delivery_stats()
    for key, value in stats.items():
        print(f"  {key.replace('_', ' ').title()}: {value}")
    
    print(f"\n✅ Slack notification system demonstration completed!")

if __name__ == "__main__":
    asyncio.run(demonstrate_slack_system())