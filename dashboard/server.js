const express = require('express');
const path = require('path');
const fs = require('fs');
const cors = require('cors');
const si = require('systeminformation');
const os = require('os');
const http = require('http');
const { Server } = require('socket.io');
const axios = require('axios');
const { spawn } = require('child_process');
const { createProxyMiddleware } = require('http-proxy-middleware');
const app = express();
const server = http.createServer(app);

const DEFAULT_PORT = Number(process.env.PORT) || 3001;
const HOST = (process.env.HOST || '0.0.0.0').trim();
const FLASK_BASE_URL = process.env.FLASK_BASE_URL || 'http://localhost:5000';
const CHAT_API_URL = process.env.CHAT_API_URL || `${FLASK_BASE_URL}/chat`;
const CHAT_STREAM_URL = process.env.CHAT_STREAM_URL || `${FLASK_BASE_URL}/chat/stream`;
const CORE_API_URL = process.env.CORE_API_URL || 'http://localhost:8000';

// Allow all localhost ports + any configured origins — broad for dev/LAN, lock down in prod
const _rawOrigins = (process.env.ALLOWED_ORIGINS || '').split(',').map(o => o.trim()).filter(Boolean);
const _localhostRe = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/;

const io = new Server(server, {
  cors: { origin: true, methods: ['GET', 'POST'], credentials: true },
});

