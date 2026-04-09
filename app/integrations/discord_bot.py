#!/usr/bin/env python3
"""
AIOps Discord Bot Integration
Comprehensive Discord bot for real-time alerts, monitoring, and ChatOps

This Discord bot provides:
- Real-time system alerts and notifications
- Interactive monitoring commands
- System status reporting with rich embeds
- ChatOps functionality for DevOps tasks
- Incident management and escalation
- Performance metrics visualization
"""

import asyncio
import json
import logging
import os
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp
import psutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('discord_bot')

# Mock discord.py for demonstration
class MockDiscordClient:
    """Mock Discord client for demonstration purposes"""
    def __init__(self):
        self.guilds = []
        self.channels = {}
        self.is_ready = False
    
    async def login(self, token):
        logger.info("Mock Discord client logged in")
        self.is_ready = True
    
    async def close(self):
        logger.info("Mock Discord client closed")
        self.is_ready = False
    
    def run(self, token):
        logger.info("Mock Discord client started")
    
    async def send_message(self, channel_id: int, content: str = None, embed: dict = None):
        logger.info(f"Sending message to channel {channel_id}: {content or 'Embed message'}")
        if embed:
            logger.info(f"Embed: {embed}")

class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class NotificationType(Enum):
    """Notification types"""
    SYSTEM_ALERT = "system_alert"
    PERFORMANCE = "performance"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    MAINTENANCE = "maintenance"

@dataclass
class DiscordAlert:
    """Discord alert data structure"""
    title: str
    description: str
    severity: AlertSeverity
    notification_type: NotificationType
    timestamp: datetime
    source: str
    details: Dict[str, Any]
    channel_id: Optional[int] = None
    thread_id: Optional[int] = None
    
    def to_embed(self) -> Dict[str, Any]:
        """Convert alert to Discord embed format"""
        # Color coding by severity
        colors = {
            AlertSeverity.CRITICAL: 0xFF0000,  # Red
            AlertSeverity.HIGH: 0xFF8C00,      # Orange
            AlertSeverity.MEDIUM: 0xFFFF00,    # Yellow
            AlertSeverity.LOW: 0x00FF00,       # Green
            AlertSeverity.INFO: 0x0000FF       # Blue
        }
        
        embed = {
            "title": self.title,
            "description": self.description,
            "color": colors.get(self.severity, 0x808080),
            "timestamp": self.timestamp.isoformat(),
            "footer": {
                "text": f"Source: {self.source} | Type: {self.notification_type.value}"
            },
            "fields": []
        }
        
        # Add severity field
        embed["fields"].append({
            "name": "Severity",
            "value": f"🔥 {self.severity.value.upper()}",
            "inline": True
        })
        
        # Add details as fields
        for key, value in self.details.items():
            if len(embed["fields"]) < 25:  # Discord embed limit
                embed["fields"].append({
                    "name": key.replace('_', ' ').title(),
                    "value": str(value)[:1024],  # Discord field value limit
                    "inline": True
                })
        
        return embed

@dataclass
class DiscordConfig:
    """Discord bot configuration"""
    token: str
    guild_id: int
    channels: Dict[str, int]  # Channel mapping (alerts, monitoring, etc.)
    command_prefix: str = "!"
    enable_chatops: bool = True
    alert_retention_days: int = 7

