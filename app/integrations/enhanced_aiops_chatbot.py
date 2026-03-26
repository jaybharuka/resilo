"""
Enhanced AIOps Chatbot with Hugging Face AI Integration
Combines Google Gemini Pro with free Hugging Face models for superior performance
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any
import traceback

# System monitoring
import psutil
import platform

# Hugging Face integration (optional — requires transformers + torch)
try:
    from huggingface_ai_integration import enhance_response_with_ai, initialize_huggingface_ai
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    HUGGINGFACE_AVAILABLE = False
    enhance_response_with_ai = lambda text, *a, **kw: text
    initialize_huggingface_ai = lambda *a, **kw: None

# Google Gemini (keep existing functionality)
try:
    from openai import OpenAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ OpenAI not available. Using Hugging Face AI only.")

class EnhancedAIOpsBot:
    """
    Advanced AIOps chatbot with dual AI engines:
    - Google Gemini Pro for general conversations
    - Hugging Face models for specialized AI tasks
    """
    
    def __init__(self):
        self.bot_name = "AIOps Assistant"
        self.version = "3.0 - Hugging Face Enhanced"
        
        # Initialize AI engines
        self.gemini_model = None
        self.huggingface_ai = None
        
        # System monitoring
        self.system_data = {}
        
        # Chat history with AI enhancements
        self.chat_history = []
        
        print(f"🚀 Initializing {self.bot_name} v{self.version}")
        self.initialize_ai_engines()
        self.update_system_data()
    
    def initialize_ai_engines(self):
        """Initialize both AI engines"""
        try:
            # Initialize Hugging Face AI (always available)
            print("🤗 Initializing Hugging Face AI...")
            self.huggingface_ai = initialize_huggingface_ai()
            
            # Initialize Google Gemini if available
            if GEMINI_AVAILABLE:
                print("🧠 Initializing NVIDIA OpenAI Client...")
                nvidia_api_key = os.getenv('AI_API_KEY') or os.getenv('NVIDIA_API_KEY')
                if nvidia_api_key:
                    self.gemini_model = OpenAI(
                        base_url="https://integrate.api.nvidia.com/v1",
                        api_key=nvidia_api_key
                    )
                    print("✅ NVIDIA OpenAI Client initialized")
                else:
                    print("⚠️ NVIDIA_API_KEY not found in environment variables")
            
            print("✅ AI engines initialization complete!")
            
        except Exception as e:
            print(f"❌ Error initializing AI engines: {e}")
            traceback.print_exc()
    
    def update_system_data(self):
        """Update current system monitoring data"""
        try:
            # CPU Information
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory Information
            memory = psutil.virtual_memory()
            
            # Disk Information
            disk = psutil.disk_usage('/')
            
            # Network Information
            network = psutil.net_io_counters()
            
            # Process Information
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Top 5 CPU-intensive processes
            top_processes = sorted(processes, key=lambda x: x['cpu_percent'] or 0, reverse=True)[:5]
            
            self.system_data = {
                "timestamp": datetime.now().isoformat(),
                "cpu": {
                    "usage_percent": cpu_percent,
                    "count": cpu_count,
                    "frequency": cpu_freq.current if cpu_freq else "Unknown"
                },
                "memory": {
                    "total": round(memory.total / (1024**3), 2),  # GB
                    "available": round(memory.available / (1024**3), 2),  # GB
                    "percent": memory.percent,
                    "used": round(memory.used / (1024**3), 2)  # GB
                },
                "disk": {
                    "total": round(disk.total / (1024**3), 2),  # GB
                    "used": round(disk.used / (1024**3), 2),  # GB
                    "free": round(disk.free / (1024**3), 2),  # GB
                    "percent": round((disk.used / disk.total) * 100, 1)
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                },
                "top_processes": top_processes,
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine()
                }
            }
            
        except Exception as e:
            print(f"Error updating system data: {e}")
            self.system_data = {"error": "Unable to collect system data", "timestamp": datetime.now().isoformat()}
    
    def _status_label(self, value, warn=70, crit=85):
        """Return a plain-text status label based on thresholds."""
        if value is None or value == 'Unknown':
            return 'Unknown'
        try:
            v = float(value)
            if v >= crit:
                return 'CRITICAL'
            elif v >= warn:
                return 'WARNING'
            else:
                return 'OK'
        except (TypeError, ValueError):
            return 'Unknown'

    def _fmt_bytes(self, b):
        """Format raw bytes into human-readable string."""
        try:
            b = int(b)
            if b >= 1024**3:
                return f"{b / 1024**3:.1f} GB"
            elif b >= 1024**2:
                return f"{b / 1024**2:.1f} MB"
            elif b >= 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b} B"
        except (TypeError, ValueError):
            return str(b)

    def get_base_response_gemini(self, user_message: str) -> str:
        """Get base response from Google Gemini"""
        try:
            if not self.gemini_model:
                return self.get_fallback_response(user_message)

            cpu   = self.system_data.get('cpu', {})
            mem   = self.system_data.get('memory', {})
            disk  = self.system_data.get('disk', {})
            net   = self.system_data.get('network', {})
            procs = self.system_data.get('top_processes', [])
            plat  = self.system_data.get('platform', {})

            top_proc_lines = "\n".join(
                f"  - {p.get('name','?')} PID={p.get('pid','?')} CPU={p.get('cpu_percent',0):.1f}% MEM={p.get('memory_percent',0):.1f}%"
                for p in procs[:5]
            )

            system_context = f"""You are an expert AIOps assistant with direct access to live system telemetry.
