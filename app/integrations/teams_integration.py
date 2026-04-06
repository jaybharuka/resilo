"""
Microsoft Teams Integration for AIOps Bot
Provides Teams notifications, alerts, and interactive messaging capabilities
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('teams_integration')

class MessageType(Enum):
    """Types of Teams messages"""
    ALERT = "alert"
    INFO = "info" 
    WARNING = "warning"
    SUCCESS = "success"
    CRITICAL = "critical"

class TeamsCardType(Enum):
    """Types of adaptive cards"""
    SIMPLE = "simple"
    DETAILED = "detailed"
    INTERACTIVE = "interactive"
    DASHBOARD = "dashboard"

@dataclass
class TeamsAlert:
    """Teams alert message structure"""
    title: str
    message: str
    alert_type: MessageType = MessageType.INFO
    severity: str = "medium"
    timestamp: datetime = field(default_factory=datetime.now)
    system_data: Dict[str, Any] = field(default_factory=dict)
    actions: List[Dict[str, str]] = field(default_factory=list)

@dataclass
class TeamsCredentials:
    """Teams API credentials"""
    tenant_id: str
    client_id: str
    client_secret: str
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None

class MicrosoftTeamsIntegrator:
    """
    Microsoft Teams integration for AIOps Bot
    Supports webhooks, bot messaging, and adaptive cards
    """
    
    def __init__(self, credentials: TeamsCredentials):
        self.credentials = credentials
        self.access_token = None
        self.token_expires_at = None
        self.session = None
        
        # Teams API endpoints
        self.auth_url = f"https://login.microsoftonline.com/{credentials.tenant_id}/oauth2/v2.0/token"
        self.graph_api_base = "https://graph.microsoft.com/v1.0"
        
        logger.info("Microsoft Teams integrator initialized")
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        await self.authenticate()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API"""
        try:
            if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
                return True
            
            auth_data = {
                'grant_type': 'client_credentials',
                'client_id': self.credentials.client_id,
                'client_secret': self.credentials.client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            async with self.session.post(self.auth_url, data=auth_data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data['access_token']
                    expires_in = token_data.get('expires_in', 3600)
                    self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
                    
                    logger.info("Successfully authenticated with Microsoft Graph API")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Authentication failed: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    async def send_webhook_message(self, webhook_url: str, alert: TeamsAlert) -> bool:
        """Send message via Teams webhook (incoming webhook connector)"""
        try:
            card = self.create_adaptive_card(alert, TeamsCardType.DETAILED)
            
            payload = {
                "type": "message",
                "attachments": [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card
                }]
            }
            
            async with self.session.post(webhook_url, json=payload) as response:
                if response.status == 200:
                    logger.info(f"Webhook message sent successfully: {alert.title}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Webhook failed: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False
    
    async def send_channel_message(self, team_id: str, channel_id: str, alert: TeamsAlert) -> bool:
        """Send message to specific Teams channel via Graph API"""
        try:
            await self.authenticate()
            
            card = self.create_adaptive_card(alert, TeamsCardType.INTERACTIVE)
            
            message_payload = {
                "body": {
                    "contentType": "html", 
                    "content": f"<h3>{alert.title}</h3><p>{alert.message}</p>"
                },
                "attachments": [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": json.dumps(card)
                }]
            }
            
            url = f"{self.graph_api_base}/teams/{team_id}/channels/{channel_id}/messages"
            
            async with self.session.post(url, json=message_payload, headers=self.get_auth_headers()) as response:
                if response.status == 201:
                    logger.info(f"Channel message sent successfully: {alert.title}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Channel message failed: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Channel message error: {e}")
            return False
    
    async def send_direct_message(self, user_id: str, alert: TeamsAlert) -> bool:
        """Send direct message to user"""
        try:
            await self.authenticate()
            
            # Create chat first
            chat_payload = {
                "chatType": "oneOnOne",
                "members": [
                    {
                        "@odata.type": "#microsoft.graph.aadUserConversationMember",
                        "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')"
                    }
                ]
            }
            
            # Create or get existing chat
            url = f"{self.graph_api_base}/chats"
            chat_id = None
            
            async with self.session.post(url, json=chat_payload, headers=self.get_auth_headers()) as response:
                if response.status == 201:
                    chat_data = await response.json()
                    chat_id = chat_data['id']
                elif response.status == 409:  # Chat already exists
                    # Get existing chats and find the one with this user
                    chats_url = f"{self.graph_api_base}/me/chats"
                    async with self.session.get(chats_url, headers=self.get_auth_headers()) as chats_response:
                        if chats_response.status == 200:
                            chats_data = await chats_response.json()
                            for chat in chats_data.get('value', []):
                                if chat.get('chatType') == 'oneOnOne':
                                    chat_id = chat['id']
                                    break
            
            if not chat_id:
                logger.error("Could not create or find chat")
                return False
            
            # Send message to chat
            card = self.create_adaptive_card(alert, TeamsCardType.SIMPLE)
            
            message_payload = {
                "body": {
                    "contentType": "html",
                    "content": f"<h3>{alert.title}</h3><p>{alert.message}</p>"
                },
                "attachments": [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": json.dumps(card)
                }]
            }
            
            message_url = f"{self.graph_api_base}/chats/{chat_id}/messages"
            
            async with self.session.post(message_url, json=message_payload, headers=self.get_auth_headers()) as response:
                if response.status == 201:
                    logger.info(f"Direct message sent successfully: {alert.title}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Direct message failed: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Direct message error: {e}")
            return False
    
    def create_adaptive_card(self, alert: TeamsAlert, card_type: TeamsCardType = TeamsCardType.SIMPLE) -> Dict[str, Any]:
        """Create adaptive card for Teams message"""
        
        # Color scheme based on alert type
        color_scheme = {
            MessageType.CRITICAL: "attention",
            MessageType.ALERT: "warning", 
            MessageType.WARNING: "warning",
            MessageType.INFO: "accent",
            MessageType.SUCCESS: "good"
        }
        
        card_color = color_scheme.get(alert.alert_type, "default")
        
        if card_type == TeamsCardType.SIMPLE:
            return self._create_simple_card(alert, card_color)
        elif card_type == TeamsCardType.DETAILED:
            return self._create_detailed_card(alert, card_color)
        elif card_type == TeamsCardType.INTERACTIVE:
            return self._create_interactive_card(alert, card_color)
        elif card_type == TeamsCardType.DASHBOARD:
            return self._create_dashboard_card(alert, card_color)
        else:
            return self._create_simple_card(alert, card_color)
    
    def _create_simple_card(self, alert: TeamsAlert, color: str) -> Dict[str, Any]:
        """Create simple adaptive card"""
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": [
                {
                    "type": "Container",
                    "style": color,
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"🤖 AIOps Alert: {alert.title}",
                            "weight": "bolder",
                            "size": "medium"
                        },
                        {
                            "type": "TextBlock", 
                            "text": alert.message,
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"⏰ {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                            "size": "small",
                            "color": "dark"
                        }
                    ]
                }
            ]
        }
    
    def _create_detailed_card(self, alert: TeamsAlert, color: str) -> Dict[str, Any]:
        """Create detailed adaptive card with system info"""
        system_facts = []
        if alert.system_data:
            for key, value in alert.system_data.items():
                system_facts.append({
                    "title": key.replace('_', ' ').title(),
                    "value": str(value)
                })
        
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": [
                {
                    "type": "Container",
                    "style": color,
                    "items": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "url": "https://img.icons8.com/color/48/000000/bot.png",
                                            "size": "small"
                                        }
                                    ]
                                },
                                {
                                    "type": "Column", 
                                    "width": "stretch",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": f"AIOps Alert: {alert.title}",
                                            "weight": "bolder",
                                            "size": "large"
                                        },
                                        {
                                            "type": "TextBlock",
                                            "text": f"Severity: {alert.severity.upper()}",
                                            "size": "small",
                                            "weight": "bolder"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "TextBlock",
                    "text": alert.message,
                    "wrap": True,
                    "spacing": "medium"
                }
            ]
        }
        
        # Add system information if available
        if system_facts:
            card["body"].append({
                "type": "FactSet",
                "facts": system_facts[:6],  # Limit to 6 facts
                "spacing": "medium"
            })
        
        # Add timestamp
        card["body"].append({
            "type": "TextBlock",
            "text": f"⏰ {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "size": "small",
            "color": "dark",
            "spacing": "medium"
        })
        
        return card
    
    def _create_interactive_card(self, alert: TeamsAlert, color: str) -> Dict[str, Any]:
        """Create interactive adaptive card with action buttons"""
        card = self._create_detailed_card(alert, color)
        
        # Add action buttons
        actions = [
            {
                "type": "Action.OpenUrl",
                "title": "🔍 View Dashboard",
                "url": "http://localhost:5000"  # Your AIOps dashboard URL
            },
            {
                "type": "Action.OpenUrl", 
                "title": "📊 System Metrics",
                "url": "http://localhost:5000/metrics"
            }
        ]
        
        # Add custom actions from alert
        for action in alert.actions:
            actions.append({
                "type": "Action.OpenUrl",
                "title": action.get("title", "Action"),
                "url": action.get("url", "#")
            })
        
        card["actions"] = actions
        return card
    
    def _create_dashboard_card(self, alert: TeamsAlert, color: str) -> Dict[str, Any]:
        """Create dashboard-style card with metrics"""
        metrics = []
        if alert.system_data:
            cpu = alert.system_data.get('cpu_usage', 0)
            memory = alert.system_data.get('memory_usage', 0) 
            disk = alert.system_data.get('disk_usage', 0)
            
            metrics = [
                {"name": "CPU", "value": f"{cpu}%", "color": "good" if cpu < 70 else "warning" if cpu < 90 else "attention"},
                {"name": "Memory", "value": f"{memory}%", "color": "good" if memory < 80 else "warning" if memory < 95 else "attention"},
                {"name": "Disk", "value": f"{disk}%", "color": "good" if disk < 85 else "warning" if disk < 95 else "attention"}
            ]
        
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "🖥️ System Dashboard",
                    "weight": "bolder",
                    "size": "large"
                },
                {
                    "type": "TextBlock",
                    "text": alert.message,
                    "wrap": True,
                    "spacing": "medium"
                }
            ]
        }
        
        # Add metrics if available
        if metrics:
            metric_columns = []
            for metric in metrics:
                metric_columns.append({
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": metric["name"],
                            "weight": "bolder",
                            "horizontalAlignment": "center"
                        },
                        {
                            "type": "TextBlock",
                            "text": metric["value"],
                            "size": "large",
                            "color": metric["color"],
                            "horizontalAlignment": "center"
                        }
                    ]
                })
            
            card["body"].append({
                "type": "ColumnSet",
                "columns": metric_columns,
                "spacing": "medium"
            })
        
        return card
    
    async def get_teams_info(self) -> Dict[str, Any]:
        """Get available teams and channels"""
        try:
            await self.authenticate()
            
            # Get teams
            teams_url = f"{self.graph_api_base}/me/joinedTeams"
            teams_data = {}
            
            async with self.session.get(teams_url, headers=self.get_auth_headers()) as response:
                if response.status == 200:
                    teams_result = await response.json()
                    
                    for team in teams_result.get('value', []):
                        team_id = team['id']
                        team_name = team['displayName']
                        
                        # Get channels for this team
                        channels_url = f"{self.graph_api_base}/teams/{team_id}/channels"
                        
                        async with self.session.get(channels_url, headers=self.get_auth_headers()) as channels_response:
                            if channels_response.status == 200:
                                channels_result = await channels_response.json()
                                channels = [
                                    {
                                        'id': channel['id'],
                                        'name': channel['displayName']
                                    }
                                    for channel in channels_result.get('value', [])
                                ]
                                teams_data[team_name] = {
                                    'id': team_id,
                                    'channels': channels
                                }
            
            return teams_data
            
        except Exception as e:
            logger.error(f"Error getting Teams info: {e}")
            return {}