class AIOpsDiscordBot:
    """Main Discord bot for AIOps platform"""
    
    def __init__(self, config: DiscordConfig):
        self.config = config
        self.client = MockDiscordClient()  # In real implementation, use discord.Client()
        self.alert_history: List[DiscordAlert] = []
        self.system_monitor = SystemMonitor()
        self.chatops_handler = ChatOpsHandler()
        
        # Channel configuration
        self.channels = {
            "alerts": config.channels.get("alerts", 123456789),
            "monitoring": config.channels.get("monitoring", 123456790),
            "deployments": config.channels.get("deployments", 123456791),
            "general": config.channels.get("general", 123456792)
        }
        
        logger.info("AIOps Discord Bot initialized")
    
    async def start(self):
        """Start the Discord bot"""
        try:
            await self.client.login(self.config.token)
            logger.info("Discord bot started successfully")
            
            # Start background tasks
            asyncio.create_task(self.monitor_system())
            asyncio.create_task(self.cleanup_old_alerts())
            
        except Exception as e:
            logger.error(f"Failed to start Discord bot: {e}")
            raise
    
    async def stop(self):
        """Stop the Discord bot"""
        await self.client.close()
        logger.info("Discord bot stopped")
    
    async def send_alert(self, alert: DiscordAlert):
        """Send alert to Discord channel"""
        try:
            # Determine target channel based on alert type
            channel_id = self.get_channel_for_alert(alert)
            
            # Create embed
            embed = alert.to_embed()
            
            # Send message
            await self.client.send_message(channel_id, embed=embed)
            
            # Store in history
            self.alert_history.append(alert)
            
            logger.info(f"Sent {alert.severity.value} alert: {alert.title}")
            
            # Auto-escalate critical alerts
            if alert.severity == AlertSeverity.CRITICAL:
                await self.escalate_alert(alert)
                
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def get_channel_for_alert(self, alert: DiscordAlert) -> int:
        """Determine appropriate channel for alert"""
        if alert.channel_id:
            return alert.channel_id
        
        if alert.notification_type == NotificationType.DEPLOYMENT:
            return self.channels["deployments"]
        elif alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            return self.channels["alerts"]
        else:
            return self.channels["monitoring"]
    
    async def escalate_alert(self, alert: DiscordAlert):
        """Escalate critical alerts"""
        escalation_embed = {
            "title": "🚨 CRITICAL ALERT ESCALATION",
            "description": f"Critical alert requires immediate attention: {alert.title}",
            "color": 0xFF0000,
            "fields": [
                {
                    "name": "Original Alert",
                    "value": alert.description[:1024],
                    "inline": False
                },
                {
                    "name": "Escalation Time",
                    "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "inline": True
                }
            ]
        }
        
        # Send to alerts channel with @everyone mention
        await self.client.send_message(
            self.channels["alerts"], 
            content="@everyone Critical Alert Escalation",
            embed=escalation_embed
        )
    
    async def monitor_system(self):
        """Background system monitoring"""
        while True:
            try:
                # Get system metrics
                metrics = await self.system_monitor.get_current_metrics()
                
                # Check for issues
                alerts = self.system_monitor.analyze_metrics(metrics)
                
                # Send alerts if any
                for alert in alerts:
                    await self.send_alert(alert)
                
                # Send periodic status update
                if datetime.now().minute % 15 == 0:  # Every 15 minutes
                    await self.send_status_update(metrics)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"System monitoring error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def send_status_update(self, metrics: Dict[str, Any]):
        """Send periodic status update"""
        status_embed = {
            "title": "📊 System Status Update",
            "description": "Current system performance metrics",
            "color": 0x00FF00,
            "timestamp": datetime.now().isoformat(),
            "fields": [
                {
                    "name": "CPU Usage",
                    "value": f"{metrics['cpu_percent']:.1f}%",
                    "inline": True
                },
                {
                    "name": "Memory Usage", 
                    "value": f"{metrics['memory_percent']:.1f}%",
                    "inline": True
                },
                {
                    "name": "Disk Usage",
                    "value": f"{metrics['disk_percent']:.1f}%",
                    "inline": True
                },
                {
                    "name": "Active Connections",
                    "value": str(metrics.get('connections', 'N/A')),
                    "inline": True
                },
                {
                    "name": "Uptime",
                    "value": metrics.get('uptime', 'N/A'),
                    "inline": True
                },
                {
                    "name": "Load Average",
                    "value": str(metrics.get('load_avg', 'N/A')),
                    "inline": True
                }
            ]
        }
        
        await self.client.send_message(self.channels["monitoring"], embed=status_embed)
    
    async def cleanup_old_alerts(self):
        """Clean up old alerts from history"""
        while True:
            try:
                cutoff_date = datetime.now() - timedelta(days=self.config.alert_retention_days)
                
                initial_count = len(self.alert_history)
                self.alert_history = [
                    alert for alert in self.alert_history 
                    if alert.timestamp > cutoff_date
                ]
                
                cleaned_count = initial_count - len(self.alert_history)
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} old alerts")
                
                await asyncio.sleep(3600)  # Check every hour
                
            except Exception as e:
                logger.error(f"Alert cleanup error: {e}")
                await asyncio.sleep(3600)
    
    async def handle_command(self, message_content: str, channel_id: int, user_id: int) -> str:
        """Handle bot commands"""
        if not message_content.startswith(self.config.command_prefix):
            return None
        
        command = message_content[len(self.config.command_prefix):].strip().split()
        
        if not command:
            return None
        
        cmd = command[0].lower()
        args = command[1:] if len(command) > 1 else []
        
        # Route to ChatOps handler
        if self.config.enable_chatops:
            return await self.chatops_handler.handle_command(cmd, args, channel_id, user_id)
        
        return "ChatOps is disabled"

