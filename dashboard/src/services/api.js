import axios from 'axios';

// --- Direct Mode Flag ---
// When REACT_APP_DIRECT_MODE is set to '1' or 'true', the frontend will bypass
// all Node/Express proxy logic and talk straight to the Flask backend (port 5000 by default).
// This is useful when the Node layer is unreachable or you want a lighter stack.
export const DIRECT_MODE = /^(1|true)$/i.test(process.env.REACT_APP_DIRECT_MODE || '');
export const USE_MOCKS = /^(1|true)$/i.test(process.env.REACT_APP_USE_MOCKS || '');

// Determine API base URL:
// - If REACT_APP_API_BASE_URL is provided, use it.
// - Otherwise, derive from the current browser location (hostname:5000),
//   which makes the build work from localhost and LAN IPs without rebuilds.
export const API_BASE_URL = (() => {
  // Highest priority: user override stored locally (advanced networking)
  try {
    const override = (typeof window !== 'undefined') ? localStorage.getItem('aiops:apiBase') : null;
    if (override && override.trim()) return override.trim();
  } catch {}
  const env = process.env.REACT_APP_API_BASE_URL;
  if (env && env.trim()) return env.trim();
  try {
    if (typeof window !== 'undefined' && window.location) {
      const { protocol, hostname } = window.location;
      return `${protocol}//${hostname}:5000`;
    }
  } catch {}
  return 'http://localhost:5000';
})();
const inferSocketUrl = () => {
  const env = process.env.REACT_APP_SOCKET_URL;
  if (env) return env;
  try {
    const u = new URL(API_BASE_URL);
    return `${u.protocol}//${u.hostname}:3001`;
  } catch {
    return 'http://localhost:3001';
  }
};
const NODE_BASE_URL = inferSocketUrl();
// Node API client (disabled when DIRECT_MODE)
const nodeApi = !DIRECT_MODE ? axios.create({ baseURL: NODE_BASE_URL, timeout: 15000, headers: { 'Content-Type': 'application/json' } }) : null;

// Create axios instance with default config
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

let authToken = null;
let refreshToken = null;
let refreshing = false;
let refreshQueue = [];

// Helper to determine if a URL is an auth endpoint
function isAuthEndpoint(urlLike) {
  try {
    const u = new URL(urlLike, API_BASE_URL);
    return u.pathname.startsWith('/auth/');
  } catch {
    const s = String(urlLike || '');
    return s.includes('/auth/');
  }
}