Respond concisely and technically. Use the real metrics below in every answer.
Format responses in clean HTML using <strong>, <ul>, <li>, <br> — no markdown.

=== LIVE SYSTEM SNAPSHOT ({self.system_data.get('timestamp','')}) ===
Platform : {plat.get('system','?')} {plat.get('release','?')} ({plat.get('machine','?')})
CPU      : {cpu.get('usage_percent','?')}% used | {cpu.get('count','?')} cores | {cpu.get('frequency','?')} MHz
Memory   : {mem.get('percent','?')}% used | {mem.get('used','?')} GB / {mem.get('total','?')} GB | {mem.get('available','?')} GB free
Disk     : {disk.get('percent','?')}% used | {disk.get('used','?')} GB / {disk.get('total','?')} GB | {disk.get('free','?')} GB free
Network  : Sent {self._fmt_bytes(net.get('bytes_sent',0))} | Recv {self._fmt_bytes(net.get('bytes_recv',0))}
Top processes by CPU:
{top_proc_lines or '  (none available)'}
=== END SNAPSHOT ===

User: {user_message}

Rules:
- Never say you "don't have access" to metrics — you have them above.
- If asked for health/status, give a structured report of all metrics.
- If values are high (CPU>80%, MEM>85%, DISK>90%), flag them clearly and give specific remediation steps.
- Be specific: use actual numbers from the snapshot, not placeholders.
- Keep response under 300 words. Use HTML formatting."""

            response = self.gemini_model.chat.completions.create(
                model="abacusai/dracarys-llama-3.1-70b-instruct",
                messages=[{"role": "user", "content": system_context}],
                temperature=1,
                top_p=1,
                max_tokens=4096,
                stream=False
            )
            return response.choices[0].message.content if response.choices else "I apologize, but I couldn't generate a response."

        except Exception as e:
            print(f"Error with Gemini response: {e}")
            return self.get_fallback_response(user_message)

    def get_fallback_response(self, user_message: str) -> str:
        """
        Rich metric-based responses using live psutil data.
        Covers all common query intents without any AI dependency.
        """
        msg = user_message.lower().strip()

        cpu   = self.system_data.get('cpu', {})
        mem   = self.system_data.get('memory', {})
        disk  = self.system_data.get('disk', {})
        net   = self.system_data.get('network', {})
        procs = self.system_data.get('top_processes', [])
        plat  = self.system_data.get('platform', {})

        cpu_pct  = cpu.get('usage_percent')
        mem_pct  = mem.get('percent')
        disk_pct = disk.get('percent')

        cpu_status  = self._status_label(cpu_pct,  warn=70, crit=85)
        mem_status  = self._status_label(mem_pct,  warn=75, crit=90)
        disk_status = self._status_label(disk_pct, warn=75, crit=90)

        def pct_bar(value, warn=70, crit=85):
            """Return a simple ASCII bar and colored label."""
            try:
                v = float(value)
                filled = int(v / 5)
                bar = '█' * filled + '░' * (20 - filled)
                label = 'CRITICAL' if v >= crit else 'WARNING' if v >= warn else 'OK'
                return bar, label, v
            except (TypeError, ValueError):
                return '░' * 20, 'UNKNOWN', 0

        # ── Health / Status / Summary ──────────────────────────────────────────
        if any(k in msg for k in ['health', 'status', 'summary', 'check', 'overview', 'report', 'how is', 'how are']):
            issues = []
            if cpu_status in ('WARNING', 'CRITICAL'):
                issues.append(f"CPU at {cpu_pct}% — consider identifying top processes consuming resources")
            if mem_status in ('WARNING', 'CRITICAL'):
                issues.append(f"Memory at {mem_pct}% — {mem.get('available', '?')} GB available, consider freeing cache or restarting heavy services")
            if disk_status in ('WARNING', 'CRITICAL'):
                issues.append(f"Disk at {disk_pct}% — only {disk.get('free', '?')} GB free, run disk cleanup")

            overall = 'CRITICAL' if any(s == 'CRITICAL' for s in [cpu_status, mem_status, disk_status]) \
                else 'WARNING' if any(s == 'WARNING' for s in [cpu_status, mem_status, disk_status]) \
                else 'OK'

            top_procs_html = ''.join(
                f"<li><strong>{p.get('name','?')}</strong> (PID {p.get('pid','?')}) — "
                f"CPU: {p.get('cpu_percent', 0):.1f}% | MEM: {p.get('memory_percent', 0):.1f}%</li>"
                for p in procs[:5]
            ) if procs else '<li>No process data available</li>'

            issues_html = ''.join(f'<li>⚠ {i}</li>' for i in issues) if issues else '<li>No issues detected</li>'

            return (
                f"<strong>System Health Report</strong> &mdash; "
                f"<strong style='color:{'#ef4444' if overall=='CRITICAL' else '#f59e0b' if overall=='WARNING' else '#10b981'}'>{overall}</strong><br><br>"
                f"<strong>CPU</strong><br>"
                f"Usage: <strong>{cpu_pct}%</strong> [{cpu_status}] | Cores: {cpu.get('count','?')} | Freq: {cpu.get('frequency','?')} MHz<br><br>"
                f"<strong>Memory</strong><br>"
                f"Usage: <strong>{mem_pct}%</strong> [{mem_status}] | Used: {mem.get('used','?')} GB / {mem.get('total','?')} GB | Free: {mem.get('available','?')} GB<br><br>"
                f"<strong>Disk</strong><br>"
                f"Usage: <strong>{disk_pct}%</strong> [{disk_status}] | Used: {disk.get('used','?')} GB / {disk.get('total','?')} GB | Free: {disk.get('free','?')} GB<br><br>"
                f"<strong>Network I/O</strong><br>"
                f"Sent: {self._fmt_bytes(net.get('bytes_sent',0))} | Received: {self._fmt_bytes(net.get('bytes_recv',0))}<br><br>"
                f"<strong>Top Processes</strong><ul>{top_procs_html}</ul>"
                f"<strong>Issues</strong><ul>{issues_html}</ul>"
                f"Platform: {plat.get('system','?')} {plat.get('release','?')} ({plat.get('machine','?')})"
            )

        # ── CPU / Performance / Bottleneck ────────────────────────────────────
        if any(k in msg for k in ['cpu', 'processor', 'performance', 'bottleneck', 'analyze', 'slow', 'lag', 'throughput']):
            top_procs_html = ''.join(
                f"<li><strong>{p.get('name','?')}</strong> (PID {p.get('pid','?')}) &mdash; "
                f"{p.get('cpu_percent',0):.1f}% CPU, {p.get('memory_percent',0):.1f}% MEM</li>"
                for p in procs[:5]
            ) if procs else '<li>No process data</li>'

            advice = []
            if cpu_pct is not None:
                if float(cpu_pct) >= 85:
                    advice.append("CPU is critically high. Identify and terminate or throttle the top consuming process immediately.")
                    if procs:
                        advice.append(f"Primary offender: <strong>{procs[0].get('name','?')}</strong> at {procs[0].get('cpu_percent',0):.1f}%.")
                elif float(cpu_pct) >= 70:
                    advice.append("CPU is elevated. Monitor for sustained spikes over the next few minutes.")
                else:
                    advice.append("CPU load is within normal range. No immediate action needed.")
            advice.append(f"Cores available: {cpu.get('count','?')} | Clock speed: {cpu.get('frequency','?')} MHz.")

            advice_html = ''.join(f'<li>{a}</li>' for a in advice)

            return (
                f"<strong>CPU Performance Analysis</strong><br><br>"
                f"Current usage: <strong>{cpu_pct}%</strong> [{cpu_status}]<br>"
                f"Cores: {cpu.get('count','?')} | Frequency: {cpu.get('frequency','?')} MHz<br><br>"
                f"<strong>Top CPU Consumers</strong><ul>{top_procs_html}</ul>"
                f"<strong>Analysis</strong><ul>{advice_html}</ul>"
            )

        # ── Memory / RAM ──────────────────────────────────────────────────────
        if any(k in msg for k in ['memory', 'ram', 'heap', 'swap', 'oom']):
            advice = []
            if mem_pct is not None:
                if float(mem_pct) >= 90:
                    advice.append("Memory is critically low. Restart or kill memory-heavy services immediately.")
                elif float(mem_pct) >= 75:
                    advice.append("Memory is elevated. Consider clearing caches or restarting services proactively.")
                else:
                    advice.append("Memory usage is healthy.")
                advice.append(f"{mem.get('available','?')} GB of free memory remains.")
            if procs:
                top_mem = sorted(procs, key=lambda x: x.get('memory_percent', 0) or 0, reverse=True)[:3]
                mem_html = ''.join(
                    f"<li><strong>{p.get('name','?')}</strong> — {p.get('memory_percent',0):.1f}% MEM</li>"
                    for p in top_mem
                )
                advice_html = ''.join(f'<li>{a}</li>' for a in advice)
                return (
                    f"<strong>Memory Analysis</strong><br><br>"
                    f"Usage: <strong>{mem_pct}%</strong> [{mem_status}]<br>"
                    f"Used: {mem.get('used','?')} GB / Total: {mem.get('total','?')} GB / Free: {mem.get('available','?')} GB<br><br>"
                    f"<strong>Top Memory Consumers</strong><ul>{mem_html}</ul>"
                    f"<strong>Recommendations</strong><ul>{advice_html}</ul>"
                )
            return (
                f"<strong>Memory</strong>: {mem_pct}% used [{mem_status}]<br>"
                f"{mem.get('used','?')} GB used / {mem.get('total','?')} GB total / {mem.get('available','?')} GB free"
            )

        # ── Disk / Storage ────────────────────────────────────────────────────
        if any(k in msg for k in ['disk', 'storage', 'space', 'drive', 'filesystem', 'file system']):
            advice = []
            if disk_pct is not None:
                if float(disk_pct) >= 90:
                    advice.append("Disk is critically full. Run cleanup immediately — remove logs, temp files, old backups.")
                elif float(disk_pct) >= 75:
                    advice.append("Disk usage is elevated. Plan cleanup within the next 24 hours.")
                else:
                    advice.append("Disk usage is healthy.")
                advice.append(f"{disk.get('free','?')} GB of free space remaining.")
            advice_html = ''.join(f'<li>{a}</li>' for a in advice)
            return (
                f"<strong>Disk Storage Analysis</strong><br><br>"
                f"Usage: <strong>{disk_pct}%</strong> [{disk_status}]<br>"
                f"Used: {disk.get('used','?')} GB / Total: {disk.get('total','?')} GB / Free: {disk.get('free','?')} GB<br><br>"
                f"<strong>Recommendations</strong><ul>{advice_html}</ul>"
            )

        # ── Network ───────────────────────────────────────────────────────────
        if any(k in msg for k in ['network', 'bandwidth', 'traffic', 'packet', 'latency', 'connection', 'sent', 'received']):
            return (
                f"<strong>Network I/O Statistics</strong><br><br>"
                f"Bytes Sent: <strong>{self._fmt_bytes(net.get('bytes_sent',0))}</strong><br>"
                f"Bytes Received: <strong>{self._fmt_bytes(net.get('bytes_recv',0))}</strong><br>"
                f"Packets Sent: {net.get('packets_sent',0):,}<br>"
                f"Packets Received: {net.get('packets_recv',0):,}<br><br>"
                f"These are cumulative counters since the last system boot. "
                f"For per-second throughput, compare two snapshots over a time interval."
            )

        # ── Processes ─────────────────────────────────────────────────────────
        if any(k in msg for k in ['process', 'processes', 'running', 'task', 'service', 'pid']):
            if not procs:
                return "No process data is available at this time."
            rows = ''.join(
                f"<li><strong>{p.get('name','?')}</strong> (PID {p.get('pid','?')}) &mdash; "
                f"CPU: {p.get('cpu_percent',0):.1f}% | MEM: {p.get('memory_percent',0):.1f}%</li>"
                for p in procs[:10]
            )
            return (
                f"<strong>Top Processes by CPU Usage</strong><ul>{rows}</ul>"
                f"Showing top {min(len(procs), 10)} of all running processes."
            )

        # ── Optimization ──────────────────────────────────────────────────────
        if any(k in msg for k in ['optim', 'improve', 'reduce', 'tune', 'resource', 'efficient']):
            tips = []
            if cpu_pct is not None and float(cpu_pct) >= 70:
                tops = [p.get('name', '?') for p in procs[:2]]
                tips.append(f"<strong>CPU ({cpu_pct}% used):</strong> Throttle or reschedule {', '.join(tops) if tops else 'high-CPU processes'}.")
            if mem_pct is not None and float(mem_pct) >= 70:
                tips.append(f"<strong>Memory ({mem_pct}% used):</strong> Clear page cache (`sync; echo 3 > /proc/sys/vm/drop_caches`) or restart memory-heavy services.")
            if disk_pct is not None and float(disk_pct) >= 70:
                tips.append(f"<strong>Disk ({disk_pct}% used):</strong> Delete old logs in /var/log, clear temp files, and archive unused data.")
            if not tips:
                tips.append(f"System is well-optimized. CPU: {cpu_pct}%, Memory: {mem_pct}%, Disk: {disk_pct}% — all within healthy thresholds.")
                tips.append("Consider scheduling regular log rotation and monitoring alert thresholds.")
            tips_html = ''.join(f'<li>{t}</li>' for t in tips)
            return f"<strong>Resource Optimization Recommendations</strong><ul>{tips_html}</ul>"

        # ── Troubleshoot ──────────────────────────────────────────────────────
        if any(k in msg for k in ['troubleshoot', 'issue', 'problem', 'error', 'debug', 'diagnos', 'fix', 'fail', 'crash', 'alert']):
            findings = []
            if cpu_pct is not None and float(cpu_pct) >= 85:
                findings.append(f"🔴 <strong>High CPU</strong>: {cpu_pct}% — Top process: {procs[0].get('name','?') if procs else 'unknown'}")
            elif cpu_pct is not None and float(cpu_pct) >= 70:
                findings.append(f"🟡 <strong>Elevated CPU</strong>: {cpu_pct}%")
            if mem_pct is not None and float(mem_pct) >= 90:
                findings.append(f"🔴 <strong>Memory critical</strong>: {mem_pct}% — {mem.get('available','?')} GB remaining")
            elif mem_pct is not None and float(mem_pct) >= 75:
                findings.append(f"🟡 <strong>Memory elevated</strong>: {mem_pct}%")
            if disk_pct is not None and float(disk_pct) >= 90:
                findings.append(f"🔴 <strong>Disk critical</strong>: {disk_pct}% — {disk.get('free','?')} GB free")
            if not findings:
                findings.append("🟢 No critical issues found. CPU, memory, and disk are all within normal parameters.")

            findings_html = ''.join(f'<li>{f}</li>' for f in findings)
            steps = (
                "<li>Check application logs for errors (Event Viewer on Windows, /var/log on Linux).</li>"
                "<li>Verify network connectivity if services are unreachable.</li>"
                "<li>Review recent deployments or config changes that may have introduced the issue.</li>"
                "<li>Run the Process Snapshot action to see all active processes.</li>"
            )
            return (
                f"<strong>Diagnostic Report</strong><br><br>"
                f"<strong>Findings</strong><ul>{findings_html}</ul>"
                f"<strong>Recommended Steps</strong><ul>{steps}</ul>"
            )

        # ── Default: full snapshot ─────────────────────────────────────────────
        top_procs_html = ''.join(
            f"<li><strong>{p.get('name','?')}</strong> — CPU: {p.get('cpu_percent',0):.1f}% | MEM: {p.get('memory_percent',0):.1f}%</li>"
            for p in procs[:5]
        ) if procs else '<li>No process data available</li>'

        return (
            f"<strong>Live System Snapshot</strong><br><br>"
            f"CPU: <strong>{cpu_pct}%</strong> [{cpu_status}] | {cpu.get('count','?')} cores @ {cpu.get('frequency','?')} MHz<br>"
            f"Memory: <strong>{mem_pct}%</strong> [{mem_status}] | {mem.get('used','?')} / {mem.get('total','?')} GB<br>"
            f"Disk: <strong>{disk_pct}%</strong> [{disk_status}] | {disk.get('free','?')} GB free<br>"
            f"Network: ↑ {self._fmt_bytes(net.get('bytes_sent',0))} / ↓ {self._fmt_bytes(net.get('bytes_recv',0))}<br><br>"
            f"<strong>Top Processes</strong><ul>{top_procs_html}</ul>"
            f"Ask me about <em>health</em>, <em>CPU</em>, <em>memory</em>, <em>disk</em>, <em>network</em>, <em>processes</em>, <em>optimization</em>, or <em>troubleshooting</em>."
        )
    
    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Main message processing with dual AI enhancement
        """
        try:
            # Update system data
            self.update_system_data()
            
            # Get base response from Gemini or fallback
            base_response = self.get_base_response_gemini(user_message)
            
            # Enhance with Hugging Face AI
            if self.huggingface_ai:
                print("🤗 Enhancing response with Hugging Face AI...")
                ai_enhancement = enhance_response_with_ai(
                    user_message, 
                    base_response, 
                    self.system_data
                )
                
                # Combine responses
                final_response = ai_enhancement.get('enhanced_response', base_response)
                
                # Add chat entry with AI analysis
                chat_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user_message": user_message,
                    "base_response": base_response,
                    "enhanced_response": final_response,
                    "ai_analysis": {
                        "sentiment": ai_enhancement.get('sentiment', {}),
                        "issue_classification": ai_enhancement.get('issue_classification', {}),
                        "suggested_actions": ai_enhancement.get('suggested_actions', [])
                    },
                    "system_snapshot": self.system_data
                }
                
                self.chat_history.append(chat_entry)
                
                return {
                    "response": final_response,
                    "ai_analysis": chat_entry["ai_analysis"],
                    "system_data": self.system_data,
                    "ai_powered": True
                }
            
            else:
                # Fallback without Hugging Face enhancement
                chat_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user_message": user_message,
                    "response": base_response,
                    "system_snapshot": self.system_data,
                    "ai_powered": False
                }
                
                self.chat_history.append(chat_entry)
                
                return {
                    "response": base_response,
                    "system_data": self.system_data,
                    "ai_powered": False
                }
        
        except Exception as e:
            error_msg = f"I encountered an error while processing your request: {str(e)}"
            print(f"Error in process_message: {e}")
            traceback.print_exc()
            
            return {
                "response": error_msg,
                "error": True,
                "system_data": self.system_data
            }
    
    def get_system_summary(self) -> str:
        """Get a comprehensive system summary with AI analysis"""
        try:
            # Basic system summary
            cpu_usage = self.system_data.get('cpu', {}).get('usage_percent', 'Unknown')
            memory_usage = self.system_data.get('memory', {}).get('percent', 'Unknown')
            disk_usage = self.system_data.get('disk', {}).get('percent', 'Unknown')
            
            summary = f"""
🖥️ <strong>System Health Report</strong>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 CPU Usage: {cpu_usage}%
💾 Memory Usage: {memory_usage}%
💿 Disk Usage: {disk_usage}%

"""
            
            # Add AI-powered analysis if available
            if self.huggingface_ai:
                # Analyze overall system health
                system_status = "System performance is good"
                if cpu_usage != 'Unknown' and float(cpu_usage) > 80:
                    system_status = "High CPU usage detected - performance may be impacted"
                elif memory_usage != 'Unknown' and float(memory_usage) > 85:
                    system_status = "High memory usage detected - system may slow down"
                elif disk_usage != 'Unknown' and float(disk_usage) > 90:
                    system_status = "Low disk space - cleanup recommended"
                
                # Use Hugging Face to classify the system state
                ai_analysis = enhance_response_with_ai(
                    system_status,
                    "System analysis complete",
                    self.system_data
                )
                
                summary += f"🤖 <strong>AI Analysis:</strong> {ai_analysis.get('enhanced_response', system_status)}\n\n"
                
                if ai_analysis.get('suggested_actions'):
                    summary += "💡 <strong>Suggested Actions:</strong>\n"
                    for action in ai_analysis['suggested_actions'][:3]:
                        summary += f"   • {action}\n"
            
            return summary
            
        except Exception as e:
            return f"Error generating system summary: {e}"
    
    def start_interactive_chat(self):
        """Start interactive chat session"""
        print(f"\n{'='*60}")
        print(f"🤖 {self.bot_name} v{self.version}")
        print(f"{'='*60}")
        print("🤗 Enhanced with Hugging Face AI models")
        print("🧠 Powered by Google Gemini Pro")
        print("💬 Type 'quit' to exit, 'system' for system summary")
        print(f"{'='*60}\n")
        
        # Show initial system summary
        print(self.get_system_summary())
        
        while True:
            try:
                user_input = input("\n💬 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye! Thanks for using AIOps Assistant!")
                    break
                
                elif user_input.lower() in ['system', 'status', 'summary']:
                    print(self.get_system_summary())
                    continue
                
                elif not user_input:
                    continue
                
                # Process message with AI enhancement
                print("🤖 Analyzing... ", end="", flush=True)
                result = self.process_message(user_input)
                print("✅")
                
                # Display response
                print(f"\n🤖 AIOps Assistant: {result['response']}")
                
                # Show AI analysis if available
                if result.get('ai_analysis'):
                    ai_analysis = result['ai_analysis']
                    sentiment = ai_analysis.get('sentiment', {})
                    classification = ai_analysis.get('issue_classification', {})
                    
                    print(f"\n📊 <strong>AI Analysis:</strong>")
                    print(f"   🎭 Sentiment: {sentiment.get('sentiment', 'neutral')} ({sentiment.get('emotion', 'calm')})")
                    print(f"   📝 Issue Type: {classification.get('primary_category', 'general')}")
                    
                    if classification.get('suggested_actions'):
                        print(f"   💡 Suggestions: {', '.join(classification['suggested_actions'][:2])}")
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye! Thanks for using AIOps Assistant!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                continue

def main():
    """Main function to start the enhanced chatbot"""
    try:
        # Create and start the enhanced AIOps bot
        bot = EnhancedAIOpsBot()
        bot.start_interactive_chat()
        
    except Exception as e:
        print(f"Failed to start AIOps bot: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()