class SystemMonitor:
    """System monitoring for Discord alerts"""
    
    def __init__(self):
        self.thresholds = {
            "cpu_critical": 90.0,
            "cpu_high": 80.0,
            "memory_critical": 95.0,
            "memory_high": 85.0,
            "disk_critical": 95.0,
            "disk_high": 85.0
        }
    
    async def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Network metrics
            connections = len(psutil.net_connections())
            
            # System uptime
            boot_time = psutil.boot_time()
            uptime = datetime.now() - datetime.fromtimestamp(boot_time)
            uptime_str = str(uptime).split('.')[0]  # Remove microseconds
            
            # Load average (Unix-like systems)
            try:
                load_avg = os.getloadavg()
            except AttributeError:
                load_avg = "N/A (Windows)"
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent,
                "connections": connections,
                "uptime": uptime_str,
                "load_avg": load_avg,
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {}
    
    def analyze_metrics(self, metrics: Dict[str, Any]) -> List[DiscordAlert]:
        """Analyze metrics and generate alerts"""
        alerts = []
        
        if not metrics:
            return alerts
        
        # CPU alerts
        cpu_percent = metrics.get("cpu_percent", 0)
        if cpu_percent >= self.thresholds["cpu_critical"]:
            alerts.append(DiscordAlert(
                title="🔥 Critical CPU Usage",
                description=f"CPU usage is critically high at {cpu_percent:.1f}%",
                severity=AlertSeverity.CRITICAL,
                notification_type=NotificationType.SYSTEM_ALERT,
                timestamp=datetime.now(),
                source="SystemMonitor",
                details={"cpu_usage": f"{cpu_percent:.1f}%", "threshold": "90%"}
            ))
        elif cpu_percent >= self.thresholds["cpu_high"]:
            alerts.append(DiscordAlert(
                title="⚠️ High CPU Usage",
                description=f"CPU usage is high at {cpu_percent:.1f}%",
                severity=AlertSeverity.HIGH,
                notification_type=NotificationType.PERFORMANCE,
                timestamp=datetime.now(),
                source="SystemMonitor",
                details={"cpu_usage": f"{cpu_percent:.1f}%", "threshold": "80%"}
            ))
        
        # Memory alerts
        memory_percent = metrics.get("memory_percent", 0)
        if memory_percent >= self.thresholds["memory_critical"]:
            alerts.append(DiscordAlert(
                title="🔥 Critical Memory Usage",
                description=f"Memory usage is critically high at {memory_percent:.1f}%",
                severity=AlertSeverity.CRITICAL,
                notification_type=NotificationType.SYSTEM_ALERT,
                timestamp=datetime.now(),
                source="SystemMonitor",
                details={"memory_usage": f"{memory_percent:.1f}%", "threshold": "95%"}
            ))
        elif memory_percent >= self.thresholds["memory_high"]:
            alerts.append(DiscordAlert(
                title="⚠️ High Memory Usage",
                description=f"Memory usage is high at {memory_percent:.1f}%",
                severity=AlertSeverity.HIGH,
                notification_type=NotificationType.PERFORMANCE,
                timestamp=datetime.now(),
                source="SystemMonitor",
                details={"memory_usage": f"{memory_percent:.1f}%", "threshold": "85%"}
            ))
        
        # Disk alerts
        disk_percent = metrics.get("disk_percent", 0)
        if disk_percent >= self.thresholds["disk_critical"]:
            alerts.append(DiscordAlert(
                title="🔥 Critical Disk Usage",
                description=f"Disk usage is critically high at {disk_percent:.1f}%",
                severity=AlertSeverity.CRITICAL,
                notification_type=NotificationType.SYSTEM_ALERT,
                timestamp=datetime.now(),
                source="SystemMonitor",
                details={"disk_usage": f"{disk_percent:.1f}%", "threshold": "95%"}
            ))
        elif disk_percent >= self.thresholds["disk_high"]:
            alerts.append(DiscordAlert(
                title="⚠️ High Disk Usage",
                description=f"Disk usage is high at {disk_percent:.1f}%",
                severity=AlertSeverity.HIGH,
                notification_type=NotificationType.PERFORMANCE,
                timestamp=datetime.now(),
                source="SystemMonitor",
                details={"disk_usage": f"{disk_percent:.1f}%", "threshold": "85%"}
            ))
        
        return alerts