function setLocal(key, val) {
  try { if (val === null || val === undefined) localStorage.removeItem(key); else localStorage.setItem(key, val); } catch {}
}
function getLocal(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

// Initialize from localStorage at module load
try { authToken = getLocal('aiops:token'); } catch {}
try { refreshToken = getLocal('aiops:refresh'); } catch {}

export function setAuthTokenOnClient(token) {
  authToken = token || null;
  if (token) setLocal('aiops:token', token); else setLocal('aiops:token', null);
}

export function setRefreshTokenOnClient(token) {
  refreshToken = token || null;
  if (token) setLocal('aiops:refresh', token); else setLocal('aiops:refresh', null);
}

// Request interceptor
api.interceptors.request.use(
  (config) => {
    console.log(`🔌 API Request: ${config.method?.toUpperCase()} ${config.url}`);
    if (authToken) {
      config.headers = config.headers || {};
      config.headers['Authorization'] = `Bearer ${authToken}`;
    }
    return config;
  },
  (error) => {
    console.error('❌ Request error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    console.log(`✅ API Response: ${response.status} ${response.config.url}`);
    return response;
  },
  async (error) => {
    const status = error?.response?.status;
    console.error('❌ Response error:', status, error.message);
    const original = error.config || {};
    // Only attempt refresh when:
    // - The response is 401
    // - It's not already a retry
    // - We are NOT calling an auth endpoint (e.g., /auth/login)
    // - We have a refresh token available on the client
    if (
      status === 401 &&
      !original.__isRetry &&
      !isAuthEndpoint(original.url || '') &&
      !!refreshToken &&
      !!authToken
    ) {
      // Try refresh flow once
      original.__isRetry = true;
      return await attemptRefreshAndReplay(original);
    }
    return Promise.reject(error);
  }
);

async function attemptRefreshAndReplay(originalConfig) {
  if (refreshing) {
    return new Promise((resolve, reject) => {
      refreshQueue.push({ resolve, reject, originalConfig });
    });
  }
  refreshing = true;
  try {
    if (!refreshToken) {
      throw new Error('missing_refresh_token');
    }
    // Prefer backend refresh using body refresh_token; fallback header-only refresh.
    const body = refreshToken ? { refresh_token: refreshToken } : {};
    const resp = await api.post('/auth/refresh', body);
    const { token: newAccess, refresh_token: newRefresh } = resp.data || resp;
    if (newAccess) {
      authToken = newAccess;
      setLocal('aiops:token', newAccess);
    }
    if (newRefresh) {
      refreshToken = newRefresh;
      setLocal('aiops:refresh', newRefresh);
    }
    // Replay queued requests
    const queued = refreshQueue.slice();
    refreshQueue = [];
    queued.forEach(({ resolve }) => {
      resolve(api(originalConfig));
    });
    return api(originalConfig);
  } catch (e) {
    // Notify global unauthorized
    try { window.dispatchEvent(new CustomEvent('aiops:unauthorized')); } catch {}
    // Flush queued with error
    const queued = refreshQueue.slice();
    refreshQueue = [];
    queued.forEach(({ reject }) => reject(e));
    return Promise.reject(e);
  } finally {
    refreshing = false;
  }
}

export const apiService = {
  // Config
  async getConfig() {
    try { const res = await api.get('/config'); return res.data; } catch (e) { return { error: e?.message || String(e) }; }
  },
  // Health check
  async checkHealth() {
    try {
      const response = await api.get('/health');
      return response.data;
    } catch (error) {
      console.error('Health check failed:', error);
      return { status: 'offline', error: error?.message || String(error) };
    }
  },

  // Get system metrics (prefers cached snapshot)
  async getSystemData() {
    try {
      const response = await api.get('/dashboard-snapshot');
      return response.data;
    } catch (error) {
      // Fallback to slower system-health
      try {
        const res2 = await api.get('/system-health');
        return res2.data;
      } catch (e2) {
        if (DIRECT_MODE) {
          console.warn('Direct mode: Flask snapshot & system-health failed; returning minimal offline state. Error:', error?.message || error);
          return { status: 'offline', last_updated: new Date().toISOString(), source: 'direct' };
        }
        console.warn('Flask system endpoints failed, trying Node /api/system ...', error?.message || error);
        // Try Node realtime API for live data
        try {
          const res = await nodeApi.get('/api/system');
          const d = res.data || {};
          return {
            cpu: d.cpu ?? 0,
            memory: d.memory ?? 0,
            disk: (d.disk ?? d.storage ?? 0),
            network_in: d.network ?? d.network_in ?? 0,
            network_out: d.network_out ?? 0,
            temperature: d.temperature ?? null,
            status: d.status === 'success' ? 'healthy' : (d.status || 'unknown'),
            uptime: d.uptime ?? null,
            active_processes: d.processes ?? d.threads ?? null,
            last_updated: d.timestamp || new Date().toISOString(),
            source: 'node'
          };
        } catch (err2) {
          console.error('Node /api/system failed:', err2?.message || err2);
          // Return mock data as last resort
          return { status: 'offline', error: 'Both Flask and Node system endpoints unavailable', last_updated: new Date().toISOString() };
        }
      }
    }
  },

  // Get AI insights
  async getAiInsights() {
    try {
      const response = await api.get('/ai-health');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch AI insights:', error);
      return [];
    }
  },

  // Get recent alerts
  async getAlerts() {
    try {
      const response = await api.get('/anomalies');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch alerts:', error);
      return [];
    }
  },

  // Devices and company stats
  async getDevices() {
    try {
      const res = await api.get('/devices');
      return res.data || [];
    } catch (error) {
      console.error('Failed to fetch devices:', error?.message || error);
      return [];
    }
  },
  async getCompanyStats() {
    try {
      const res = await api.get('/company-stats');
      return res.data || {};
    } catch (error) {
      console.warn('Failed to fetch company stats, will compute from devices if possible:', error?.message || error);
      return null;
    }
  },

  // Chat with AI
  async sendChatMessage(message, extra = {}) {
    try {
      const payload = { message, ...(extra || {}) };
      const response = await api.post('/chat', payload);
      return response.data;
    } catch (error) {
      console.error('Chat request failed:', error);
      return {
        response: "I'm currently offline, but I'll be back soon! In the meantime, check your system metrics above. 🤖",
        timestamp: new Date().toISOString(),
        source: 'fallback'
      };
    }
  },

  // Analyze text with AI
  async analyzeText(text, type = 'sentiment') {
    try {
      const response = await api.post('/analyze', { text, type });
      return response.data;
    } catch (error) {
      console.error('AI analysis failed:', error);
      return {
        result: { error: 'AI analysis unavailable' },
        timestamp: new Date().toISOString(),
        analysis_type: type
      };
    }
  },

  // Get performance data for charts
  async getPerformanceData() {
    try {
      const response = await api.get('/performance');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch performance data:', error);
      return [];
    }
  }
};

// Additional helpers aligned with Flask endpoints
export const systemApi = {
  getProcesses: async () => {
    try { return (await api.get('/processes')).data; }
    catch {
      try { return (await nodeApi.get('/api/processes')).data; }
      catch (e) { throw e; }
    }
  },
  getSystemInfo: async () => {
    try { return (await api.get('/system-info')).data; }
    catch {
      // Fallback to Node /api/system and map to the expected shape
      const d = (await nodeApi.get('/api/system')).data || {};
      const bootIso = (() => {
        try {
          const now = Date.now();
          const seconds = typeof d.uptime === 'number' ? d.uptime : null;
          if (seconds) return new Date(now - seconds * 1000).toISOString();
        } catch {}
        return null;
      })();
      return {
        platform: 'Windows',
        cpu_cores: null,
        total_memory: null,
        available_memory: null,
        free_disk: null,
        cpu_freq: null,
        boot_time: bootIso,
        load_avg: 'N/A'
      };
    }
  },
  getPredictive: async (timeframe = '1hour') => (await api.get(`/predictive-analytics?timeframe=${encodeURIComponent(timeframe)}`)).data,
};

// Authentication endpoints
export const authApi = {
  register: async ({ email, password, name, role }) => {
    return (await api.post('/auth/register', { email, password, name, role })).data;
  },
  login: async ({ email, password, role }) => {
    const res = (await api.post('/auth/login', { email, password, role })).data;
    if (res?.token) setAuthTokenOnClient(res.token);
    if (res?.refresh_token) setRefreshTokenOnClient(res.refresh_token);
    return res;
  },
  me: async () => (await api.get('/auth/me')).data,
  logout: async () => {
    try { await api.post('/auth/logout', { refresh_token: refreshToken }); } finally {
      setAuthTokenOnClient(null);
      setRefreshTokenOnClient(null);
    }
    return { ok: true };
  },
  refresh: async () => {
    const body = refreshToken ? { refresh_token: refreshToken } : {};
    const res = (await api.post('/auth/refresh', body)).data;
    if (res?.token) setAuthTokenOnClient(res.token);
    if (res?.refresh_token) setRefreshTokenOnClient(res.refresh_token);
    return res;
  },
  createInvite: async ({ role = 'employee', email, ttl_seconds } = {}) => {
    return (await api.post('/auth/invites', { role, email, ttl_seconds })).data;
  },
  redeemInvite: async ({ token, email, password, name }) => {
    return (await api.post('/auth/redeem-invite', { token, email, password, name })).data;
  },
};

// Action endpoints for system operations and AI controls
export const actionsApi = {
  // System actions
  memoryCleanup: async (options = {}) => {
    // options: { aggressive?, trimWorkingSets?, includeBrowserCache?, dryRun? }
    const payload = {
      aggressive: !!options.aggressive,
      trim_working_sets: !!options.trimWorkingSets,
      include_browser_cache: !!options.includeBrowserCache,
      dry_run: !!options.dryRun
    };
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/actions/memory-cleanup', payload)).data; } catch {}
    }
    return (await api.post('/actions/memory-cleanup', payload)).data;
  },
  diskCleanup: async (options = {}) => {
    const payload = { dry_run: !!options.dryRun };
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/actions/disk-cleanup', payload)).data; } catch {}
    }
    return (await api.post('/actions/disk-cleanup', payload)).data;
  },
  processMonitor: async () => {
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/actions/process-monitor')).data; } catch {}
    }
    return (await api.post('/actions/process-monitor')).data;
  },
  emergencyStop: async () => {
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/actions/emergency-stop', { top_cpu: true })).data; } catch {}
    }
    return (await api.post('/actions/emergency-stop', { top_cpu: true })).data;
  },

  // AI actions
  retrainModels: async () => {
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/ai/retrain')).data; } catch {}
    }
    return (await api.post('/ai/retrain')).data;
  },
  runDiagnostics: async () => {
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/ai/diagnostics')).data; } catch {}
    }
    return (await api.post('/ai/diagnostics')).data;
  },
  updateParameters: async (params = {}) => {
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/ai/update-params', params)).data; } catch {}
    }
    return (await api.post('/ai/update-params', params)).data;
  },
  exportInsights: async () => {
    if (!DIRECT_MODE) {
      try { return (await nodeApi.post('/api/ai/export-insights')).data; } catch {}
    }
    return (await api.post('/ai/export-insights')).data;
  },
};

