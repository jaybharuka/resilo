"""
Autonomous Operations System
Proactive issue resolution with user permission management
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

import psutil


class ActionType(Enum):
    SAFE = "safe"           # Auto-approved actions
    MODERATE = "moderate"   # Requires user permission
    RISKY = "risky"        # Requires explicit confirmation

class UrgencyLevel(Enum):
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class AutonomousAction:
    id: str
    name: str
    description: str
    action_type: ActionType
    urgency: UrgencyLevel
    command: str
    reason: str
    auto_approve_time: int  # seconds
    safety_score: float     # 0-1, higher = safer

class AutonomousBot:
    def __init__(self):
        self.pending_actions = {}
        self.action_history = []
        self.user_preferences = {
            'auto_approve_safe': True,
            'auto_approve_timeout': 300,  # 5 minutes
            'max_actions_per_hour': 5,
            'notification_methods': ['dashboard', 'email']
        }
        
        # Define available autonomous actions
        self.available_actions = {
            'clear_temp_files': AutonomousAction(
                id='clear_temp_files',
                name='Clear Temporary Files',
                description='Remove temporary files to free disk space',
                action_type=ActionType.SAFE,
                urgency=UrgencyLevel.MEDIUM,
                command='del /q /s %temp%\\*.*',
                reason='Low disk space detected',
                auto_approve_time=60,
                safety_score=0.95
            ),
            'restart_service': AutonomousAction(
                id='restart_service',
                name='Restart Unresponsive Service',
                description='Restart a service that has stopped responding',
                action_type=ActionType.MODERATE,
                urgency=UrgencyLevel.HIGH,
                command='net stop {service} && net start {service}',
                reason='Service not responding',
                auto_approve_time=180,
                safety_score=0.7
            ),
            'kill_high_cpu_process': AutonomousAction(
                id='kill_high_cpu_process',
                name='Terminate High CPU Process',
                description='Kill process consuming excessive CPU resources',
                action_type=ActionType.MODERATE,
                urgency=UrgencyLevel.HIGH,
                command='taskkill /pid {pid} /f',
                reason='Process using excessive CPU',
                auto_approve_time=300,
                safety_score=0.6
            ),
            'clear_memory_cache': AutonomousAction(
                id='clear_memory_cache',
                name='Clear Memory Cache',
                description='Clear system memory cache to free RAM',
                action_type=ActionType.SAFE,
                urgency=UrgencyLevel.MEDIUM,
                command='powershell "Clear-RecycleBin -Force"',
                reason='High memory usage detected',
                auto_approve_time=120,
                safety_score=0.9
            ),
            'optimize_startup': AutonomousAction(
                id='optimize_startup',
                name='Optimize Startup Programs',
                description='Disable unnecessary startup programs',
                action_type=ActionType.MODERATE,
                urgency=UrgencyLevel.LOW,
                command='optimize_startup_script.ps1',
                reason='Slow boot time detected',
                auto_approve_time=600,
                safety_score=0.8
            )
        }

    async def analyze_system_and_suggest_actions(self) -> List[Dict]:
        """Analyze current system state and suggest autonomous actions"""
        system_data = self._get_current_system_data()
        suggestions = []
        
        # CPU Analysis
        if system_data['cpu'] > 95:
            suggestions.append(self._suggest_cpu_action(system_data))
        
        # Memory Analysis  
        if system_data['memory'] > 90:
            suggestions.append(self._suggest_memory_action(system_data))
        
        # Disk Analysis
        if system_data['disk'] > 95:
            suggestions.append(self._suggest_disk_action(system_data))
        
        # Service Analysis
        unresponsive_services = self._check_service_health()
        if unresponsive_services:
            suggestions.extend(self._suggest_service_actions(unresponsive_services))
        
        return [s for s in suggestions if s is not None]

    def _suggest_cpu_action(self, system_data: Dict) -> Optional[Dict]:
        """Suggest action for high CPU usage"""
        high_cpu_processes = self._get_high_cpu_processes()
        
        if high_cpu_processes:
            process = high_cpu_processes[0]  # Highest CPU process
            action = self.available_actions['kill_high_cpu_process']
            
            return {
                'action': action,
                'details': {
                    'process_name': process['name'],
                    'process_pid': process['pid'],
                    'cpu_percent': process['cpu_percent']
                },
                'reason': f"Process '{process['name']}' using {process['cpu_percent']:.1f}% CPU",
                'estimated_impact': "High - will free up CPU resources immediately"
            }
        return None

    def _suggest_memory_action(self, system_data: Dict) -> Optional[Dict]:
        """Suggest action for high memory usage"""
        action = self.available_actions['clear_memory_cache']
        
        return {
            'action': action,
            'details': {
                'current_memory': system_data['memory'],
                'available_gb': system_data.get('available_memory_gb', 0)
            },
            'reason': f"Memory usage at {system_data['memory']:.1f}%",
            'estimated_impact': "Medium - will free 1-2GB of RAM"
        }

    def _suggest_disk_action(self, system_data: Dict) -> Optional[Dict]:
        """Suggest action for low disk space"""
        action = self.available_actions['clear_temp_files']
        
        return {
            'action': action,
            'details': {
                'current_disk': system_data['disk'],
                'free_gb': system_data.get('disk_free_gb', 0)
            },
            'reason': f"Disk usage at {system_data['disk']:.1f}%",
            'estimated_impact': "Medium - will free 500MB-2GB of space"
        }

    async def request_user_permission(self, action_suggestion: Dict) -> str:
        """Request permission from user for an action"""
        action = action_suggestion['action']
        suggestion_id = f"{action.id}_{int(time.time())}"
        
        # Store pending action
        self.pending_actions[suggestion_id] = {
            'suggestion': action_suggestion,
            'timestamp': datetime.now(),
            'status': 'pending',
            'auto_approve_at': datetime.now() + timedelta(seconds=action.auto_approve_time)
        }
        
        # Check if auto-approval is enabled for this action type
        if (action.action_type == ActionType.SAFE and 
            self.user_preferences['auto_approve_safe']):
            return await self._auto_approve_action(suggestion_id)
        
        # Send notification to user
        await self._send_permission_request(suggestion_id, action_suggestion)
        
        return suggestion_id

    async def _auto_approve_action(self, suggestion_id: str) -> str:
        """Auto-approve safe actions"""
        if suggestion_id in self.pending_actions:
            self.pending_actions[suggestion_id]['status'] = 'auto_approved'
            await self._execute_action(suggestion_id)
            return 'auto_approved'
        return 'error'

    async def _send_permission_request(self, suggestion_id: str, action_suggestion: Dict):
        """Send permission request to user via configured methods"""
        action = action_suggestion['action']
        
        notification = {
            'id': suggestion_id,
            'type': 'permission_request',
            'title': f'Autonomous Action Required: {action.name}',
            'message': action.description,
            'reason': action_suggestion['reason'],
            'urgency': action.urgency.value,
            'safety_score': action.safety_score,
            'estimated_impact': action_suggestion.get('estimated_impact', 'Unknown'),
            'auto_approve_in': action.auto_approve_time,
            'actions': [
                {'id': 'approve', 'label': 'Approve', 'style': 'primary'},
                {'id': 'deny', 'label': 'Deny', 'style': 'secondary'},
                {'id': 'delay', 'label': 'Delay 30min', 'style': 'default'}
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        # Here you would send via WebSocket, email, Slack, etc.
        print(f"🤖 Permission Request: {json.dumps(notification, indent=2)}")

    async def handle_user_response(self, suggestion_id: str, response: str) -> Dict:
        """Handle user's response to permission request"""
        if suggestion_id not in self.pending_actions:
            return {'status': 'error', 'message': 'Invalid suggestion ID'}
        
        pending_action = self.pending_actions[suggestion_id]
        
        if response == 'approve':
            pending_action['status'] = 'approved'
            result = await self._execute_action(suggestion_id)
            return {'status': 'executed', 'result': result}
        
        elif response == 'deny':
            pending_action['status'] = 'denied'
            return {'status': 'denied', 'message': 'Action denied by user'}
        
        elif response == 'delay':
            # Delay by 30 minutes
            pending_action['auto_approve_at'] = datetime.now() + timedelta(minutes=30)
            return {'status': 'delayed', 'message': 'Action delayed by 30 minutes'}
        
        return {'status': 'error', 'message': 'Invalid response'}

    async def _execute_action(self, suggestion_id: str) -> Dict:
        """Execute the approved action"""
        if suggestion_id not in self.pending_actions:
            return {'success': False, 'error': 'Action not found'}
        
        pending_action = self.pending_actions[suggestion_id]
        action = pending_action['suggestion']['action']
        
        try:
            # Log action execution
            execution_log = {
                'id': suggestion_id,
                'action_name': action.name,
                'executed_at': datetime.now().isoformat(),
                'reason': pending_action['suggestion']['reason'],
                'command': action.command
            }
            
            # Here you would execute the actual command
            # For demo purposes, we'll simulate execution
            result = await self._simulate_action_execution(action)
            
            execution_log['result'] = result
            execution_log['success'] = True
            
            # Store in history
            self.action_history.append(execution_log)
            
            # Clean up pending action
            del self.pending_actions[suggestion_id]
            
            return execution_log
            
        except Exception as e:
            error_log = {
                'id': suggestion_id,
                'action_name': action.name,
                'executed_at': datetime.now().isoformat(),
                'success': False,
                'error': str(e)
            }
            self.action_history.append(error_log)
            return error_log

    async def _simulate_action_execution(self, action: AutonomousAction) -> Dict:
        """Simulate action execution (replace with actual implementation)"""
        await asyncio.sleep(1)  # Simulate processing time
        
        return {
            'output': f"Successfully executed {action.name}",
            'impact': f"Estimated improvement: {action.safety_score * 100:.0f}%",
            'duration': "1.2 seconds"
        }

    def _get_current_system_data(self) -> Dict:
        """Get current system metrics"""
        return {
            'cpu': psutil.cpu_percent(interval=1),
            'memory': psutil.virtual_memory().percent,
            'disk': psutil.disk_usage('/').percent,
            'available_memory_gb': psutil.virtual_memory().available / (1024**3),
            'disk_free_gb': psutil.disk_usage('/').free / (1024**3)
        }

    def _get_high_cpu_processes(self) -> List[Dict]:
        """Get processes with high CPU usage"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                if proc.info['cpu_percent'] > 80:
                    processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)

    def _check_service_health(self) -> List[str]:
        """Check for unresponsive services (simplified)"""
        # This would implement actual service health checks
        return []

    def _suggest_service_actions(self, services: List[str]) -> List[Dict]:
        """Suggest actions for unresponsive services"""
        suggestions = []
        for service in services:
            action = self.available_actions['restart_service']
            suggestions.append({
                'action': action,
                'details': {'service_name': service},
                'reason': f"Service '{service}' is unresponsive",
                'estimated_impact': "High - will restore service functionality"
            })
        return suggestions

    async def check_auto_approvals(self):
        """Check for actions that should be auto-approved due to timeout"""
        current_time = datetime.now()
        
        for suggestion_id, pending_action in list(self.pending_actions.items()):
            if (pending_action['status'] == 'pending' and 
                current_time >= pending_action['auto_approve_at']):
                
                action = pending_action['suggestion']['action']
                if action.action_type != ActionType.RISKY:  # Never auto-approve risky actions
                    await self._auto_approve_action(suggestion_id)

    def get_action_history(self) -> List[Dict]:
        """Get history of executed actions"""
        return self.action_history

    def get_pending_actions(self) -> Dict:
        """Get currently pending actions"""
        return {
            k: {
                'action_name': v['suggestion']['action'].name,
                'reason': v['suggestion']['reason'],
                'status': v['status'],
                'timestamp': v['timestamp'].isoformat(),
                'auto_approve_at': v['auto_approve_at'].isoformat()
            }
            for k, v in self.pending_actions.items()
        }

# Integration example
async def demo_autonomous_system():
    """Demo the autonomous system"""
    bot = AutonomousBot()
    
    # Analyze system and get suggestions
    suggestions = await bot.analyze_system_and_suggest_actions()
    
    print("🤖 Autonomous System Analysis:")
    for suggestion in suggestions:
        suggestion_id = await bot.request_user_permission(suggestion)
        print(f"📋 Action suggested: {suggestion_id}")
    
    # Check pending actions
    pending = bot.get_pending_actions()
    print(f"⏳ Pending actions: {len(pending)}")
    
    return bot

if __name__ == "__main__":
    # Run demo
    asyncio.run(demo_autonomous_system())