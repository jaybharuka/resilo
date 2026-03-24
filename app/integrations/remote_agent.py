#!/usr/bin/env python3
"""
AIOps Remote Agent
──────────────────
Streams real system metrics AND executes allowlisted remediation commands.

New protocol (core_api.py / port 8000):
    AIOPS_SERVER=https://HOST  AIOPS_KEY=<api_key>  AIOPS_ORG=<org_id>  python app/integrations/remote_agent.py
    → uses POST /ingest/heartbeat with X-Agent-Key header + org_id in body

Legacy protocol (Flask / port 5000):
    python app/integrations/remote_agent.py --server http://HOST:5000 --token YOUR_TOKEN
    → uses POST /agents/heartbeat with token in JSON body

Both protocols are supported simultaneously. New protocol is preferred when
AIOPS_KEY and AIOPS_ORG environment variables are set.

Safety flags:
    ALLOW_SYSTEM_ACTIONS=true   — required env var to enable command execution
                                  (defaults to false for safe read-only mode)

Requirements: psutil, requests  (auto-installed if missing)
Platforms:    Windows · Linux · macOS
"""

import argparse
import os
import platform
import socket
import subprocess
import sys
import threading
import time

# ── Auto-install lightweight deps ────────────────────────────────────────────
for _pkg in ['psutil', 'requests']:
    try:
        __import__(_pkg)
    except ImportError:
        print(f'[agent] Installing {_pkg}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', _pkg, '-q'])

import psutil      # noqa: E402
import requests    # noqa: E402

# ── Safety gate ───────────────────────────────────────────────────────────────
ALLOW_SYSTEM_ACTIONS = os.environ.get('ALLOW_SYSTEM_ACTIONS', 'false').lower() in ('1', 'true', 'yes')

OS_NAME  = platform.system().lower()   # 'linux' | 'darwin' | 'windows'
HOSTNAME = socket.gethostname()

# ── Allowlisted static command map ────────────────────────────────────────────
# Each action maps to a hardcoded argv list per OS.
# No user input ever reaches the shell — params only used for dynamic actions.
STATIC_COMMANDS = {
    'clear_cache': {
        'linux':   ['sh', '-c', 'sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null; echo done'],
        'darwin':  ['purge'],
        'windows': ['ipconfig', '/flushdns'],
    },
    'disk_cleanup': {
        'linux': [
            'sh', '-c',
            'find /tmp -type f -atime +1 -delete 2>/dev/null; '
            'find /var/log -name "*.gz" -delete 2>/dev/null; '
            'echo cleanup done',
        ],
        'darwin': ['sh', '-c', 'find /tmp -type f -atime +1 -delete 2>/dev/null; echo done'],
        'windows': ['cmd', '/c', 'del /q /f /s %TEMP%\\* 2>nul & echo done'],
    },
    'free_memory': {
        'linux':   ['sh', '-c', 'sync; sysctl -w vm.drop_caches=3 2>/dev/null; echo done'],
        'darwin':  ['purge'],
        'windows': [
            'powershell', '-NoProfile', '-Command',
            '[System.GC]::Collect(); Write-Output "GC complete"',
        ],
    },
    'run_gc': {
        'linux': [
            'sh', '-c',
            'for pid in $(pgrep -x python3 2>/dev/null); '
            'do kill -SIGUSR1 "$pid" 2>/dev/null; done; echo done',
        ],
        'darwin': [
            'sh', '-c',
            'for pid in $(pgrep -x python3 2>/dev/null); '
            'do kill -SIGUSR1 "$pid" 2>/dev/null; done; echo done',
        ],
        'windows': [
            'powershell', '-NoProfile', '-Command',
            '[System.GC]::Collect(); Write-Output "GC triggered"',
        ],
    },
}

# Actions that are safe to run with no system-actions permission
READ_ONLY_ACTIONS = {'ping'}     # future use — reserved