// Integrations endpoints
export const integrationsApi = {
  testSlack: async (payload = {}) => (await api.post('/integrations/slack/test', payload)).data,
  testDiscord: async (payload = {}) => (await api.post('/integrations/discord/test', payload)).data,
};

// Jobs API for polling status/logs and building download URL
export const jobsApi = {
  get: async (jobId) => (await api.get(`/jobs/${encodeURIComponent(jobId)}`)).data,
  logs: async (jobId) => (await api.get(`/jobs/${encodeURIComponent(jobId)}/logs`)).data,
  downloadUrl: (jobId) => `${API_BASE_URL}/jobs/${encodeURIComponent(jobId)}/download`,
};

// SSE subscription for system snapshots
export function subscribeSystemSSE(onData, onStatus) {
  if (typeof window === 'undefined' || !window.EventSource) return () => {};
  try {
    const es = new EventSource(`${API_BASE_URL}/events/system`);
    if (onStatus) {
      try { es.onopen = () => onStatus('open'); } catch {}
      try { es.onerror = () => onStatus('error'); } catch {}
    }
    const handler = (ev) => {
      if (ev?.data && ev.type !== 'heartbeat') {
        try { const parsed = JSON.parse(ev.data); onData && onData(parsed); } catch {}
      }
    };
    es.onmessage = handler;
    es.addEventListener('heartbeat', () => {});
    return () => { try { es.close(); } catch {} };
  } catch (e) {
    console.warn('SSE not available:', e?.message || e);
    return () => {};
  }
}