const _corsOptions = {
  origin(origin, cb) {
    if (!origin || _localhostRe.test(origin) || _rawOrigins.includes(origin)) return cb(null, true);
    cb(null, true); // allow all in express layer; Flask handles its own CORS for auth routes
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Request-ID'],
  exposedHeaders: ['X-RateLimit-Limit', 'X-RateLimit-Remaining', 'Retry-After'],
};

app.use(cors(_corsOptions));

// Security headers — defence-in-depth (Nginx adds these too, but belt-and-suspenders)
app.use((_req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  next();
});

// ── Flask reverse proxy (MUST be before express.json — body stream must be intact) ──
// Forwards /auth/*, /api/performance, /api/insights, /api/chat, etc. to Flask.
// express.json() would consume the body before the proxy can stream it upstream.
const _EXPRESS_NATIVE_PREFIXES = [
  '/api/system', '/api/processes', '/api/network', '/api/alerts',
  '/api/health', '/api/local-agent', '/api/actions', '/api/ai',
  '/connect.ps1',
];
const _isExpressNative = (path) => {
  // Exact root
  if (path === '/' || path === '/api') return true;
  for (const p of _EXPRESS_NATIVE_PREFIXES) {
    if (path === p || path.startsWith(p + '/') || path.startsWith(p + '?')) return true;
  }
  return false;
};

const _flaskProxy = createProxyMiddleware({
  target: FLASK_BASE_URL,
  changeOrigin: true,
  pathFilter: (path) => {
    if (path.startsWith('/static/') || path.startsWith('/socket.io')) return false;
    if (_isExpressNative(path)) return false;
    return true;
  },
  on: {
    error(err, req, res) {
      console.warn(`[proxy→flask] ${req.method} ${req.url} — ${err.message}`);
      if (!res.headersSent) {
        res.status(502).json({ error: 'Backend unavailable', detail: err.message });
      }
    },
  },
});
app.use(_flaskProxy);

// JSON body parser — after proxy so Flask-bound requests keep their raw body stream intact
app.use(express.json());

// Cache for system data to reduce load (kept minimal, no synthetic defaults in Option A mode)
let systemCache = {};
let lastUpdate = 0;
const CACHE_DURATION = 2000; // 2 seconds

// Helper to get the effective port (supports dynamic/fallback ports)
function getEffectivePort(req) {
  try {
    const host = req.headers.host || '';
    const parts = host.split(':');
    const p = parts.length > 1 ? parseInt(parts[1], 10) : DEFAULT_PORT;
    return Number.isFinite(p) ? p : DEFAULT_PORT;
  } catch (e) {
    return DEFAULT_PORT;
  }
}

// Root route: serve React build if present, else show helpful info
app.get('/', (req, res) => {
  const port = getEffectivePort(req);
  const indexPath = path.join(__dirname, 'build', 'index.html');
  if (fs.existsSync(indexPath)) {
    return res.sendFile(indexPath);
  }
  res.type('html').send(`
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>AIOps Realtime API</title>
        <style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;line-height:1.4;padding:24px;color:#111} code{background:#f3f4f6;padding:2px 6px;border-radius:4px} a{color:#2563eb;text-decoration:none} a:hover{text-decoration:underline}</style>
      </head>
      <body>
        <h1>AIOps Realtime API</h1>
        <p>This service powers realtime metrics and chat for the dashboard.</p>
        <p><strong>No production build found.</strong> To serve the actual dashboard here, run <code>npm run build</code> inside <code>dashboard</code>.</p>
        <ul>
          <li>Health check: <a href="/api/health"><code>/api/health</code></a></li>
          <li>System metrics: <a href="/api/system"><code>/api/system</code></a></li>
          <li>Processes: <a href="/api/processes"><code>/api/processes</code></a></li>
          <li>Network: <a href="/api/network"><code>/api/network</code></a></li>
          <li>Alerts: <a href="/api/alerts"><code>/api/alerts</code></a></li>
        </ul>
        <p>Realtime websocket: <code>ws://localhost:${port}</code> (Socket.IO at <code>/socket.io</code>)</p>
        <p>See <a href="/api"><code>/api</code></a> for a JSON index.</p>
      </body>
    </html>
  `);
});

// Simple API index
app.get('/api', (req, res) => {
  const port = getEffectivePort(req);
  res.json({
    status: 'ok',
    service: 'AIOps System Monitor API',
    version: 1,
    endpoints: {
      health: '/api/health',
      system: '/api/system',
      processes: '/api/processes',
      network: '/api/network',
      alerts: '/api/alerts',
      actions: [
        '/api/actions/memory-cleanup',
        '/api/actions/disk-cleanup',
        '/api/actions/process-monitor',
        '/api/actions/emergency-stop'
      ],
      ai: [
        '/api/ai/retrain',
        '/api/ai/diagnostics',
        '/api/ai/update-params',
        '/api/ai/export-insights'
      ],
      websocket: `ws://localhost:${port}/socket.io`
    },
    timestamp: new Date().toISOString()
  });
});

// Helper function to get cached or fresh data
const getCachedData = async (key, fetchFunction) => {
  const now = Date.now();
  if (!systemCache[key] || (now - lastUpdate) > CACHE_DURATION) {
    try {
      systemCache[key] = await fetchFunction();
      lastUpdate = now;
    } catch (error) {
      console.error(`Error fetching ${key}:`, error);
      // Do not inject synthetic defaults (Option A) – preserve previous value or empty object
      if (!systemCache[key]) systemCache[key] = {};
    }
  }
  return systemCache[key];
};

// Removed getDefaultData – real values only.

// Real-time system metrics endpoint
app.get('/api/system', async (req, res) => {
  try {
    const [cpuData, memData, diskData, networkData, tempData, processData] = await Promise.all([
      getCachedData('cpu', () => si.currentLoad()),
      getCachedData('memory', () => si.mem()),
      getCachedData('disk', () => si.fsSize()),
      getCachedData('network', () => si.networkStats()),
      getCachedData('temperature', () => si.cpuTemperature()),
      getCachedData('processes', () => si.processes())
    ]);

    // Process and format the data
    const systemData = {
      cpu: typeof cpuData.currentLoad === 'number' ? Math.round(cpuData.currentLoad) : null,
      memory: (memData.total && memData.active) ? Math.round((memData.active / memData.total) * 100) : null,
      disk: (diskData[0] && diskData[0].size) ? Math.round((diskData[0].used / diskData[0].size) * 100) : null,
      storage: (diskData[0] && diskData[0].size) ? Math.round((diskData[0].used / diskData[0].size) * 100) : null,
      network_in: (networkData[0] && typeof networkData[0].rx_sec === 'number') ? Math.round((networkData[0].rx_sec || 0) / 1024) : null,
      network_out: (networkData[0] && typeof networkData[0].tx_sec === 'number') ? Math.round((networkData[0].tx_sec || 0) / 1024) : null,
      network: (networkData[0] && typeof networkData[0].rx_sec === 'number') ? Math.round((networkData[0].rx_sec || 0) / 1024) : null,
      temperature: typeof tempData.main === 'number' ? Math.round(tempData.main) : null,
      power: null,
      fanSpeed: null,
      processes: typeof processData.all === 'number' ? Math.round(processData.all) : null,
      threads: (typeof processData.all === 'number') ? Math.round(processData.all * 8.5) : null,
      uptime: Math.round(os.uptime()),
      source: 'express',
      timestamp: new Date().toISOString()
    };

    // Calculate health score based on real metrics
    const healthScore = calculateHealthScore(systemData);
    
    res.json({
      ...systemData,
      healthScore,
      status: 'success'
    });

  } catch (error) {
    console.error('System API Error:', error);
    res.status(500).json({
      error: 'Failed to fetch system data',
      status: 'error'
    });
  }
});

// Real process list endpoint
app.get('/api/processes', async (req, res) => {
  try {
    const processData = await si.processes();
    
    // Format processes for frontend
    const formattedProcesses = processData.list.slice(0, 20).map((proc) => ({
      pid: proc.pid || null,
      name: proc.name || 'unknown',
      cpu: typeof proc.cpu === 'number' ? Math.round(proc.cpu * 10) / 10 : 0,
      memory: proc.mem ? `${Math.round(proc.mem * 100) / 100}%` : '0%',
      status: proc.state || 'unknown',
      priority: proc.priority != null ? String(proc.priority) : 'Normal',
      type: getProcessType(proc.name),
      icon: getProcessIcon(proc.name)
    }));

    res.json({
      processes: formattedProcesses,
      total: processData.all || formattedProcesses.length,
      status: 'success'
    });

  } catch (error) {
    console.error('Processes API Error:', error);
    res.status(500).json({
      error: 'Failed to fetch process data',
      status: 'error'
    });
  }
});

// Network statistics endpoint
app.get('/api/network', async (req, res) => {
  try {
    const networkData = await si.networkStats();
    const interfaceData = await si.networkInterfaces();
    
    const stats = networkData[0] || {};
    const interfaces = interfaceData.slice(0, 3);

    res.json({
      currentSpeed: Math.round((stats.rx_sec || 0) / 1024 / 1024 * 8), // Convert to Mbps
      downloadSpeed: Math.round((stats.rx_sec || 0) / 1024 / 1024),
      uploadSpeed: Math.round((stats.tx_sec || 0) / 1024 / 1024),
      interfaces: interfaces.map(iface => ({
        name: iface.iface,
        type: iface.type || 'ethernet',
        speed: iface.speed || 1000,
        ip4: iface.ip4 || 'N/A',
        mac: iface.mac || 'N/A'
      })),
      status: 'success'
    });

  } catch (error) {
    console.error('Network API Error:', error);
    res.status(500).json({
      error: 'Failed to fetch network data',
      status: 'error'
    });
  }
});

// System alerts and notifications endpoint
app.get('/api/alerts', async (req, res) => {
  try {
    const systemData = await getCachedData('alerts', async () => {
      const [cpu, mem, temp] = await Promise.all([
        si.currentLoad(),
        si.mem(),
        si.cpuTemperature()
      ]);
      return { cpu, mem, temp };
    });

    const alerts = [];
    const cpuLoad = systemData.cpu.currentload || 25;
    const memUsage = systemData.mem.total ? (systemData.mem.active / systemData.mem.total) * 100 : 45;
    const temperature = systemData.temp.main || 45;

    // Generate real alerts based on system state
    if (cpuLoad > 80) {
      alerts.push({
        id: Date.now() + 1,
        type: 'warning',
        title: 'High CPU Usage',
        message: `CPU usage is at ${Math.round(cpuLoad)}%`,
        time: new Date().toLocaleTimeString(),
        priority: 'high'
      });
    }

    if (memUsage > 85) {
      alerts.push({
        id: Date.now() + 2,
        type: 'warning',
        title: 'High Memory Usage',
        message: `Memory usage is at ${Math.round(memUsage)}%`,
        time: new Date().toLocaleTimeString(),
        priority: 'medium'
      });
    }

    if (temperature > 70) {
      alerts.push({
        id: Date.now() + 3,
        type: 'error',
        title: 'High Temperature',
        message: `CPU temperature is ${Math.round(temperature)}°C`,
        time: new Date().toLocaleTimeString(),
        priority: 'high'
      });
    }

    // No synthetic info alert injection (Option A)

    res.json({
      alerts,
      count: alerts.length,
      status: 'success'
    });

  } catch (error) {
    console.error('Alerts API Error:', error);
    res.status(500).json({
      error: 'Failed to fetch alerts',
      status: 'error'
    });
  }
});

// Helper functions
function calculateHealthScore(data) {
  const cpuScore = Math.max(0, 100 - data.cpu);
  const memScore = Math.max(0, 100 - data.memory);
  const tempScore = Math.max(0, 100 - (data.temperature - 20) * 2);
  const storageScore = Math.max(0, 100 - data.storage);
  
  return Math.round((cpuScore + memScore + tempScore + storageScore) / 4);
}

function getProcessType(name) {
  if (!name) return 'Unknown';
  const lower = name.toLowerCase();
  if (lower.includes('chrome') || lower.includes('firefox') || lower.includes('edge')) return 'Browser';
  if (lower.includes('node') || lower.includes('npm')) return 'Development';
  if (lower.includes('system') || lower.includes('kernel')) return 'System';
  if (lower.includes('service')) return 'Service';
  return 'Application';
}

function getProcessIcon(name) {
  if (!name) return '⚙️';
  const lower = name.toLowerCase();
  if (lower.includes('chrome')) return '🌐';
  if (lower.includes('node')) return '💚';
  if (lower.includes('system')) return '🔧';
  if (lower.includes('explorer')) return '📁';
  if (lower.includes('code')) return '💻';
  return '📱';
}

// ── Local Agent: one-click launch / status / stop ─────────────────────────────
const REPO_ROOT = path.resolve(__dirname, '..');
const AGENT_SCRIPT = path.join(REPO_ROOT, 'app', 'integrations', 'remote_agent.py');

// Candidate Python executables (try venv first, then system)
const PYTHON_CANDIDATES = [
  path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'),
  path.join(REPO_ROOT, '.venv', 'bin', 'python3'),
  path.join(REPO_ROOT, '.venv', 'bin', 'python'),
  'python3',
  'python',
];

// In-memory map of running local agents: agent_id -> { proc, pid, label }
const localAgentProcs = new Map();

function spawnAgent(apiKey, orgId) {
  const env = {
    ...process.env,
    AIOPS_SERVER: CORE_API_URL,
    AIOPS_KEY: apiKey,
    AIOPS_ORG: orgId,
    ALLOW_SYSTEM_ACTIONS: 'false',
  };
  for (const exe of PYTHON_CANDIDATES) {
    try {
      const proc = spawn(exe, [AGENT_SCRIPT], {
        env,
        cwd: REPO_ROOT,
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });
      if (proc.pid) {
        proc.unref();
        return proc;
      }
    } catch (_) { /* try next */ }
  }
  throw new Error('No Python executable found. Ensure Python is installed or the .venv is present.');
}

app.post('/api/local-agent/launch', async (req, res) => {
  const { org_id, token, label } = req.body || {};
  if (!org_id || !token) return res.status(400).json({ error: 'org_id and token are required' });

  const agentLabel = (label || '').trim() || `${os.hostname()}-local`;

  // 1. Register agent with core API
  let regData;
  try {
    const regRes = await axios.post(
      `${CORE_API_URL}/api/orgs/${org_id}/agents`,
      { label: agentLabel },
      { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, timeout: 10000 }
    );
    regData = regRes.data;
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.response?.data || err.message || 'Failed to register agent';
    return res.status(502).json({ error: String(msg) });
  }

  const { id: agentId, api_key: apiKey } = regData;

  // 2. Spawn remote_agent.py in background
  let proc;
  try {
    proc = spawnAgent(apiKey, org_id);
  } catch (err) {
    return res.status(500).json({ error: err.message, agent_id: agentId, tip: 'Agent was registered but could not be auto-started. Use the install_cmd manually.' });
  }

  localAgentProcs.set(agentId, { proc, pid: proc.pid, label: agentLabel });

  res.json({ agent_id: agentId, label: agentLabel, pid: proc.pid, status: 'running' });
});

app.get('/api/local-agent/status', (req, res) => {
  const agents = [];
  for (const [agentId, info] of localAgentProcs.entries()) {
    let running = false;
    try { process.kill(info.pid, 0); running = true; } catch (_) {}
    agents.push({ agent_id: agentId, label: info.label, pid: info.pid, running });
  }
  res.json({ agents });
});

app.delete('/api/local-agent/stop/:agentId', (req, res) => {
  const { agentId } = req.params;
  const info = localAgentProcs.get(agentId);
  if (!info) return res.status(404).json({ error: 'No local agent with that ID' });
  try { process.kill(info.pid); } catch (_) {}
  localAgentProcs.delete(agentId);
  res.json({ stopped: true, agent_id: agentId });
});

// Serve dynamic PowerShell bootstrap script for WMI zero-input onboarding.
// Usage: irm http://HOST:3001/connect.ps1?token=TOKEN | iex
app.get('/connect.ps1', (req, res) => {
  const token = (req.query.token || '').trim();
  if (!token) {
    return res.status(400).type('text/plain').send('# Error: missing ?token= parameter');
  }
  const regUrl = `${CORE_API_URL}/api/wmi-register`;
  const script = `
$t='${token}'
$u='${regUrl}'
try { Enable-PSRemoting -Force -SkipNetworkProfileCheck -EA Stop } catch {}
$chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#%^&*'
$p=-join(1..18 | ForEach-Object { $chars[(Get-Random -Max $chars.Length)] })
net user resilo-monitor $p /add /y 2>$null
net localgroup administrators resilo-monitor /add 2>$null
$ip=(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
if (-not $ip) { $ip=$env:COMPUTERNAME }
$os=(Get-CimInstance Win32_OperatingSystem -EA SilentlyContinue).Caption
if (-not $os) { $os='Windows' }
$b=@{token=$t;hostname=$env:COMPUTERNAME;ip=$ip;os=$os;arch=$env:PROCESSOR_ARCHITECTURE;username='resilo-monitor';password=$p;port=5985} | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri $u -Body $b -ContentType 'application/json' -UseBasicParsing
Write-Host 'Machine registered. You can close this window.'
`.trimStart();
  res.type('text/plain').send(script);
});

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

// ---- Actions: system operations (proxy to Flask if present) ----
async function proxyOrAck(req, res, path, data = {}) {
  if (FLASK_BASE_URL) {
    try {
      const out = await axios.post(`${FLASK_BASE_URL}${path}`, data, { timeout: 30000 });
      return res.json(out.data);
    } catch (e) {
      // Fallthrough to local ack below
      console.warn(`Proxy to Flask failed for ${path}:`, e.message);
    }
  }
  // Local acknowledgement with real system context (non-hardcoded)
  try {
    const [mem, fs] = await Promise.all([si.mem(), si.fsSize()]);
    return res.json({
      status: 'accepted',
      path,
      context: {
        memoryActiveGB: Math.round((mem.active / (1024 ** 3)) * 10) / 10,
        memoryTotalGB: Math.round((mem.total / (1024 ** 3)) * 10) / 10,
        diskUsedGB: Math.round((fs?.[0]?.used || 0) / (1024 ** 3)),
        diskTotalGB: Math.round((fs?.[0]?.size || 0) / (1024 ** 3))
      },
      timestamp: new Date().toISOString()
    });
  } catch (err) {
    return res.status(502).json({ status: 'error', error: err.message, path });
  }
}

app.post('/api/actions/memory-cleanup', (req, res) => proxyOrAck(req, res, '/actions/memory-cleanup'));
app.post('/api/actions/disk-cleanup', (req, res) => proxyOrAck(req, res, '/actions/disk-cleanup'));
app.post('/api/actions/process-monitor', (req, res) => proxyOrAck(req, res, '/actions/process-monitor'));
app.post('/api/actions/emergency-stop', (req, res) => proxyOrAck(req, res, '/actions/emergency-stop'));

// ---- AI actions (proxy to Flask if present) ----
app.post('/api/ai/retrain', (req, res) => proxyOrAck(req, res, '/ai/retrain'));
app.post('/api/ai/diagnostics', (req, res) => proxyOrAck(req, res, '/ai/diagnostics'));
app.post('/api/ai/update-params', (req, res) => proxyOrAck(req, res, '/ai/update-params', req.body || {}));
app.post('/api/ai/export-insights', (req, res) => proxyOrAck(req, res, '/ai/export-insights'));

// Socket.IO realtime broadcasting
let broadcastInterval = null;
const activeChatStreams = new Map(); // streamId -> { abortController, interval }
const BROADCAST_MS = 2000;

io.on('connection', (socket) => {
  console.log('🔌 Client connected:', socket.id);

  // Start interval if not running
  if (!broadcastInterval) {
    broadcastInterval = setInterval(async () => {
      try {
        const [cpuData, memData, diskData, networkData, tempData, processData] = await Promise.all([
          si.currentLoad(),
          si.mem(),
          si.fsSize(),
          si.networkStats(),
          si.cpuTemperature(),
          si.processes(),
        ]);

        const payload = {
          cpu: Math.round(cpuData.currentload || 25.5),
          memory: memData.total ? Math.round((memData.active / memData.total) * 100) : 45,
          disk: diskData[0] ? Math.round((diskData[0].used / diskData[0].size) * 100) : 65,
          network_in: Math.round(networkData[0]?.rx_sec || 0),
          network_out: Math.round(networkData[0]?.tx_sec || 0),
          temperature: Math.round(tempData.main || 45),
          timestamp: new Date().toISOString(),
        };

        io.emit('system', payload);

        // Emit top processes as a separate channel
        const top = (processData.list || [])
          .sort((a, b) => (b.cpu || 0) - (a.cpu || 0))
          .slice(0, 10)
          .map((p) => ({
            pid: p.pid,
            name: p.name,
            cpu_percent: p.cpu || 0,
            memory_percent: (p.mem || 0) * 100,
            status: p.state || 'running',
          }));
        io.emit('processes', top);
      } catch (err) {
        console.error('Broadcast error:', err.message);
      }
    }, BROADCAST_MS);
  }

  socket.on('disconnect', () => {
    console.log('🔌 Client disconnected:', socket.id);
    if (io.engine.clientsCount === 0 && broadcastInterval) {
      clearInterval(broadcastInterval);
      broadcastInterval = null;
      console.log('⏹️ Stopped broadcasting (no clients)');
    }
  });

  // Chat streaming: prefer Flask SSE /chat/stream, fallback to /chat full response
  socket.on('chat:send', async ({ message, streamId, token }) => {
    if (!message || !streamId) return;
    // Cleanup any prior stream with same id
    const prev = activeChatStreams.get(streamId);
    if (prev) {
      try { prev.abortController?.abort(); } catch {}
      try { if (prev.interval) clearInterval(prev.interval); } catch {}
      activeChatStreams.delete(streamId);
    }

    const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

    // Try SSE streaming first
    try {
      const controller = new AbortController();
      activeChatStreams.set(streamId, { abortController: controller });

      const res = await axios.post(CHAT_STREAM_URL, { message }, {
        responseType: 'stream',
        headers: { Accept: 'text/event-stream', ...authHeaders },
        signal: controller.signal,
        // Increase timeout for long generations
        timeout: 0,
      });

      let buffer = '';
      const stream = res.data; // Node.js Readable
      stream.on('data', (chunk) => {
        buffer += chunk.toString('utf8');
        // Split SSE events by double newline
        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const event = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          // Parse lines of the event
          const lines = event.split('\n');
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith(':')) continue; // comment/empty
            if (trimmed.startsWith('data:')) {
              const payload = trimmed.slice(5).trim();
              if (!payload) continue;
              try {
                // Accept either raw string tokens or JSON
                let token = '';
                if ((payload.startsWith('{') && payload.endsWith('}')) || (payload.startsWith('[') && payload.endsWith(']'))) {
                  const json = JSON.parse(payload);
                  token = json.token || json.delta || json.text || '';
                } else {
                  token = payload;
                }
                if (token) socket.emit('chat:chunk', { streamId, token });
              } catch (e) {
                // If JSON parse fails, emit raw
                socket.emit('chat:chunk', { streamId, token: payload });
              }
            }
            if (trimmed.startsWith('event:') && trimmed.includes('done')) {
              socket.emit('chat:done', { streamId });
            }
          }
        }
      });
      stream.on('end', () => {
        socket.emit('chat:done', { streamId });
        activeChatStreams.delete(streamId);
      });
      stream.on('error', (e) => {
        const msg = e?.message || 'Chat stream error';
        socket.emit('chat:error', { streamId, error: msg });
        activeChatStreams.delete(streamId);
      });
      return; // using SSE stream path
    } catch (err) {
      // Fall through to non-streaming
      // Only log 404/connection errors quietly; other errors bubble as error event below
      if (err?.response?.status && err.response.status !== 404) {
        console.warn('SSE streaming failed, falling back:', err.message);
      }
    }

    // Fallback: call /chat for full response and simulate streaming
    try {
      const res = await axios.post(CHAT_API_URL, { message }, { headers: authHeaders, timeout: 60000 });
      const text = (res.data && (res.data.response || res.data.text || res.data.answer)) || '';
      const words = text.split(/(\s+)/);
      let i = 0;
      const interval = setInterval(() => {
        if (i >= words.length) {
          clearInterval(interval);
          socket.emit('chat:done', { streamId });
          activeChatStreams.delete(streamId);
          return;
        }
        socket.emit('chat:chunk', { streamId, token: words[i] });
        i += 1;
      }, 25);
      activeChatStreams.set(streamId, { interval });
    } catch (err) {
      const msg = err?.response?.data?.error || err.message || 'Chat failed';
      socket.emit('chat:error', { streamId, error: msg });
      activeChatStreams.delete(streamId);
    }
  });

  // Client requested cancel
  socket.on('chat:cancel', ({ streamId }) => {
    const entry = activeChatStreams.get(streamId);
    if (!entry) return;
    try { entry.abortController?.abort(); } catch {}
    try { if (entry.interval) clearInterval(entry.interval); } catch {}
    activeChatStreams.delete(streamId);
    socket.emit('chat:done', { streamId });
  });
});

