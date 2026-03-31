InfraHub Page
InfraHub.js is the unified Infrastructure Command Center. It shows all connected machines — regardless of how they were added — with real-time CPU/Memory/Disk stats, online/warning/offline status, and owner attribution. Clicking any machine opens AgentDashboard.js — a full-screen diagnostic view with live animated counters, historical trend charts, alert history, and remediation buttons.

Two Ways to Add a Windows Machine
Method A — Agentless (WMI/WinRM) — No software install needed
The user only runs one PowerShell command on their machine:


Enable-PSRemoting -Force -SkipNetworkProfileCheck
Then the admin adds the machine in InfraHub by entering the hostname/IP + Windows credentials. The server then polls the machine every 30 seconds via WinRM (port 5985), runs PowerShell WMI queries, and stores the results. Nothing runs on the user's machine.

Key backend file: wmi_poller.py

Method B — Agent-Based (Push Model)
The admin generates a registration token in the dashboard. The user downloads remote_agent.py and runs it:


python remote_agent.py --server http://YOUR_SERVER:8000 --token <token>
The agent pushes metrics every 3 seconds to the server. It also polls for pending commands (remediation actions) and executes them from a safe allowlist.

Full Data Flow

USER MACHINE                     SERVER (port 8000)             DASHBOARD (port 3001)
─────────────────                ──────────────────             ─────────────────────
WMI: WinRM port 5985   ←──────── polls every 30s ──────────►   InfraHub shows card
Agent: pushes heartbeat ────────► stores MetricSnapshot ──────► InfraHub shows live data
Admin triggers command  ◄──────── queued in Agent.pending_cmds
Agent executes + reports ───────► stores result ───────────────► Shown in AgentDashboard
Anomaly Detection & Fixes
Anomalies: Alert rules are configured per-org (CPU > X%, memory > Y%, disk > Z%). Each MetricSnapshot insert evaluates rules and creates Alert records visible in the Alerts panel.
Fixes: Admin clicks a button in AgentDashboard.js → command queued → agent picks it up on next heartbeat → executes one of: clear_cache, disk_cleanup, free_memory, restart_service, kill_process → result stored and shown.
Current Gaps (things that may need wiring)
Gap	Fix Needed
InfraHub "Add Windows Machine" modal may not be connected to wmiApi.create()	Wire the submit handler in InfraHub.js
Alert rule evaluation on metric insert may not be automatic	Verify rule check runs inside the heartbeat/WMI store path
Remediation results only visible in AgentDashboard, not InfraHub cards	Surface a status badge in the card
Would you like me to investigate any of these gaps specifically, or implement any missing wiring?

The explanation above covers the full picture. Since this was an informational request rather than a code implementation task, no further plan approval is needed — the analysis is complete.

To summarize what you should focus on next if you want the full admin → metrics → anomaly → fix flow working reliably:

Verify InfraHub's "Add Windows Machine" modal is calling wmiApi.create() — look in InfraHub.js for the form submit handler
Verify alert rule evaluation fires on every metric insert in core_api.py inside the /ingest/heartbeat handler
The agent script remote_agent.py is ready to distribute to user machines right now — just generate a token and hand it to the user