class ChatOpsHandler:
    """Handle ChatOps commands through Discord"""
    
    def __init__(self):
        self.commands = {
            "status": self.cmd_status,
            "metrics": self.cmd_metrics,
            "alerts": self.cmd_alerts,
            "services": self.cmd_services,
            "deploy": self.cmd_deploy,
            "scale": self.cmd_scale,
            "help": self.cmd_help
        }
    
    async def handle_command(self, cmd: str, args: List[str], channel_id: int, user_id: int) -> str:
        """Handle ChatOps command"""
        if cmd not in self.commands:
            return f"Unknown command: {cmd}. Use `!help` for available commands."
        
        try:
            return await self.commands[cmd](args, channel_id, user_id)
        except Exception as e:
            logger.error(f"Command error for {cmd}: {e}")
            return f"Error executing command: {cmd}"
    
    async def cmd_status(self, args: List[str], channel_id: int, user_id: int) -> str:
        """Get system status"""
        monitor = SystemMonitor()
        metrics = await monitor.get_current_metrics()
        
        if not metrics:
            return "❌ Unable to retrieve system metrics"
        
        status = f"""📊 **System Status**
🖥️ CPU: {metrics['cpu_percent']:.1f}%
💾 Memory: {metrics['memory_percent']:.1f}%
💿 Disk: {metrics['disk_percent']:.1f}%
🌐 Connections: {metrics['connections']}
⏱️ Uptime: {metrics['uptime']}
📈 Load Average: {metrics['load_avg']}"""
        
        return status
    
    async def cmd_metrics(self, args: List[str], channel_id: int, user_id: int) -> str:
        """Get detailed metrics"""
        return "📊 Detailed metrics would be displayed here (requires monitoring backend)"
    
    async def cmd_alerts(self, args: List[str], channel_id: int, user_id: int) -> str:
        """Get recent alerts"""
        return "🚨 Recent alerts would be displayed here (requires alert history)"
    
    async def cmd_services(self, args: List[str], channel_id: int, user_id: int) -> str:
        """Get service status"""
        return "🔧 Service status would be displayed here (requires service registry)"
    
    async def cmd_deploy(self, args: List[str], channel_id: int, user_id: int) -> str:
        """Trigger deployment"""
        if not args:
            return "❌ Usage: !deploy <service> [environment]"
        
        service = args[0]
        environment = args[1] if len(args) > 1 else "staging"
        
        return f"🚀 Deployment of {service} to {environment} would be triggered here"
    
    async def cmd_scale(self, args: List[str], channel_id: int, user_id: int) -> str:
        """Scale service"""
        if len(args) < 2:
            return "❌ Usage: !scale <service> <replicas>"
        
        service = args[0]
        replicas = args[1]
        
        return f"📈 Scaling {service} to {replicas} replicas would be executed here"
    
    async def cmd_help(self, args: List[str], channel_id: int, user_id: int) -> str:
        """Show help"""
        help_text = """🤖 **AIOps Bot Commands**

**Monitoring:**
• `!status` - Show system status
• `!metrics` - Show detailed metrics
• `!alerts` - Show recent alerts
• `!services` - Show service status

**Operations:**
• `!deploy <service> [env]` - Deploy service
• `!scale <service> <replicas>` - Scale service

**General:**
• `!help` - Show this help"""
        
        return help_text