// Real-time data service using polling
export class RealTimeService {
  constructor() {
    this.listeners = new Map();
    this.polling = false;
    this.interval = null;
    this.intervalMs = 5000; // default 5s, configurable
    this._sseUnsub = null;
    this.sseEnabled = (() => { try { return (localStorage.getItem('aiops:sse') ?? 'on') !== 'off'; } catch { return true; } })();
    this.sseConnected = false;
    // Listen for global refresh events
    try {
      this._onRefresh = () => this.refreshNow();
      window.addEventListener('aiops:refresh', this._onRefresh);
    } catch {}
  }

  // Subscribe to real-time updates
  subscribe(eventType, callback) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, []);
    }
    this.listeners.get(eventType).push(callback);

    // Start polling if not already started
    if (!this.polling) {
      this.startPolling();
    }

    // Return unsubscribe function
    return () => {
      const callbacks = this.listeners.get(eventType);
      if (callbacks) {
        const index = callbacks.indexOf(callback);
        if (index > -1) {
          callbacks.splice(index, 1);
        }
      }
    };
  }

  // Start polling for updates
  startPolling() {
    if (this.polling) return;
    
    this.polling = true;
    console.log('🔄 Starting real-time data polling...');

    // Try SSE for 'system' channel; if it pushes, we'll emit without waiting for ticks
    if (this.listeners.has('system') && !this._sseUnsub && this.sseEnabled) {
      this._sseUnsub = subscribeSystemSSE(
        (snap) => this.emit('system', snap),
        (status) => {
          const connected = status === 'open';
          if (this.sseConnected !== connected) {
            this.sseConnected = connected;
            this.emit('sse-status', { enabled: this.sseEnabled, connected: this.sseConnected });
          }
        }
      );
    }

    const tick = async () => {
      try {
        // Fetch system data
        if (this.listeners.has('system')) {
          const systemData = await apiService.getSystemData();
          this.emit('system', systemData);
        }

        // Fetch AI insights
        if (this.listeners.has('insights')) {
          const insights = await apiService.getAiInsights();
          this.emit('insights', insights);
        }

        // Fetch alerts
        if (this.listeners.has('alerts')) {
          const alerts = await apiService.getAlerts();
          this.emit('alerts', alerts);
        }

        // Fetch processes for Systems page if requested
        if (this.listeners.has('processes')) {
          try {
            const procs = await systemApi.getProcesses();
            this.emit('processes', procs);
          } catch (e) {
            // ignore errors for processes to avoid breaking other channels
          }
        }

      } catch (error) {
        console.error('Polling error:', error);
      }
    };

    // Run first tick immediately for responsiveness
    tick();
    this.interval = setInterval(tick, this.intervalMs);
  }

  // Stop polling
  stopPolling() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    this.polling = false;
    console.log('⏹️ Stopped real-time data polling');
    if (this._sseUnsub) {
      try { this._sseUnsub(); } catch {}
      this._sseUnsub = null;
    }
    if (this.sseConnected) {
      this.sseConnected = false;
      this.emit('sse-status', { enabled: this.sseEnabled, connected: false });
    }
  }

  // Emit data to listeners
  emit(eventType, data) {
    const callbacks = this.listeners.get(eventType);
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in ${eventType} callback:`, error);
        }
      });
    }
  }

  // Cleanup
  destroy() {
    this.stopPolling();
    this.listeners.clear();
    try { window.removeEventListener('aiops:refresh', this._onRefresh); } catch {}
  }

  // Trigger immediate refresh for all active channels
  async refreshNow() {
    try {
      if (this.listeners.has('system')) {
        const systemData = await apiService.getSystemData();
        this.emit('system', systemData);
      }
      if (this.listeners.has('insights')) {
        const insights = await apiService.getAiInsights();
        this.emit('insights', insights);
      }
      if (this.listeners.has('alerts')) {
        const alerts = await apiService.getAlerts();
        this.emit('alerts', alerts);
      }
      if (this.listeners.has('processes')) {
        try {
          const procs = await systemApi.getProcesses();
          this.emit('processes', procs);
        } catch (e) {}
      }
    } catch (e) {
      console.error('Immediate refresh failed:', e);
    }
  }

  // Update polling interval at runtime
  setIntervalMs(ms) {
    const next = Number(ms) || 5000;
    if (next === this.intervalMs) return;
    this.intervalMs = next;
    if (this.polling) {
      this.stopPolling();
      this.startPolling();
    }
  }
  
  // Enable/disable SSE usage
  setSSEnabled(enabled) {
    const want = !!enabled;
    if (this.sseEnabled === want) return;
    this.sseEnabled = want;
    try { localStorage.setItem('aiops:sse', want ? 'on' : 'off'); } catch {}
    // Rewire subscription if polling
    if (this.polling) {
      if (this._sseUnsub) { try { this._sseUnsub(); } catch {}; this._sseUnsub = null; }
      this.sseConnected = false;
      this.emit('sse-status', { enabled: this.sseEnabled, connected: false });
      if (this.listeners.has('system') && this.sseEnabled) {
        this._sseUnsub = subscribeSystemSSE(
          (snap) => this.emit('system', snap),
          (status) => {
            const connected = status === 'open';
            if (this.sseConnected !== connected) {
              this.sseConnected = connected;
              this.emit('sse-status', { enabled: this.sseEnabled, connected: this.sseConnected });
            }
          }
        );
      }
    }
  }

  getSSEStatus() {
    return { enabled: this.sseEnabled, connected: this.sseConnected };
  }
  
}

// Create singleton instance
export const realTimeService = new RealTimeService();

export default apiService;