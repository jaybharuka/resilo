#!/usr/bin/env python3
"""
Enhanced Integration Hub
Universal notification system with multiple channels and intelligent routing
"""

import asyncio
import aiohttp
import smtplib
import json
import yaml
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import ssl
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class NotificationChannel(Enum):
    DISCORD = "discord"
    SLACK = "slack"
    EMAIL = "email"
    WEBHOOK = "webhook"
    TEAMS = "teams"
    TELEGRAM = "telegram"

class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class NotificationMessage:
    title: str
    content: str
    priority: NotificationPriority
    channels: List[NotificationChannel]
    data: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.data is None:
            self.data = {}

class EnhancedIntegrationHub:
    """Enhanced integration hub for multi-channel notifications"""
    
    def __init__(self):
        self.config = self.load_config()
        self.enabled_channels = self.detect_enabled_channels()
        self.notification_history = []
        self.delivery_stats = {channel.value: {"sent": 0, "failed": 0} for channel in NotificationChannel}
        
        logger.info(f"✅ Integration hub initialized with {len(self.enabled_channels)} channels")
    
    def load_config(self) -> Dict:
        """Load configuration"""
        try:
            with open('config/enterprise_config.yml', 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            return {}
    
    def detect_enabled_channels(self) -> List[NotificationChannel]:
        """Detect which notification channels are configured"""
        enabled = []
        credentials = self.config.get('credentials', {})
        
        # Discord
        if (credentials.get('discord', {}).get('bot_token') and 
            credentials.get('discord', {}).get('webhook_url')):
            enabled.append(NotificationChannel.DISCORD)
        
        # Slack
        if credentials.get('slack', {}).get('bot_token'):
            enabled.append(NotificationChannel.SLACK)
        
        # Email
        if (credentials.get('messaging', {}).get('smtp', {}).get('username') and 
            credentials.get('messaging', {}).get('smtp', {}).get('password')):
            enabled.append(NotificationChannel.EMAIL)
        
        # Webhook
        if credentials.get('webhook', {}).get('url'):
            enabled.append(NotificationChannel.WEBHOOK)
        
        # Teams
        if credentials.get('teams', {}).get('webhook_url'):
            enabled.append(NotificationChannel.TEAMS)
        
        # Telegram
        if (credentials.get('telegram', {}).get('bot_token') and 
            credentials.get('telegram', {}).get('chat_id')):
            enabled.append(NotificationChannel.TELEGRAM)
        
        logger.info(f"📡 Detected channels: {[c.value for c in enabled]}")
        return enabled
    
    async def send_notification(self, message: NotificationMessage) -> Dict[str, bool]:
        """Send notification to multiple channels"""
        results = {}
        
        # Filter channels to only enabled ones
        target_channels = [c for c in message.channels if c in self.enabled_channels]
        
        if not target_channels:
            logger.warning("⚠️ No enabled channels for notification")
            return {}
        
        # Create tasks for all channels
        tasks = []
        for channel in target_channels:
            task = self.send_to_channel(channel, message)
            tasks.append((channel, task))
        
        # Execute all tasks concurrently
        for channel, task in tasks:
            try:
                success = await task
                results[channel.value] = success
                
                if success:
                    self.delivery_stats[channel.value]["sent"] += 1
                    logger.info(f"✅ Sent to {channel.value}")
                else:
                    self.delivery_stats[channel.value]["failed"] += 1
                    logger.error(f"❌ Failed to send to {channel.value}")
                    
            except Exception as e:
                results[channel.value] = False
                self.delivery_stats[channel.value]["failed"] += 1
                logger.error(f"❌ Error sending to {channel.value}: {e}")
        
        # Store in history
        self.notification_history.append({
            'message': message,
            'results': results,
            'timestamp': datetime.now()
        })
        
        # Keep only last 100 notifications
        if len(self.notification_history) > 100:
            self.notification_history.pop(0)
        
        return results
    
    async def send_to_channel(self, channel: NotificationChannel, message: NotificationMessage) -> bool:
        """Send message to specific channel"""
        try:
            if channel == NotificationChannel.DISCORD:
                return await self.send_discord(message)
            elif channel == NotificationChannel.SLACK:
                return await self.send_slack(message)
            elif channel == NotificationChannel.EMAIL:
                return await self.send_email(message)
            elif channel == NotificationChannel.WEBHOOK:
                return await self.send_webhook(message)
            elif channel == NotificationChannel.TEAMS:
                return await self.send_teams(message)
            elif channel == NotificationChannel.TELEGRAM:
                return await self.send_telegram(message)
            else:
                logger.warning(f"⚠️ Unknown channel: {channel}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error in {channel.value}: {e}")
            return False
    
    async def send_discord(self, message: NotificationMessage) -> bool:
        """Send Discord notification"""
        webhook_url = self.config.get('credentials', {}).get('discord', {}).get('webhook_url')
        
        if not webhook_url:
            return False
        
        # Color coding based on priority
        color_map = {
            NotificationPriority.LOW: 0x28a745,      # Green
            NotificationPriority.MEDIUM: 0xffc107,   # Yellow
            NotificationPriority.HIGH: 0xfd7e14,     # Orange
            NotificationPriority.CRITICAL: 0xdc3545  # Red
        }
        
        embed = {
            "title": f"🤖 {message.title}",
            "description": message.content[:2000],  # Discord limit
            "color": color_map.get(message.priority, 0x007bff),
            "timestamp": message.timestamp.isoformat(),
            "footer": {
                "text": f"AIOps Monitor • Priority: {message.priority.value.upper()}"
            }
        }
        
        # Add fields from data
        if message.data:
            fields = []
            for key, value in list(message.data.items())[:10]:  # Max 10 fields
                fields.append({
                    "name": key.replace('_', ' ').title(),
                    "value": str(value)[:1024],  # Discord field limit
                    "inline": True
                })
            embed["fields"] = fields
        
        payload = {"embeds": [embed]}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return response.status == 204
        except Exception as e:
            logger.error(f"❌ Discord error: {e}")
            return False
    
    async def send_slack(self, message: NotificationMessage) -> bool:
        """Send Slack notification"""
        bot_token = self.config.get('credentials', {}).get('slack', {}).get('bot_token')
        channel = self.config.get('credentials', {}).get('slack', {}).get('channel', '#alerts')
        
        if not bot_token:
            return False
        
        # Priority emoji
        priority_emoji = {
            NotificationPriority.LOW: "🟢",
            NotificationPriority.MEDIUM: "🟡",
            NotificationPriority.HIGH: "🟠",
            NotificationPriority.CRITICAL: "🔴"
        }
        
        # Create blocks for rich formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{priority_emoji.get(message.priority, '🤖')} {message.title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message.content
                }
            }
        ]
        
        # Add data fields
        if message.data:
            fields = []
            for key, value in list(message.data.items())[:10]:
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key.replace('_', ' ').title()}:*\n{value}"
                })
            
            if fields:
                blocks.append({
                    "type": "section",
                    "fields": fields[:10]  # Slack limit
                })
        
        # Add footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"AIOps Monitor • {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')} • Priority: {message.priority.value.upper()}"
                }
            ]
        })
        
        payload = {
            "channel": channel,
            "blocks": blocks
        }
        
        try:
            headers = {"Authorization": f"Bearer {bot_token}"}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://slack.com/api/chat.postMessage",
                    json=payload,
                    headers=headers
                ) as response:
                    result = await response.json()
                    return result.get("ok", False)
        except Exception as e:
            logger.error(f"❌ Slack error: {e}")
            return False
    
    async def send_email(self, message: NotificationMessage) -> bool:
        """Send email notification"""
        smtp_config = self.config.get('credentials', {}).get('messaging', {}).get('smtp', {})
        
        if not smtp_config.get('username') or not smtp_config.get('password'):
            return False
        
        try:
            # Priority indicators
            priority_indicators = {
                NotificationPriority.LOW: "🟢 LOW",
                NotificationPriority.MEDIUM: "🟡 MEDIUM",
                NotificationPriority.HIGH: "🟠 HIGH",
                NotificationPriority.CRITICAL: "🔴 CRITICAL"
            }
            
            subject = f"AIOps Alert: {message.title} [{priority_indicators.get(message.priority, 'UNKNOWN')}]"
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = smtp_config['username']
            msg['To'] = smtp_config.get('recipient', 'admin@company.com')
            
            # Create HTML content
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #333;">🤖 AIOps Notification</h2>
                <h3 style="color: #667eea;">{message.title}</h3>
                <p>{message.content}</p>
                
                {self.format_email_data(message.data) if message.data else ''}
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    Generated at {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')} • 
                    Priority: {message.priority.value.upper()}
                </p>
            </body>
            </html>
            """
            
            # Create text content
            text_content = f"""
AIOps Notification

{message.title}
{'-' * len(message.title)}

{message.content}

Generated at {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Priority: {message.priority.value.upper()}
            """
            
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            context = ssl.create_default_context()
            server = smtp_config.get('server', 'smtp.gmail.com')
            port = smtp_config.get('port', 587)
            
            with smtplib.SMTP(server, port) as smtp:
                if smtp_config.get('use_tls', True):
                    smtp.starttls(context=context)
                smtp.login(smtp_config['username'], smtp_config['password'])
                smtp.send_message(msg)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Email error: {e}")
            return False
    
    def format_email_data(self, data: Dict) -> str:
        """Format data for email"""
        if not data:
            return ""
        
        html = "<h4>Additional Information:</h4><ul>"
        for key, value in data.items():
            html += f"<li><strong>{key.replace('_', ' ').title()}:</strong> {value}</li>"
        html += "</ul>"
        return html
    
    async def send_webhook(self, message: NotificationMessage) -> bool:
        """Send webhook notification"""
        webhook_url = self.config.get('credentials', {}).get('webhook', {}).get('url')
        
        if not webhook_url:
            return False
        
        payload = {
            "title": message.title,
            "content": message.content,
            "priority": message.priority.value,
            "timestamp": message.timestamp.isoformat(),
            "data": message.data or {}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return 200 <= response.status < 300
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return False
    
    async def send_teams(self, message: NotificationMessage) -> bool:
        """Send Microsoft Teams notification"""
        webhook_url = self.config.get('credentials', {}).get('teams', {}).get('webhook_url')
        
        if not webhook_url:
            return False
        
        # Color coding
        color_map = {
            NotificationPriority.LOW: "Good",
            NotificationPriority.MEDIUM: "Warning",
            NotificationPriority.HIGH: "Attention",
            NotificationPriority.CRITICAL: "Error"
        }
        
        # Create adaptive card
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0078D4",
            "summary": message.title,
            "sections": [
                {
                    "activityTitle": f"🤖 {message.title}",
                    "activitySubtitle": f"Priority: {message.priority.value.upper()}",
                    "text": message.content,
                    "facts": []
                }
            ]
        }
        
        # Add data as facts
        if message.data:
            for key, value in list(message.data.items())[:10]:
                card["sections"][0]["facts"].append({
                    "name": key.replace('_', ' ').title(),
                    "value": str(value)
                })
        
        # Add timestamp
        card["sections"][0]["facts"].append({
            "name": "Timestamp",
            "value": message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=card) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"❌ Teams error: {e}")
            return False
    
    async def send_telegram(self, message: NotificationMessage) -> bool:
        """Send Telegram notification"""
        bot_token = self.config.get('credentials', {}).get('telegram', {}).get('bot_token')
        chat_id = self.config.get('credentials', {}).get('telegram', {}).get('chat_id')
        
        if not bot_token or not chat_id:
            return False
        
        # Priority emoji
        priority_emoji = {
            NotificationPriority.LOW: "🟢",
            NotificationPriority.MEDIUM: "🟡",
            NotificationPriority.HIGH: "🟠",
            NotificationPriority.CRITICAL: "🔴"
        }
        
        # Format message
        text = f"{priority_emoji.get(message.priority, '🤖')} *{message.title}*\n\n"
        text += f"{message.content}\n\n"
        
        if message.data:
            text += "*Additional Information:*\n"
            for key, value in list(message.data.items())[:5]:
                text += f"• {key.replace('_', ' ').title()}: {value}\n"
            text += "\n"
        
        text += f"⏰ {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"🤖 Priority: {message.priority.value.upper()}"
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    result = await response.json()
                    return result.get("ok", False)
        except Exception as e:
            logger.error(f"❌ Telegram error: {e}")
            return False
    
    def get_delivery_stats(self) -> Dict:
        """Get delivery statistics"""
        total_sent = sum(stats["sent"] for stats in self.delivery_stats.values())
        total_failed = sum(stats["failed"] for stats in self.delivery_stats.values())
        total_attempts = total_sent + total_failed
        
        success_rate = (total_sent / total_attempts * 100) if total_attempts > 0 else 0
        
        return {
            "total_sent": total_sent,
            "total_failed": total_failed,
            "success_rate": success_rate,
            "channels": self.delivery_stats,
            "enabled_channels": [c.value for c in self.enabled_channels]
        }
    
    def create_aiops_notification(self, analysis: Dict) -> NotificationMessage:
        """Create AIOps notification from analysis"""
        anomalies = analysis.get('anomalies', [])
        
        if not anomalies:
            return NotificationMessage(
                title="System Health Check - All Clear",
                content="✅ All systems operating normally. No anomalies detected.",
                priority=NotificationPriority.LOW,
                channels=[NotificationChannel.DISCORD, NotificationChannel.SLACK],
                data={
                    "cpu_usage": f"{analysis.get('metrics', {}).get('cpu_percent', 0):.1f}%",
                    "memory_usage": f"{analysis.get('metrics', {}).get('memory_percent', 0):.1f}%",
                    "status": "healthy"
                }
            )
        
        # Determine priority
        severity_levels = [a.get('severity', 'medium') for a in anomalies]
        if 'critical' in severity_levels:
            priority = NotificationPriority.CRITICAL
            channels = list(NotificationChannel)  # All channels for critical
        elif 'high' in severity_levels:
            priority = NotificationPriority.HIGH
            channels = [NotificationChannel.DISCORD, NotificationChannel.SLACK, NotificationChannel.EMAIL]
        else:
            priority = NotificationPriority.MEDIUM
            channels = [NotificationChannel.DISCORD, NotificationChannel.SLACK]
        
        # Create content
        issue_count = len(anomalies)
        content = f"Detected {issue_count} system issue{'s' if issue_count > 1 else ''}:\n\n"
        
        for anomaly in anomalies[:3]:  # Limit to top 3
            content += f"• {anomaly.get('type', '').replace('_', ' ').title()}: "
            content += f"{anomaly.get('current_value', 0):.1f}% ({anomaly.get('severity', 'medium')})\n"
        
        if len(anomalies) > 3:
            content += f"• And {len(anomalies) - 3} more issues...\n"
        
        # Add AI analysis if available
        ai_analysis = analysis.get('ai_analysis', '')
        if ai_analysis:
            content += f"\n🧠 AI Analysis: {ai_analysis[:200]}..."
        
        # Add resolution results
        resolution_results = analysis.get('resolution_results', [])
        if resolution_results:
            successful_resolutions = [r for r in resolution_results if r.get('success')]
            if successful_resolutions:
                content += f"\n\n✅ {len(successful_resolutions)} issue(s) automatically resolved"
        
        return NotificationMessage(
            title=f"AIOps Alert: {issue_count} Issues Detected",
            content=content,
            priority=priority,
            channels=channels,
            data={
                "anomaly_count": issue_count,
                "cpu_usage": f"{analysis.get('metrics', {}).get('cpu_percent', 0):.1f}%",
                "memory_usage": f"{analysis.get('metrics', {}).get('memory_percent', 0):.1f}%",
                "disk_usage": f"{analysis.get('metrics', {}).get('disk_percent', 0):.1f}%",
                "resolution_attempts": len(resolution_results),
                "successful_resolutions": len([r for r in resolution_results if r.get('success')])
            }
        )

async def test_integration_hub():
    """Test the integration hub"""
    print("🚀 Testing Enhanced Integration Hub")
    print("=" * 50)
    
    hub = EnhancedIntegrationHub()
    
    print(f"📡 Enabled channels: {[c.value for c in hub.enabled_channels]}")
    
    # Test notification
    test_message = NotificationMessage(
        title="Integration Hub Test",
        content="🧪 This is a test notification from the Enhanced Integration Hub. All systems are being tested for proper notification delivery.",
        priority=NotificationPriority.MEDIUM,
        channels=hub.enabled_channels[:3],  # Test first 3 channels
        data={
            "test_type": "integration_test",
            "timestamp": datetime.now().isoformat(),
            "status": "testing"
        }
    )
    
    print(f"\n📤 Sending test notification to {len(test_message.channels)} channels...")
    
    results = await hub.send_notification(test_message)
    
    print(f"\n📊 Results:")
    for channel, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"   {channel}: {status}")
    
    print(f"\n📈 Delivery Statistics:")
    stats = hub.get_delivery_stats()
    print(f"   Total sent: {stats['total_sent']}")
    print(f"   Total failed: {stats['total_failed']}")
    print(f"   Success rate: {stats['success_rate']:.1f}%")
    
    return hub

if __name__ == "__main__":
    asyncio.run(test_integration_hub())