# ── Command executor ──────────────────────────────────────────────────────────

def _validate_service_name(name: str) -> bool:
    """Only allow alphanumeric + hyphen/underscore service names."""
    return bool(name) and all(c.isalnum() or c in '-_.' for c in name)


def _validate_process_target(value: str) -> bool:
    """Allow alphanumeric process names or numeric PIDs."""
    return bool(value) and (str(value).isdigit() or
                            all(c.isalnum() or c in '-_./' for c in str(value)))


def execute_command(cmd: dict) -> tuple:
    """
    Execute one allowlisted command.
    Returns (status, result_str, error_str)
      status ∈ {'success', 'failed', 'skipped'}
    """
    action = cmd.get('action', '')
    params = cmd.get('params') or {}

    # ── Safety gate ──────────────────────────────────────────────────────────
    if not ALLOW_SYSTEM_ACTIONS:
        return ('skipped',
                None,
                'ALLOW_SYSTEM_ACTIONS is not set. '
                'Set the env var to "true" and restart the agent to enable execution.')

    # ── Dynamic actions ───────────────────────────────────────────────────────

    if action == 'kill_process':
        target = str(params.get('name') or params.get('pid') or '').strip()
        if not target or not _validate_process_target(target):
            return ('failed', None,
                    'kill_process requires params.name (str) or params.pid (int)')
        killed = []
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if (str(proc.pid) == target or
                            proc.name().lower() == target.lower()):
                        proc.terminate()
                        killed.append(f'{proc.name()}(pid={proc.pid})')
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if killed:
                return ('success', f'Terminated: {", ".join(killed)}', None)
            return ('failed', None, f'No process matching "{target}" found')
        except Exception as exc:
            return ('failed', None, str(exc))

    if action == 'restart_service':
        svc = str(params.get('service_name') or '').strip()
        if not _validate_service_name(svc):
            return ('failed', None,
                    'restart_service requires a valid service_name (alphanumeric/-/_)')
        if OS_NAME == 'linux':
            argv = ['systemctl', 'restart', svc]
        elif OS_NAME == 'darwin':
            argv = ['launchctl', 'restart', svc]
        elif OS_NAME == 'windows':
            # stop then start; ignore errors on stop
            subprocess.run(['sc', 'stop', svc], capture_output=True, timeout=30)
            argv = ['sc', 'start', svc]
        else:
            return ('skipped', None, f'restart_service not supported on {OS_NAME}')
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            if out.returncode == 0:
                return ('success', out.stdout.strip() or f'{svc} restarted', None)
            return ('failed', None, out.stderr.strip() or f'exit {out.returncode}')
        except FileNotFoundError:
            return ('failed', None, f'{argv[0]} not found on this system')
        except subprocess.TimeoutExpired:
            return ('failed', None, 'restart timed out after 30s')
        except Exception as exc:
            return ('failed', None, str(exc))

    # ── Static allowlisted commands ───────────────────────────────────────────
    if action in STATIC_COMMANDS:
        platform_cmds = STATIC_COMMANDS[action]
        argv = platform_cmds.get(OS_NAME) or platform_cmds.get('linux')
        if not argv:
            return ('skipped', None, f'No command defined for platform {OS_NAME}')
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            stdout = out.stdout.strip()
            stderr = out.stderr.strip()
            if out.returncode == 0:
                return ('success', stdout or f'{action} completed', None)
            # Some commands return non-zero but still succeed (e.g. purge on macOS)
            if stdout:
                return ('success', stdout, None)
            return ('failed', None, stderr or f'exit {out.returncode}')
        except FileNotFoundError:
            return ('failed', None, f'Command binary not found for {action} on {OS_NAME}')
        except subprocess.TimeoutExpired:
            return ('failed', None, f'{action} timed out after 60s')
        except Exception as exc:
            return ('failed', None, str(exc))

    return ('failed', None, f'Unknown action: {action!r}')


