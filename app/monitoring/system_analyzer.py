"""
Enhanced System Analysis Commands for AIOps Chatbot
Advanced diagnostics and automated problem detection
"""

import json
import platform
import socket
import subprocess
from datetime import datetime, timedelta

import psutil
import requests
import win32api
import win32con
import win32evtlog
import wmi


class SystemAnalyzer:
    def __init__(self):
        self.computer = wmi.WMI() if platform.system() == "Windows" else None
        
    def comprehensive_performance_analysis(self):
        """Perform deep performance analysis"""
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'overall_score': 0,
            'issues': [],
            'recommendations': []
        }
        
        # CPU Analysis
        cpu_times = psutil.cpu_times()
        cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
        cpu_freq = psutil.cpu_freq()
        
        cpu_analysis = {
            'average_usage': sum(cpu_percent) / len(cpu_percent),
            'max_core_usage': max(cpu_percent),
            'cores': len(cpu_percent),
            'frequency': cpu_freq.current if cpu_freq else None,
            'idle_time': cpu_times.idle
        }
        
        if cpu_analysis['average_usage'] > 80:
            analysis['issues'].append("High CPU usage detected")
            analysis['recommendations'].append("Identify and close CPU-intensive applications")
        
        # Memory Analysis  
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        memory_analysis = {
            'physical_percent': memory.percent,
            'physical_used_gb': memory.used / (1024**3),
            'physical_total_gb': memory.total / (1024**3),
            'swap_percent': swap.percent,
            'swap_used_gb': swap.used / (1024**3)
        }
        
        if memory.percent > 85:
            analysis['issues'].append("Critical memory usage")
            analysis['recommendations'].append("Restart applications or add more RAM")
        elif memory.percent > 70:
            analysis['issues'].append("High memory usage")
            analysis['recommendations'].append("Close unnecessary applications")
        
        # Disk Analysis
        disk_analysis = {}
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_analysis[partition.device] = {
                    'total_gb': usage.total / (1024**3),
                    'used_gb': usage.used / (1024**3),
                    'free_gb': usage.free / (1024**3),
                    'percent': (usage.used / usage.total) * 100
                }
                
                if usage.used / usage.total > 0.9:
                    analysis['issues'].append(f"Disk {partition.device} critically full")
                    analysis['recommendations'].append(f"Clean up files on {partition.device}")
            except PermissionError:
                continue
        
        # Network Analysis
        network_stats = psutil.net_io_counters()
        connections = len(psutil.net_connections())
        
        network_analysis = {
            'bytes_sent': network_stats.bytes_sent,
            'bytes_recv': network_stats.bytes_recv,
            'active_connections': connections,
            'packets_sent': network_stats.packets_sent,
            'packets_recv': network_stats.packets_recv
        }
        
        # Process Analysis
        processes = []
        total_processes = 0
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                total_processes += 1
                proc_info = proc.info
                if proc_info['cpu_percent'] > 5 or proc_info['memory_percent'] > 2:
                    processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        process_analysis = {
            'total_processes': total_processes,
            'high_resource_processes': sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:10]
        }
        
        # Calculate overall performance score
        cpu_score = max(0, 100 - cpu_analysis['average_usage'])
        memory_score = max(0, 100 - memory.percent)
        disk_score = max(0, 100 - max([d['percent'] for d in disk_analysis.values()]))
        
        analysis['overall_score'] = int((cpu_score + memory_score + disk_score) / 3)
        analysis['detailed_metrics'] = {
            'cpu': cpu_analysis,
            'memory': memory_analysis,
            'disk': disk_analysis,
            'network': network_analysis,
            'processes': process_analysis
        }
        
        return analysis
    
    def diagnose_network_issues(self):
        """Comprehensive network diagnostics"""
        diagnostics = {
            'timestamp': datetime.now().isoformat(),
            'connection_status': 'unknown',
            'issues': [],
            'tests': {}
        }
        
        # Test internet connectivity
        try:
            response = requests.get('https://8.8.8.8', timeout=5)
            diagnostics['tests']['internet'] = {'status': 'connected', 'latency': response.elapsed.total_seconds()}
            diagnostics['connection_status'] = 'connected'
        except:
            diagnostics['tests']['internet'] = {'status': 'failed'}
            diagnostics['issues'].append("No internet connection")
            diagnostics['connection_status'] = 'disconnected'
        
        # DNS Test
        try:
            socket.gethostbyname('google.com')
            diagnostics['tests']['dns'] = {'status': 'working'}
        except:
            diagnostics['tests']['dns'] = {'status': 'failed'}
            diagnostics['issues'].append("DNS resolution problems")
        
        # Local network test
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            diagnostics['tests']['local_network'] = {'status': 'working', 'ip': local_ip}
        except:
            diagnostics['tests']['local_network'] = {'status': 'failed'}
            diagnostics['issues'].append("Local network configuration issues")
        
        # Network interfaces
        interfaces = psutil.net_if_addrs()
        active_interfaces = []
        for interface, addresses in interfaces.items():
            for addr in addresses:
                if addr.family == socket.AF_INET and addr.address != '127.0.0.1':
                    active_interfaces.append({
                        'interface': interface,
                        'ip': addr.address,
                        'netmask': addr.netmask
                    })
        
        diagnostics['tests']['interfaces'] = active_interfaces
        
        # Network statistics
        net_stats = psutil.net_io_counters()
        diagnostics['statistics'] = {
            'bytes_sent': net_stats.bytes_sent,
            'bytes_received': net_stats.bytes_recv,
            'packets_sent': net_stats.packets_sent,
            'packets_received': net_stats.packets_recv,
            'errors_in': net_stats.errin,
            'errors_out': net_stats.errout,
            'dropped_in': net_stats.dropin,
            'dropped_out': net_stats.dropout
        }
        
        if net_stats.errin > 100 or net_stats.errout > 100:
            diagnostics['issues'].append("High network error rate detected")
        
        return diagnostics
    
    def scan_for_errors(self):
        """Scan system for errors and issues"""
        errors = {
            'timestamp': datetime.now().isoformat(),
            'critical_errors': [],
            'warnings': [],
            'system_events': [],
            'application_crashes': []
        }
        
        # Windows Event Log scanning (if available)
        if platform.system() == "Windows":
            try:
                # Check System Event Log
                hand = win32evtlog.OpenEventLog(None, "System")
                flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                
                events_found = 0
                while events_found < 50:  # Check last 50 events
                    events = win32evtlog.ReadEventLog(hand, flags, 0)
                    if not events:
                        break
                    
                    for event in events:
                        events_found += 1
                        if event.EventType == win32evtlog.EVENTLOG_ERROR_TYPE:
                            errors['critical_errors'].append({
                                'source': event.SourceName,
                                'event_id': event.EventID,
                                'time': event.TimeGenerated.isoformat(),
                                'message': str(event.StringInserts) if event.StringInserts else "No message"
                            })
                        elif event.EventType == win32evtlog.EVENTLOG_WARNING_TYPE:
                            errors['warnings'].append({
                                'source': event.SourceName,
                                'event_id': event.EventID,
                                'time': event.TimeGenerated.isoformat(),
                                'message': str(event.StringInserts) if event.StringInserts else "No message"
                            })
                
                win32evtlog.CloseEventLog(hand)
            except Exception as e:
                errors['system_events'].append(f"Could not read event log: {str(e)}")
        
        # Check for high resource usage processes
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                if proc.info['cpu_percent'] > 90:
                    errors['warnings'].append({
                        'type': 'high_cpu',
                        'process': proc.info['name'],
                        'pid': proc.info['pid'],
                        'usage': proc.info['cpu_percent']
                    })
                
                if proc.info['memory_percent'] > 20:
                    errors['warnings'].append({
                        'type': 'high_memory',
                        'process': proc.info['name'],
                        'pid': proc.info['pid'],
                        'usage': proc.info['memory_percent']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Check disk health
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                if usage.used / usage.total > 0.95:
                    errors['critical_errors'].append({
                        'type': 'disk_full',
                        'partition': partition.device,
                        'usage_percent': (usage.used / usage.total) * 100
                    })
            except PermissionError:
                continue
        
        return errors
    
    def security_analysis(self):
        """Basic security analysis"""
        security = {
            'timestamp': datetime.now().isoformat(),
            'risks': [],
            'recommendations': [],
            'firewall_status': 'unknown',
            'open_ports': []
        }
        
        # Check for open network connections
        connections = psutil.net_connections()
        listening_ports = []
        for conn in connections:
            if conn.status == 'LISTEN' and conn.laddr:
                listening_ports.append({
                    'port': conn.laddr.port,
                    'address': conn.laddr.ip,
                    'pid': conn.pid
                })
        
        security['open_ports'] = listening_ports
        
        # Check for unusual processes
        suspicious_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'connections']):
            try:
                # Basic heuristic: processes with many network connections
                if len(proc.info.get('connections', [])) > 10:
                    suspicious_processes.append({
                        'name': proc.info['name'],
                        'pid': proc.info['pid'],
                        'connections': len(proc.info.get('connections', []))
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if suspicious_processes:
            security['risks'].append("Processes with high network activity detected")
            security['suspicious_processes'] = suspicious_processes
        
        # Windows Firewall status (basic check)
        if platform.system() == "Windows":
            try:
                result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], 
                                     capture_output=True, text=True)
                if 'ON' in result.stdout:
                    security['firewall_status'] = 'enabled'
                else:
                    security['firewall_status'] = 'disabled'
                    security['risks'].append("Windows Firewall is disabled")
                    security['recommendations'].append("Enable Windows Firewall for better security")
            except:
                security['firewall_status'] = 'unknown'
        
        return security

# Export analyzer for use in chatbot
system_analyzer = SystemAnalyzer()