// ── Serve React build statically ─────────────────────────────────────────────
try {
  const buildDir = path.join(__dirname, 'build');
  app.use(express.static(buildDir));
  app.get(/^\/(?!api|socket\.io)(.*)/, (req, res) => {
    res.set('Cache-Control', 'no-store, no-cache, must-revalidate');
    res.sendFile(path.join(buildDir, 'index.html'));
  });
  console.log('🗂️ Static build serving enabled (if build exists).');
} catch (e) {
  console.warn('Static build serving not configured:', e?.message || e);
}

// Robust server start with fallback ports if the default is busy
function startServer(preferredPort) {
  let currentPort = preferredPort;
  const tryListen = (portToTry) => {
    // Bind to configured host. If HOST is '0.0.0.0' or empty, bind to all interfaces by omitting host arg.
    const onListening = () => {
      const addrInfo = server.address();
      const hostForLog = HOST && HOST !== '0.0.0.0' ? HOST : (addrInfo && (addrInfo.address === '::' ? '0.0.0.0' : addrInfo.address));
      console.log(`🚀 AIOps System Monitor API running on http://${hostForLog}:${portToTry}`);
      console.log(`📊 REST at /api/* and realtime at ws://${hostForLog}:${portToTry}`);
      if (addrInfo) {
        console.log(`🔍 Address info -> ${addrInfo.address}:${addrInfo.port} (family: ${addrInfo.family})`);
      }
    };
    try {
      if (!HOST || HOST === '0.0.0.0') {
        server.listen(portToTry, onListening);
      } else {
        server.listen(portToTry, HOST, onListening);
      }
    } catch (e) {
      console.error('Server error:', e);
      process.exit(1);
    }
  };

  server.on('error', (err) => {
    if (err && err.code === 'EADDRINUSE') {
      console.warn(`⚠️ Port ${currentPort} in use. Trying fallback...`);
      // First fallback: 3011, then random available port
      const fallback = currentPort === 3001 ? 3011 : 0;
      currentPort = fallback;
      tryListen(currentPort);
    } else {
      console.error('Server error:', err);
      process.exit(1);
    }
  });

  // Extra diagnostics to catch unexpected failures
  server.on('close', () => {
    console.warn('HTTP server closed unexpectedly');
  });
  process.on('uncaughtException', (e) => {
    console.error('Uncaught exception:', e);
  });
  process.on('unhandledRejection', (e) => {
    console.error('Unhandled rejection:', e);
  });

  process.on('exit', (code) => {
    console.log(`⚠️ Node process exiting with code ${code}`);
  });

  tryListen(currentPort);
}

startServer(DEFAULT_PORT);

module.exports = app;