# ── Metrics collection ────────────────────────────────────────────────────────

def _get_disk() -> float:
    for path in ('/', 'C:\\'):
        try:
            return psutil.disk_usage(path).percent
        except Exception:
            continue
    return 0.0


def _get_temperature():
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                if entries:
                    return round(entries[0].current, 1)
    except Exception:
        pass
    return None


def _get_load_avg():
    try:
        la = psutil.getloadavg()
        return f'{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}'
    except Exception:
        return None


def collect_metrics() -> dict:
    net = psutil.net_io_counters()
    vm  = psutil.virtual_memory()
    return {
        'cpu':           round(psutil.cpu_percent(interval=0.5), 1),
        'memory':        round(vm.percent, 1),
        'memory_used':   vm.used,
        'memory_total':  vm.total,
        'disk':          round(_get_disk(), 1),
        'network_in':    net.bytes_recv,
        'network_out':   net.bytes_sent,
        'temperature':   _get_temperature(),
        'load_avg':      _get_load_avg(),
        'processes':     len(psutil.pids()),
        'uptime_secs':   int(time.time() - psutil.boot_time()),
        'timestamp':     time.time(),
    }


def collect_info() -> dict:
    return {
        'hostname':  HOSTNAME,
        'platform':  platform.platform(),
        'os':        platform.system(),
        'cpu_cores': psutil.cpu_count(logical=True),
        'cpu_model': platform.processor() or platform.machine(),
        'python':    sys.version.split()[0],
    }


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(server: str, token: str, interval: int = 3,
        api_key: str = None, org_id: str = None):
    """
    Run the agent heartbeat loop.

    New protocol: if api_key and org_id are provided, uses X-Agent-Key header
                  and POST /ingest/heartbeat on the new core_api service.
    Legacy:       falls back to token-in-body POST /agents/heartbeat (Flask).
    """
    use_new_protocol = bool(api_key and org_id)

    if use_new_protocol:
        heartbeat_url = server.rstrip('/') + '/ingest/heartbeat'
        result_url    = server.rstrip('/') + '/ingest/command-result'
    else:
        heartbeat_url = server.rstrip('/') + '/agents/heartbeat'
        result_url    = server.rstrip('/') + '/agents/{agent_id}/commands/result'

    info      = collect_info()
    agent_id  = None           # filled in from first successful heartbeat response
    errors    = 0

    print('─' * 58)
    print('  AIOps Remote Agent')
    print('─' * 58)
    print(f'  Host:          {info["hostname"]}')
    print(f'  OS:            {info["os"]}')
    print(f'  Cores:         {info["cpu_cores"]}')
    print(f'  Server:        {server}')
    print(f'  Protocol:      {"New (X-Agent-Key)" if use_new_protocol else "Legacy (token)"}')
    print(f'  Interval:      {interval}s')
    print(f'  Actions:       {"ENABLED" if ALLOW_SYSTEM_ACTIONS else "READ-ONLY (set ALLOW_SYSTEM_ACTIONS=true to enable)"}')
    print('─' * 58)
    print('  Connecting…\n')

    while True:
        try:
            metrics = collect_metrics()
            if use_new_protocol:
                resp = requests.post(
                    heartbeat_url,
                    json={'org_id': org_id, 'info': info, 'metrics': metrics},
                    headers={'X-Agent-Key': api_key},
                    timeout=10,
                )
            else:
                resp = requests.post(
                    heartbeat_url,
                    json={'token': token, 'info': info, 'metrics': metrics},
                    timeout=10,
                )

            if resp.status_code == 200:
                errors = 0
                body   = resp.json()

                # Capture agent_id from first response
                if not agent_id and body.get('agent_id'):
                    agent_id = body['agent_id']

                ts = time.strftime('%H:%M:%S')
                m  = metrics
                print(
                    f'\r  [{ts}]  '
                    f'CPU {m["cpu"]:5.1f}%  '
                    f'MEM {m["memory"]:5.1f}%  '
                    f'DISK {m["disk"]:5.1f}%  '
                    f'↑ {m["network_out"]//1024:>7} KB  '
                    f'↓ {m["network_in"]//1024:>7} KB   ',
                    end='', flush=True,
                )

                # ── Process any commands piggy-backed in the response ─────────
                commands = body.get('commands') or []
                for cmd in commands:
                    print(f'\n  [cmd] {cmd["id"]} · {cmd["action"]} '
                          f'(source: {cmd.get("source","?")})  →  executing…')

                    t0               = time.time()
                    status, res, err = execute_command(cmd)
                    elapsed          = round(time.time() - t0, 2)

                    label = ('✓' if status == 'success' else
                             '⚠' if status == 'skipped' else '✗')
                    print(f'  [cmd] {label} {status}  ({elapsed}s)'
                          + (f'  {res or err}' if (res or err) else ''))

                    # Report result back to server
                    if agent_id:
                        try:
                            requests.post(
                                result_url.format(agent_id=agent_id),
                                json={
                                    'token':  token,
                                    'cmd_id': cmd['id'],
                                    'status': status,
                                    'result': res,
                                    'error':  err,
                                },
                                timeout=10,
                            )
                        except Exception:
                            pass   # result delivery is best-effort

            elif resp.status_code == 401:
                print('\n  [agent] Token rejected. Re-generate from the admin dashboard.')
                sys.exit(1)
            elif resp.status_code == 403:
                print('\n  [agent] Token revoked by admin.')
                sys.exit(1)
            else:
                errors += 1
                print(f'\r  [{time.strftime("%H:%M:%S")}] HTTP {resp.status_code}   ',
                      end='', flush=True)

        except requests.exceptions.ConnectionError:
            errors += 1
            wait = min(interval * max(errors, 1), 60)
            print(f'\r  [{time.strftime("%H:%M:%S")}] Unreachable — retry in {wait}s…   ',
                  end='', flush=True)
            time.sleep(wait)
            continue

        except KeyboardInterrupt:
            print('\n\n  [agent] Stopped.')
            sys.exit(0)

        except Exception as exc:
            errors += 1
            print(f'\r  [{time.strftime("%H:%M:%S")}] Error: {exc}   ', end='', flush=True)

        time.sleep(interval)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AIOps Remote Agent — stream metrics and execute safe remediation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Environment variables:\n'
            '  ALLOW_SYSTEM_ACTIONS=true  Enable command execution (default: false)\n'
            '  AIOPS_SERVER               Server URL (overrides --server)\n'
            '  AIOPS_KEY                  Agent API key for new protocol (X-Agent-Key)\n'
            '  AIOPS_ORG                  Organization ID for new protocol\n\n'
            'New protocol (core_api, recommended):\n'
            '  AIOPS_SERVER=https://HOST AIOPS_KEY=<key> AIOPS_ORG=<org> python app/integrations/remote_agent.py\n\n'
            'Legacy protocol (Flask):\n'
            '  python app/integrations/remote_agent.py --server http://HOST:5000 --token abc123\n'
        ),
    )
    parser.add_argument('--server',   default=os.environ.get('AIOPS_SERVER', 'http://localhost:5000'),
                        help='AIOps backend URL')
    parser.add_argument('--token',    default='',
                        help='Legacy agent token (use AIOPS_KEY for new protocol)')
    parser.add_argument('--interval', type=int, default=3,
                        help='Heartbeat interval in seconds (default: 3)')

    args   = parser.parse_args()
    api_key = os.environ.get('AIOPS_KEY', '')
    org_id  = os.environ.get('AIOPS_ORG', '')

    if not api_key and not args.token:
        parser.error('Provide --token (legacy) or set AIOPS_KEY+AIOPS_ORG env vars (new protocol)')

    run(args.server, args.token, args.interval, api_key=api_key, org_id=org_id)