async def demonstrate_discord_bot():
    """Demonstrate Discord bot functionality"""
    print("AIOps Discord Bot Integration Demo")
    print("=" * 50)
    
    # Configuration
    config = DiscordConfig(
        token=os.environ.get("DISCORD_BOT_TOKEN", ""),
        guild_id=123456789,
        channels={
            "alerts": 123456789,
            "monitoring": 123456790,
            "deployments": 123456791,
            "general": 123456792
        }
    )
    
    # Initialize bot
    bot = AIOpsDiscordBot(config)
    
    print("🤖 Initializing Discord bot...")
    await bot.start()
    
    # Simulate some alerts
    test_alerts = [
        DiscordAlert(
            title="High CPU Usage Detected",
            description="CPU usage has exceeded 85% for the past 5 minutes",
            severity=AlertSeverity.HIGH,
            notification_type=NotificationType.PERFORMANCE,
            timestamp=datetime.now(),
            source="PerformanceMonitor",
            details={
                "cpu_usage": "87.3%",
                "duration": "5 minutes",
                "server": "web-server-01"
            }
        ),
        DiscordAlert(
            title="Deployment Successful", 
            description="Application v2.1.0 deployed successfully to production",
            severity=AlertSeverity.INFO,
            notification_type=NotificationType.DEPLOYMENT,
            timestamp=datetime.now(),
            source="DeploymentPipeline",
            details={
                "version": "v2.1.0",
                "environment": "production",
                "duration": "3m 42s"
            }
        ),
        DiscordAlert(
            title="Critical Memory Usage",
            description="Memory usage has reached 96% - immediate action required",
            severity=AlertSeverity.CRITICAL,
            notification_type=NotificationType.SYSTEM_ALERT,
            timestamp=datetime.now(),
            source="SystemMonitor",
            details={
                "memory_usage": "96.2%",
                "available_memory": "1.2GB",
                "server": "api-server-02"
            }
        )
    ]
    
    print("\n📨 Sending test alerts...")
    for alert in test_alerts:
        await bot.send_alert(alert)
        await asyncio.sleep(1)
    
    # Test ChatOps commands
    print("\n💬 Testing ChatOps commands...")
    chatops = ChatOpsHandler()
    
    commands = [
        ("status", []),
        ("help", []),
        ("deploy", ["web-app", "staging"]),
        ("scale", ["api-service", "5"])
    ]
    
    for cmd, args in commands:
        response = await chatops.handle_command(cmd, args, 123456789, 987654321)
        print(f"Command: !{cmd} {' '.join(args)}")
        print(f"Response: {response}\n")
    
    # Test system monitoring
    print("📊 Testing system monitoring...")
    monitor = SystemMonitor()
    metrics = await monitor.get_current_metrics()
    
    print(f"Current Metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    
    # Analyze for alerts
    generated_alerts = monitor.analyze_metrics(metrics)
    if generated_alerts:
        print(f"\n🚨 Generated {len(generated_alerts)} alerts:")
        for alert in generated_alerts:
            print(f"  - {alert.severity.value}: {alert.title}")
    else:
        print("\n✅ No alerts generated - system is healthy")
    
    await bot.stop()
    
    print(f"\n📋 Discord Bot Demo Summary:")
    print(f"  🤖 Bot Status: Operational")
    print(f"  📨 Alerts Sent: {len(test_alerts)}")
    print(f"  💬 ChatOps Commands: {len(commands)} tested")
    print(f"  📊 System Monitoring: Active")
    print(f"  🔄 Background Tasks: Monitoring, Cleanup")
    print(f"  🎯 Features: Rich embeds, escalation, multi-channel")

if __name__ == "__main__":
    asyncio.run(demonstrate_discord_bot())