# Convenience functions for easy integration
async def send_aiops_alert(credentials: TeamsCredentials, webhook_url: str, 
                          title: str, message: str, alert_type: MessageType = MessageType.INFO,
                          system_data: Dict[str, Any] = None) -> bool:
    """Convenient function to send AIOps alert to Teams"""
    alert = TeamsAlert(
        title=title,
        message=message,
        alert_type=alert_type,
        system_data=system_data or {}
    )
    
    async with MicrosoftTeamsIntegrator(credentials) as teams:
        return await teams.send_webhook_message(webhook_url, alert)

async def send_system_status(credentials: TeamsCredentials, webhook_url: str,
                           cpu_usage: float, memory_usage: float, disk_usage: float) -> bool:
    """Send system status update to Teams"""
    
    # Determine alert type based on system metrics
    alert_type = MessageType.SUCCESS
    if cpu_usage > 90 or memory_usage > 95 or disk_usage > 95:
        alert_type = MessageType.CRITICAL
    elif cpu_usage > 80 or memory_usage > 85 or disk_usage > 90:
        alert_type = MessageType.WARNING
    
    system_data = {
        'cpu_usage': cpu_usage,
        'memory_usage': memory_usage,
        'disk_usage': disk_usage,
        'timestamp': datetime.now().isoformat()
    }
    
    message = f"System Status Update: CPU {cpu_usage}%, Memory {memory_usage}%, Disk {disk_usage}%"
    
    alert = TeamsAlert(
        title="System Health Check",
        message=message,
        alert_type=alert_type,
        system_data=system_data
    )
    
    async with MicrosoftTeamsIntegrator(credentials) as teams:
        return await teams.send_webhook_message(webhook_url, alert)

