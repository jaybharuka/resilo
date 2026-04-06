#!/usr/bin/env python3
"""
AIOps ChatOps Command Interface
Interactive command system for Discord and Slack integrations

Features:
- Natural language command parsing
- System status queries and operations
- Interactive command execution
- Permission-based access control
- Command history and auditing
- Real-time response formatting
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import psutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('chatops')

class CommandType(Enum):
    """Command types for ChatOps"""
    STATUS = "status"
    METRICS = "metrics"
    CONTROL = "control"
    QUERY = "query"
    ADMIN = "admin"
    HELP = "help"

class Permission(Enum):
    """Permission levels for commands"""
    PUBLIC = "public"          # Anyone can use
    OPERATOR = "operator"      # Operations team
    ADMIN = "admin"           # Administrators only
    SUPERUSER = "superuser"   # System administrators

@dataclass
class User:
    """Chat user representation"""
    id: str
    username: str
    platform: str  # discord, slack
    permissions: List[Permission] = field(default_factory=lambda: [Permission.PUBLIC])
    last_activity: datetime = field(default_factory=datetime.now)

@dataclass
class Command:
    """Command definition"""
    name: str
    aliases: List[str]
    description: str
    usage: str
    command_type: CommandType
    permission_required: Permission
    handler: str  # Method name to handle the command
    examples: List[str] = field(default_factory=list)

@dataclass
class CommandExecution:
    """Command execution context"""
    command: str
    user: User
    platform: str
    channel: str
    timestamp: datetime
    arguments: List[str] = field(default_factory=list)
    raw_message: str = ""

@dataclass
class CommandResponse:
    """Command response"""
    success: bool
    message: str
    data: Optional[Dict] = None
    embed: Optional[Dict] = None
    ephemeral: bool = False  # Only visible to command user

class SystemInterface:
    """Interface to system operations"""
    
    @staticmethod
    def get_system_status() -> Dict:
        """Get comprehensive system status"""
        try:
            # CPU information
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Memory information
            memory = psutil.virtual_memory()
            
            # Disk information
            disk = psutil.disk_usage('/')
            
            # Network information
            network = psutil.net_io_counters()
            
            # Process count
            process_count = len(psutil.pids())
            
            # Boot time
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            
            return {
                'cpu': {
                    'usage_percent': round(cpu_percent, 1),
                    'cores': cpu_count,
                    'status': 'normal' if cpu_percent < 80 else 'high'
                },
                'memory': {
                    'total_gb': round(memory.total / (1024**3), 1),
                    'used_gb': round(memory.used / (1024**3), 1),
                    'usage_percent': round(memory.percent, 1),
                    'available_gb': round(memory.available / (1024**3), 1),
                    'status': 'normal' if memory.percent < 80 else 'high'
                },
                'disk': {
                    'total_gb': round(disk.total / (1024**3), 1),
                    'used_gb': round(disk.used / (1024**3), 1),
                    'usage_percent': round((disk.used / disk.total) * 100, 1),
                    'free_gb': round(disk.free / (1024**3), 1),
                    'status': 'normal' if (disk.used / disk.total) < 0.8 else 'high'
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                },
                'system': {
                    'processes': process_count,
                    'boot_time': boot_time.isoformat(),
                    'uptime_hours': round(uptime.total_seconds() / 3600, 1),
                    'platform': psutil.WINDOWS if os.name == 'nt' else psutil.LINUX
                }
            }
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def get_service_status(service_name: Optional[str] = None) -> Dict:
        """Get status of AIOps services"""
        # Mock service status - in production this would check actual services
        services = {
            'api-gateway': {'status': 'running', 'port': 8090, 'uptime': '2h 15m'},
            'orchestrator': {'status': 'running', 'port': 8081, 'uptime': '2h 15m'},
            'performance-monitor': {'status': 'running', 'port': 8082, 'uptime': '2h 14m'},
            'analytics-engine': {'status': 'running', 'port': 8083, 'uptime': '2h 13m'},
            'auto-scaler': {'status': 'running', 'port': 8084, 'uptime': '2h 12m'},
            'config-manager': {'status': 'running', 'port': 8085, 'uptime': '2h 15m'}
        }
        
        if service_name:
            return services.get(service_name, {'error': f'Service {service_name} not found'})
        
        return services
    
    @staticmethod
    def get_recent_alerts(limit: int = 10) -> List[Dict]:
        """Get recent alerts"""
        # Mock recent alerts
        alerts = [
            {
                'id': 'ALERT-001',
                'title': 'High CPU Usage',
                'severity': 'medium',
                'time': '2 minutes ago',
                'status': 'active'
            },
            {
                'id': 'ALERT-002', 
                'title': 'Disk Space Warning',
                'severity': 'low',
                'time': '15 minutes ago',
                'status': 'acknowledged'
            },
            {
                'id': 'ALERT-003',
                'title': 'Network Latency Spike',
                'severity': 'medium',
                'time': '1 hour ago',
                'status': 'resolved'
            }
        ]
        
        return alerts[:limit]
    
    @staticmethod
    def execute_system_command(command: str, user: User) -> Dict:
        """Execute system command with permission checking"""
        
        # Permission check for dangerous commands
        dangerous_commands = ['rm', 'del', 'format', 'shutdown', 'reboot']
        if any(cmd in command.lower() for cmd in dangerous_commands):
            if Permission.ADMIN not in user.permissions:
                return {
                    'success': False,
                    'message': 'Insufficient permissions for this command',
                    'error': 'PERMISSION_DENIED'
                }
        
        # Whitelist of allowed commands
        allowed_commands = {
            'ps': 'Get running processes',
            'df': 'Check disk usage',
            'top': 'Show system processes',
            'netstat': 'Show network connections',
            'systemctl status': 'Check service status',
            'docker ps': 'List Docker containers',
            'kubectl get pods': 'List Kubernetes pods'
        }
        
        command_base = command.split()[0] if command.split() else command
        
        if command_base not in [cmd.split()[0] for cmd in allowed_commands.keys()]:
            return {
                'success': False,
                'message': f'Command "{command_base}" not in allowed list',
                'allowed_commands': list(allowed_commands.keys())
            }
        
        try:
            # In demo mode, simulate command execution
            if command.startswith('ps'):
                return {
                    'success': True,
                    'message': 'Process list retrieved',
                    'output': 'PID  COMMAND\n1234 python aiops_orchestrator.py\n5678 python api_gateway.py\n9012 python performance_monitor.py'
                }
            elif command.startswith('df'):
                return {
                    'success': True,
                    'message': 'Disk usage retrieved',
                    'output': 'Filesystem     Size  Used Avail Use%\n/dev/sda1       50G   35G   13G  73%'
                }
            else:
                return {
                    'success': True,
                    'message': f'Command "{command}" executed successfully',
                    'output': f'[Demo] Simulated output for: {command}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Command execution failed: {str(e)}',
                'error': str(e)
            }

class ChatOpsCommandProcessor:
    """Main ChatOps command processor"""
    
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.users = {}
        self.command_history = []
        self.system_interface = SystemInterface()
        
        # Register commands
        self.commands = self.register_commands()
        
        logger.info(f"ChatOps processor initialized with {len(self.commands)} commands")
    
    def register_commands(self) -> Dict[str, Command]:
        """Register all available commands"""
        commands = {}
        
        # Status commands
        commands['status'] = Command(
            name='status',
            aliases=['st', 'health'],
            description='Get system status and health information',
            usage='!status [service]',
            command_type=CommandType.STATUS,
            permission_required=Permission.PUBLIC,
            handler='handle_status',
            examples=['!status', '!status api-gateway', '!health']
        )
        
        commands['metrics'] = Command(
            name='metrics',
            aliases=['perf', 'performance'],
            description='Get system performance metrics',
            usage='!metrics [type]',
            command_type=CommandType.METRICS,
            permission_required=Permission.PUBLIC,
            handler='handle_metrics',
            examples=['!metrics', '!metrics cpu', '!perf memory']
        )
        
        commands['alerts'] = Command(
            name='alerts',
            aliases=['incidents', 'issues'],
            description='Get recent alerts and incidents',
            usage='!alerts [limit]',
            command_type=CommandType.QUERY,
            permission_required=Permission.OPERATOR,
            handler='handle_alerts',
            examples=['!alerts', '!alerts 5', '!incidents']
        )
        
        # Control commands
        commands['restart'] = Command(
            name='restart',
            aliases=['reboot', 'bounce'],
            description='Restart a service or system component',
            usage='!restart <service>',
            command_type=CommandType.CONTROL,
            permission_required=Permission.ADMIN,
            handler='handle_restart',
            examples=['!restart api-gateway', '!bounce orchestrator']
        )
        
        commands['scale'] = Command(
            name='scale',
            aliases=['resize'],
            description='Scale service instances up or down',
            usage='!scale <service> <replicas>',
            command_type=CommandType.CONTROL,
            permission_required=Permission.OPERATOR,
            handler='handle_scale',
            examples=['!scale analytics-engine 3', '!resize api-gateway 5']
        )
        
        # Query commands
        commands['logs'] = Command(
            name='logs',
            aliases=['tail', 'log'],
            description='Get recent logs from a service',
            usage='!logs <service> [lines]',
            command_type=CommandType.QUERY,
            permission_required=Permission.OPERATOR,
            handler='handle_logs',
            examples=['!logs api-gateway', '!tail orchestrator 50']
        )
        
        commands['exec'] = Command(
            name='exec',
            aliases=['run', 'execute'],
            description='Execute system command',
            usage='!exec <command>',
            command_type=CommandType.ADMIN,
            permission_required=Permission.ADMIN,
            handler='handle_exec',
            examples=['!exec ps aux', '!run df -h']
        )
        
        # Help command
        commands['help'] = Command(
            name='help',
            aliases=['?', 'commands'],
            description='Show available commands and usage',
            usage='!help [command]',
            command_type=CommandType.HELP,
            permission_required=Permission.PUBLIC,
            handler='handle_help',
            examples=['!help', '!help status', '!?']
        )
        
        return commands
    
    def get_or_create_user(self, user_id: str, username: str, platform: str) -> User:
        """Get or create user"""
        if user_id not in self.users:
            # Default permissions based on username patterns
            permissions = [Permission.PUBLIC]
            if 'admin' in username.lower() or 'root' in username.lower():
                permissions.extend([Permission.OPERATOR, Permission.ADMIN])
            elif 'ops' in username.lower() or 'operator' in username.lower():
                permissions.append(Permission.OPERATOR)
            
            self.users[user_id] = User(
                id=user_id,
                username=username,
                platform=platform,
                permissions=permissions
            )
        
        # Update last activity
        self.users[user_id].last_activity = datetime.now()
        return self.users[user_id]
    
    def parse_command(self, message: str) -> Tuple[Optional[str], List[str]]:
        """Parse command from message"""
        # Remove command prefix
        if not message.startswith('!'):
            return None, []
        
        parts = message[1:].strip().split()
        if not parts:
            return None, []
        
        command_name = parts[0].lower()
        arguments = parts[1:] if len(parts) > 1 else []
        
        return command_name, arguments
    
    def find_command(self, command_name: str) -> Optional[Command]:
        """Find command by name or alias"""
        # Direct match
        if command_name in self.commands:
            return self.commands[command_name]
        
        # Alias match
        for cmd in self.commands.values():
            if command_name in cmd.aliases:
                return cmd
        
        return None
    
    def check_permission(self, user: User, required_permission: Permission) -> bool:
        """Check if user has required permission"""
        permission_levels = {
            Permission.PUBLIC: 0,
            Permission.OPERATOR: 1,
            Permission.ADMIN: 2,
            Permission.SUPERUSER: 3
        }
        
        user_level = max([permission_levels[p] for p in user.permissions])
        required_level = permission_levels[required_permission]
        
        return user_level >= required_level
    
    async def process_command(self, execution: CommandExecution) -> CommandResponse:
        """Process a command execution"""
        
        command_name, arguments = self.parse_command(execution.raw_message)
        
        if not command_name:
            return CommandResponse(
                success=False,
                message="Invalid command format. Use !help for available commands.",
                ephemeral=True
            )
        
        command = self.find_command(command_name)
        if not command:
            return CommandResponse(
                success=False,
                message=f"Unknown command: {command_name}. Use !help for available commands.",
                ephemeral=True
            )
        
        # Check permissions
        if not self.check_permission(execution.user, command.permission_required):
            return CommandResponse(
                success=False,
                message=f"Insufficient permissions. Required: {command.permission_required.value}",
                ephemeral=True
            )
        
        # Update execution context
        execution.command = command_name
        execution.arguments = arguments
        
        # Log command execution
        self.command_history.append({
            'timestamp': execution.timestamp,
            'user': execution.user.username,
            'platform': execution.platform,
            'channel': execution.channel,
            'command': command_name,
            'arguments': arguments,
            'raw_message': execution.raw_message
        })
        
        logger.info(f"Executing command '{command_name}' for user {execution.user.username} with args: {arguments}")
        
        # Route to command handler
        handler_method = getattr(self, command.handler, None)
        if handler_method:
            return await handler_method(execution, command)
        else:
            return CommandResponse(
                success=False,
                message=f"Command handler not implemented: {command.handler}"
            )
    
    async def handle_status(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle status command"""
        service_name = execution.arguments[0] if execution.arguments else None
        
        if service_name:
            # Get specific service status
            service_status = self.system_interface.get_service_status(service_name)
            
            if 'error' in service_status:
                return CommandResponse(
                    success=False,
                    message=service_status['error']
                )
            
            return CommandResponse(
                success=True,
                message=f"Status for {service_name}",
                embed={
                    'title': f'Service Status: {service_name}',
                    'color': 0x00FF00 if service_status['status'] == 'running' else 0xFF0000,
                    'fields': [
                        {'name': 'Status', 'value': service_status['status'], 'inline': True},
                        {'name': 'Port', 'value': str(service_status.get('port', 'N/A')), 'inline': True},
                        {'name': 'Uptime', 'value': service_status.get('uptime', 'N/A'), 'inline': True}
                    ]
                }
            )
        else:
            # Get overall system status
            system_status = self.system_interface.get_system_status()
            services = self.system_interface.get_service_status()
            
            if 'error' in system_status:
                return CommandResponse(
                    success=False,
                    message=f"Error getting system status: {system_status['error']}"
                )
            
            # Count running services
            running_services = len([s for s in services.values() if s.get('status') == 'running'])
            total_services = len(services)
            
            status_message = f"""**System Status Overview**
            
🖥️ **System Health**
• CPU: {system_status['cpu']['usage_percent']}% ({system_status['cpu']['status']})
• Memory: {system_status['memory']['usage_percent']}% ({system_status['memory']['status']})
• Disk: {system_status['disk']['usage_percent']}% ({system_status['disk']['status']})

⚙️ **Services**
• Running: {running_services}/{total_services}
• Uptime: {system_status['system']['uptime_hours']} hours

📊 **Resources**
• Memory: {system_status['memory']['used_gb']}GB / {system_status['memory']['total_gb']}GB
• Disk: {system_status['disk']['used_gb']}GB / {system_status['disk']['total_gb']}GB
• Processes: {system_status['system']['processes']}
            """
            
            return CommandResponse(
                success=True,
                message=status_message
            )
    
    async def handle_metrics(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle metrics command"""
        metric_type = execution.arguments[0].lower() if execution.arguments else 'all'
        
        system_status = self.system_interface.get_system_status()
        
        if metric_type == 'cpu':
            return CommandResponse(
                success=True,
                message=f"**CPU Metrics**\n• Usage: {system_status['cpu']['usage_percent']}%\n• Cores: {system_status['cpu']['cores']}\n• Status: {system_status['cpu']['status']}"
            )
        elif metric_type == 'memory':
            return CommandResponse(
                success=True,
                message=f"**Memory Metrics**\n• Used: {system_status['memory']['used_gb']}GB / {system_status['memory']['total_gb']}GB\n• Usage: {system_status['memory']['usage_percent']}%\n• Available: {system_status['memory']['available_gb']}GB"
            )
        elif metric_type == 'disk':
            return CommandResponse(
                success=True,
                message=f"**Disk Metrics**\n• Used: {system_status['disk']['used_gb']}GB / {system_status['disk']['total_gb']}GB\n• Usage: {system_status['disk']['usage_percent']}%\n• Free: {system_status['disk']['free_gb']}GB"
            )
        else:
            return CommandResponse(
                success=True,
                message=f"**System Metrics**\n🖥️ CPU: {system_status['cpu']['usage_percent']}%\n💾 Memory: {system_status['memory']['usage_percent']}%\n💿 Disk: {system_status['disk']['usage_percent']}%\n🔄 Processes: {system_status['system']['processes']}"
            )
    
    async def handle_alerts(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle alerts command"""
        limit = 10
        if execution.arguments:
            try:
                limit = int(execution.arguments[0])
            except ValueError:
                return CommandResponse(
                    success=False,
                    message="Invalid limit. Please provide a number."
                )
        
        alerts = self.system_interface.get_recent_alerts(limit)
        
        if not alerts:
            return CommandResponse(
                success=True,
                message="No recent alerts found."
            )
        
        alert_message = f"**Recent Alerts ({len(alerts)} of {limit})**\n\n"
        for alert in alerts:
            status_emoji = "🔴" if alert['status'] == 'active' else "🟡" if alert['status'] == 'acknowledged' else "🟢"
            alert_message += f"{status_emoji} **{alert['title']}** ({alert['severity']})\n"
            alert_message += f"   ID: {alert['id']} | {alert['time']} | {alert['status']}\n\n"
        
        return CommandResponse(
            success=True,
            message=alert_message
        )
    
    async def handle_restart(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle restart command"""
        if not execution.arguments:
            return CommandResponse(
                success=False,
                message="Please specify a service to restart. Usage: !restart <service>"
            )
        
        service_name = execution.arguments[0]
        
        # Check if service exists
        services = self.system_interface.get_service_status()
        if service_name not in services:
            available_services = ', '.join(services.keys())
            return CommandResponse(
                success=False,
                message=f"Service '{service_name}' not found. Available services: {available_services}"
            )
        
        # Simulate restart
        return CommandResponse(
            success=True,
            message=f"🔄 **Service Restart Initiated**\n\nService: {service_name}\nStatus: Restarting...\nEstimated completion: 30 seconds\n\nThe service will be monitored for successful restart."
        )
    
    async def handle_scale(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle scale command"""
        if len(execution.arguments) < 2:
            return CommandResponse(
                success=False,
                message="Usage: !scale <service> <replicas>"
            )
        
        service_name = execution.arguments[0]
        try:
            replicas = int(execution.arguments[1])
        except ValueError:
            return CommandResponse(
                success=False,
                message="Invalid replica count. Please provide a number."
            )
        
        if replicas < 1 or replicas > 10:
            return CommandResponse(
                success=False,
                message="Replica count must be between 1 and 10."
            )
        
        return CommandResponse(
            success=True,
            message=f"📈 **Scaling Operation Initiated**\n\nService: {service_name}\nTarget Replicas: {replicas}\nStatus: Scaling in progress...\n\nThis may take 1-2 minutes to complete."
        )
    
    async def handle_logs(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle logs command"""
        if not execution.arguments:
            return CommandResponse(
                success=False,
                message="Please specify a service. Usage: !logs <service> [lines]"
            )
        
        service_name = execution.arguments[0]
        lines = 20
        
        if len(execution.arguments) > 1:
            try:
                lines = int(execution.arguments[1])
            except ValueError:
                return CommandResponse(
                    success=False,
                    message="Invalid line count. Please provide a number."
                )
        
        # Mock log output
        log_output = f"""**Recent logs for {service_name} (last {lines} lines)**
        
```
2025-09-14 16:35:01 INFO  [api-gateway] Starting HTTP server on port 8090
2025-09-14 16:35:02 INFO  [api-gateway] JWT authentication middleware enabled
2025-09-14 16:35:03 INFO  [api-gateway] Rate limiting configured: 1000/min
2025-09-14 16:35:10 INFO  [api-gateway] Health check endpoint registered
2025-09-14 16:35:15 DEBUG [api-gateway] Incoming request: GET /health
2025-09-14 16:35:15 DEBUG [api-gateway] Response: 200 OK
```
        """
        
        return CommandResponse(
            success=True,
            message=log_output
        )
    
    async def handle_exec(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle exec command"""
        if not execution.arguments:
            return CommandResponse(
                success=False,
                message="Please specify a command to execute. Usage: !exec <command>"
            )
        
        command_to_exec = ' '.join(execution.arguments)
        result = self.system_interface.execute_system_command(command_to_exec, execution.user)
        
        if result['success']:
            output_message = f"**Command Executed: `{command_to_exec}`**\n\n```\n{result.get('output', 'Command completed successfully')}\n```"
            return CommandResponse(
                success=True,
                message=output_message
            )
        else:
            return CommandResponse(
                success=False,
                message=f"**Command Failed: `{command_to_exec}`**\n\nError: {result['message']}"
            )
    
    async def handle_help(self, execution: CommandExecution, command: Command) -> CommandResponse:
        """Handle help command"""
        if execution.arguments:
            # Help for specific command
            cmd_name = execution.arguments[0]
            cmd = self.find_command(cmd_name)
            
            if not cmd:
                return CommandResponse(
                    success=False,
                    message=f"Command '{cmd_name}' not found."
                )
            
            help_message = f"**Help: {cmd.name}**\n\n"
            help_message += f"**Description:** {cmd.description}\n"
            help_message += f"**Usage:** {cmd.usage}\n"
            help_message += f"**Type:** {cmd.command_type.value}\n"
            help_message += f"**Permission:** {cmd.permission_required.value}\n"
            
            if cmd.aliases:
                help_message += f"**Aliases:** {', '.join(cmd.aliases)}\n"
            
            if cmd.examples:
                help_message += f"\n**Examples:**\n"
                for example in cmd.examples:
                    help_message += f"• `{example}`\n"
            
            return CommandResponse(
                success=True,
                message=help_message,
                ephemeral=True
            )
        else:
            # General help
            user_permissions = execution.user.permissions
            available_commands = []
            
            for cmd in self.commands.values():
                if self.check_permission(execution.user, cmd.permission_required):
                    available_commands.append(cmd)
            
            help_message = f"**AIOps ChatOps Commands** (Available: {len(available_commands)})\n\n"
            
            # Group by type
            command_types = {}
            for cmd in available_commands:
                if cmd.command_type not in command_types:
                    command_types[cmd.command_type] = []
                command_types[cmd.command_type].append(cmd)
            
            for cmd_type, cmds in command_types.items():
                help_message += f"**{cmd_type.value.title()} Commands:**\n"
                for cmd in cmds:
                    aliases = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
                    help_message += f"• `!{cmd.name}`{aliases} - {cmd.description}\n"
                help_message += "\n"
            
            help_message += f"Use `!help <command>` for detailed information about a specific command.\n"
            help_message += f"Your permissions: {', '.join([p.value for p in user_permissions])}"
            
            return CommandResponse(
                success=True,
                message=help_message,
                ephemeral=True
            )
    
    def get_command_stats(self) -> Dict:
        """Get command usage statistics"""
        total_commands = len(self.command_history)
        if total_commands == 0:
            return {'total_commands': 0}
        
        # Command frequency
        command_counts = {}
        user_counts = {}
        platform_counts = {}
        
        for entry in self.command_history:
            cmd = entry['command']
            user = entry['user']
            platform = entry['platform']
            
            command_counts[cmd] = command_counts.get(cmd, 0) + 1
            user_counts[user] = user_counts.get(user, 0) + 1
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        # Recent activity (last hour)
        recent_time = datetime.now() - timedelta(hours=1)
        recent_commands = [e for e in self.command_history if e['timestamp'] > recent_time]
        
        return {
            'total_commands': total_commands,
            'unique_commands': len(command_counts),
            'active_users': len(user_counts),
            'command_frequency': dict(sorted(command_counts.items(), key=lambda x: x[1], reverse=True)),
            'user_activity': dict(sorted(user_counts.items(), key=lambda x: x[1], reverse=True)),
            'platform_usage': platform_counts,
            'recent_activity': len(recent_commands),
            'registered_commands': len(self.commands)
        }

async def demonstrate_chatops():
    """Demonstrate ChatOps command interface"""
    print("AIOps ChatOps Command Interface Demo")
    print("=" * 50)
    
    # Initialize ChatOps processor
    chatops = ChatOpsCommandProcessor(demo_mode=True)
    
    # Create test users
    admin_user = chatops.get_or_create_user("admin001", "admin", "discord")
    operator_user = chatops.get_or_create_user("ops001", "operator", "slack") 
    regular_user = chatops.get_or_create_user("user001", "regularuser", "discord")
    
    # Test commands
    test_commands = [
        # Public commands
        ("!help", regular_user, "discord", "#general"),
        ("!status", regular_user, "discord", "#general"),
        ("!metrics cpu", regular_user, "slack", "#monitoring"),
        
        # Operator commands
        ("!alerts", operator_user, "slack", "#ops"),
        ("!logs api-gateway 10", operator_user, "slack", "#ops"),
        ("!scale analytics-engine 3", operator_user, "discord", "#ops"),
        
        # Admin commands
        ("!restart orchestrator", admin_user, "discord", "#admin"),
        ("!exec ps aux", admin_user, "slack", "#admin"),
        
        # Help and error cases
        ("!help status", regular_user, "discord", "#general"),
        ("!unknown-command", regular_user, "discord", "#general"),
        ("!restart api-gateway", regular_user, "discord", "#general"),  # Permission denied
    ]
    
    print(f"\n🧪 Testing {len(test_commands)} commands with different users and permissions...\n")
    
    for i, (message, user, platform, channel) in enumerate(test_commands, 1):
        print(f"Test {i}: {user.username} ({platform}) in {channel}")
        print(f"Command: {message}")
        
        execution = CommandExecution(
            command="",  # Will be parsed
            user=user,
            platform=platform,
            channel=channel,
            timestamp=datetime.now(),
            raw_message=message
        )
        
        response = await chatops.process_command(execution)
        
        print(f"Status: {'✅ Success' if response.success else '❌ Failed'}")
        print(f"Response: {response.message[:100]}{'...' if len(response.message) > 100 else ''}")
        
        if response.embed:
            print(f"Embed: {response.embed.get('title', 'Rich embed included')}")
        
        if response.ephemeral:
            print("(Private response)")
        
        print("-" * 40)
        
        # Small delay for demo
        await asyncio.sleep(0.1)
    
    # Show statistics
    print(f"\n📊 ChatOps Usage Statistics:")
    stats = chatops.get_command_stats()
    for key, value in stats.items():
        if key in ['command_frequency', 'user_activity', 'platform_usage']:
            print(f"  {key.replace('_', ' ').title()}:")
            for item, count in (value.items() if isinstance(value, dict) else []):
                print(f"    {item}: {count}")
        else:
            print(f"  {key.replace('_', ' ').title()}: {value}")
    
    # Show available commands summary
    print(f"\n📋 Available Commands by Permission Level:")
    for permission in [Permission.PUBLIC, Permission.OPERATOR, Permission.ADMIN]:
        available = [cmd for cmd in chatops.commands.values() 
                    if cmd.permission_required == permission]
        print(f"  {permission.value.title()}: {len(available)} commands")
        for cmd in available:
            print(f"    !{cmd.name} - {cmd.description}")
    
    print(f"\n✅ ChatOps command interface demonstration completed!")

if __name__ == "__main__":
    asyncio.run(demonstrate_chatops())