# Demo function
async def demo_teams_integration():
    """Demonstrate Teams integration capabilities"""
    print("🤖 Microsoft Teams Integration Demo")
    print("=" * 50)
    
    # Note: These are demo credentials - replace with real ones
    demo_credentials = TeamsCredentials(
        tenant_id="your-tenant-id",
        client_id="your-client-id", 
        client_secret="your-client-secret",
        webhook_url="your-webhook-url"
    )
    
    # Demo system data
    demo_system_data = {
        'cpu_usage': 75.5,
        'memory_usage': 68.2,
        'disk_usage': 45.8,
        'active_processes': 234,
        'uptime_hours': 72
    }
    
    # Demo alerts
    demo_alerts = [
        TeamsAlert(
            title="High CPU Usage Detected",
            message="CPU usage has exceeded 75% for the last 10 minutes. Consider scaling resources.",
            alert_type=MessageType.WARNING,
            severity="high",
            system_data=demo_system_data
        ),
        TeamsAlert(
            title="System Backup Completed",
            message="Daily system backup completed successfully. All data secured.",
            alert_type=MessageType.SUCCESS,
            severity="low",
            system_data={'backup_size': '2.4 GB', 'duration': '15 minutes'}
        ),
        TeamsAlert(
            title="Critical: Service Down",
            message="Database service is not responding. Immediate attention required!",
            alert_type=MessageType.CRITICAL,
            severity="critical",
            system_data={'service': 'postgresql', 'last_response': '5 minutes ago'}
        )
    ]
    
    print("📝 Demo Alert Cards:")
    for i, alert in enumerate(demo_alerts, 1):
        print(f"\n{i}. {alert.title}")
        print(f"   Type: {alert.alert_type.value}")
        print(f"   Severity: {alert.severity}")
        print(f"   Message: {alert.message}")
    
    print("\n🔧 Teams Integration Features:")
    print("✅ Webhook messaging (incoming webhooks)")
    print("✅ Channel messaging (Graph API)")
    print("✅ Direct messaging")
    print("✅ Adaptive cards with system metrics")
    print("✅ Interactive buttons and actions")
    print("✅ Dashboard-style cards")
    print("✅ Color-coded severity levels")
    print("✅ Automatic authentication handling")
    
    print("\n📋 Setup Requirements:")
    print("1. Register app in Azure AD")
    print("2. Configure Teams permissions")
    print("3. Set up incoming webhook in Teams channel")
    print("4. Add credentials to your configuration")
    
    print("\n🚀 Ready for integration with your AIOps bot!")

if __name__ == "__main__":
    asyncio.run(demo_teams_integration())