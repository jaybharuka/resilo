/**
 * resiloApi.js — Core API client (port 8001)
 *
 * All endpoints are org-scoped: data is automatically filtered to the
 * authenticated user's org_id (read from their JWT via /auth/me).
 * The auth token is attached from localStorage on every request.
 */
import axios from 'axios';

const CORE_BASE_URL = (() => {
  try {
    const override = localStorage.getItem('aiops:coreBase');
    if (override && override.trim()) return override.trim();
  } catch {}
  const env = process.env.REACT_APP_CORE_API_URL;
  if (env && env.trim()) return env.trim();
  try {
    if (typeof window !== 'undefined' && window.location) {
      const { protocol, hostname } = window.location;
      return `${protocol}//${hostname}:8001`;
    }
  } catch {}
  return 'http://localhost:8001';
})();

const coreAxios = axios.create({
  baseURL: CORE_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach the JWT on every request
coreAxios.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem('aiops:token');
    if (token) {
      config.headers = config.headers || {};
      config.headers['Authorization'] = `Bearer ${token}`;
    }
  } catch {}
  return config;
});

// Read org_id from stored user profile (cached in localStorage as 'aiops:user')
function getOrgId() {
  try {
    const raw = localStorage.getItem('aiops:user');
    if (raw) {
      const u = JSON.parse(raw);
      return u?.org_id || null;
    }
  } catch {}
  return null;
}

// Helper: org-scoped URL prefix
function orgPath(orgId) {
  return `/api/orgs/${orgId}`;
}

// ── Browser metrics push ──────────────────────────────────────────────────────

export const resiloApi = {
  /** Push metrics collected from the user's browser / local agent to the backend. */
  pushBrowserMetrics: async (orgId, metrics) => {
    const oid = orgId || getOrgId();
    if (!oid) return;
    const res = await coreAxios.post('/api/ingest/browser-metrics', {
      org_id: oid,
      metrics,
    });
    return res.data;
  },
};

// ── Metrics ──────────────────────────────────────────────────────────────────

export const metricsApi = {
  /** Latest snapshot per agent in the org */
  getLatest: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const res = await coreAxios.get(`${orgPath(oid)}/metrics/latest`);
    return res.data;
  },

  /** Time-series snapshots for the org (optionally filtered by agentId) */
  getHistory: async (orgId, { agentId, limit = 60 } = {}) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const params = { limit };
    if (agentId) params.agent_id = agentId;
    const res = await coreAxios.get(`${orgPath(oid)}/metrics`, { params });
    return res.data;
  },
};

// ── Alerts ───────────────────────────────────────────────────────────────────

export const alertsApi = {
  list: async (orgId, { status } = {}) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const params = {};
    if (status) params.status = status;
    const res = await coreAxios.get(`${orgPath(oid)}/alerts`, { params });
    return res.data;
  },

  update: async (orgId, alertId, { status, resolved_by } = {}) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.put(`${orgPath(oid)}/alerts/${alertId}`, { status, resolved_by });
    return res.data;
  },
};

// ── Agents ───────────────────────────────────────────────────────────────────

export const agentsApi = {
  list: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const res = await coreAxios.get(`${orgPath(oid)}/agents`);
    return res.data;
  },

  create: async (orgId, label) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/agents`, { label });
    return res.data;
  },

  remove: async (orgId, agentId) => {
    const oid = orgId || getOrgId();
    await coreAxios.delete(`${orgPath(oid)}/agents/${agentId}`);
  },

  sendCommand: async (orgId, agentId, action, params = {}) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/agents/${agentId}/command`, { action, params });
    return res.data;
  },

  patch: async (orgId, agentId, body) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.patch(`${orgPath(oid)}/agents/${agentId}`, body);
    return res.data;
  },
};

// ── WMI Agentless Polling ─────────────────────────────────────────────────────

export const wmiApi = {
  list: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const res = await coreAxios.get(`${orgPath(oid)}/wmi-targets`);
    return res.data;
  },

  create: async (orgId, body) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/wmi-targets`, body);
    return res.data;
  },

  test: async (orgId, targetId) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/wmi-targets/${targetId}/test`);
    return res.data;
  },

  remove: async (orgId, targetId) => {
    const oid = orgId || getOrgId();
    await coreAxios.delete(`${orgPath(oid)}/wmi-targets/${targetId}`);
  },

  createInvite: async (orgId) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/wmi-invite`, {});
    return res.data;
  },

  pollInvite: async (orgId, inviteId) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.get(`${orgPath(oid)}/wmi-invite/${inviteId}/status`);
    return res.data;
  },
};

// ── Remediation ───────────────────────────────────────────────────────────────

export const remediationApi = {
  list: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const res = await coreAxios.get(`${orgPath(oid)}/remediation`);
    return res.data;
  },

  stats: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return null;
    const res = await coreAxios.get(`${orgPath(oid)}/remediation/stats`);
    return res.data;
  },

  trigger: async (orgId, agentId, action, params = {}) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/remediation`, { agent_id: agentId, action, params });
    return res.data;
  },
};

// ── Audit ────────────────────────────────────────────────────────────────────

export const auditApi = {
  list: async (orgId, { limit = 50 } = {}) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const res = await coreAxios.get(`${orgPath(oid)}/audit`, { params: { limit } });
    return res.data;
  },
};

// ── Org settings ──────────────────────────────────────────────────────────────

export const orgApi = {
  get: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return null;
    const res = await coreAxios.get(`/api/orgs/${oid}`);
    return res.data;
  },

  updateSettings: async (orgId, settings) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.patch(`/api/orgs/${oid}/settings`, settings);
    return res.data;
  },
};

// ── Notification Channels ─────────────────────────────────────────────────────

export const notificationChannelsApi = {
  /** List all notification channels for the org */
  list: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const res = await coreAxios.get(`${orgPath(oid)}/notification-channels`);
    return res.data;
  },

  /** Create a new channel. body: { channel_type, label?, config, enabled?, severities? } */
  create: async (orgId, body) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/notification-channels`, body);
    return res.data;
  },

  /** Update a channel */
  update: async (orgId, channelId, body) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.put(`${orgPath(oid)}/notification-channels/${channelId}`, body);
    return res.data;
  },

  /** Delete a channel */
  remove: async (orgId, channelId) => {
    const oid = orgId || getOrgId();
    await coreAxios.delete(`${orgPath(oid)}/notification-channels/${channelId}`);
  },

  /** Send a test notification to verify the channel */
  test: async (orgId, channelId) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/notification-channels/${channelId}/test`);
    return res.data;
  },
};

// ── Alert Rules ───────────────────────────────────────────────────────────────

export const alertRulesApi = {
  /** List all custom alert rules for the org */
  list: async (orgId) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const res = await coreAxios.get(`${orgPath(oid)}/alert-rules`);
    return res.data;
  },

  /** Create a rule. body: { name, metric, threshold, severity, cooldown_minutes?, enabled?, notify_channels? } */
  create: async (orgId, body) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/alert-rules`, body);
    return res.data;
  },

  /** Update a rule */
  update: async (orgId, ruleId, body) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.put(`${orgPath(oid)}/alert-rules/${ruleId}`, body);
    return res.data;
  },

  /** Delete a rule */
  remove: async (orgId, ruleId) => {
    const oid = orgId || getOrgId();
    await coreAxios.delete(`${orgPath(oid)}/alert-rules/${ruleId}`);
  },
};

// ── Notification Logs ─────────────────────────────────────────────────────────

export const notificationLogsApi = {
  /** List notification logs with optional filters */
  list: async (orgId, { channelType, notificationType, status, limit = 100 } = {}) => {
    const oid = orgId || getOrgId();
    if (!oid) return [];
    const params = { limit };
    if (channelType)      params.channel_type      = channelType;
    if (notificationType) params.notification_type  = notificationType;
    if (status)           params.status             = status;
    const res = await coreAxios.get(`${orgPath(oid)}/notification-logs`, { params });
    return res.data;
  },
};

// ── Daily Summary ─────────────────────────────────────────────────────────────

export const dailySummaryApi = {
  /** Manually trigger the daily summary for the org */
  send: async (orgId) => {
    const oid = orgId || getOrgId();
    const res = await coreAxios.post(`${orgPath(oid)}/daily-summary/send`);
    return res.data;
  },
};

// Legacy default export kept for backward compat with resiloApi imports
const legacyApi = {
  getMetrics:    () => coreAxios.get('/api/health'),   // no-op fallback
  getAlerts:     (filters = {}) => coreAxios.get(`${orgPath(getOrgId())}/alerts`, { params: filters }).catch(() => ({ data: [] })),
  getAnomalies:  () => coreAxios.get(`${orgPath(getOrgId())}/alerts`, { params: { status: 'open' } }).catch(() => ({ data: [] })),
  getRemediations: () => coreAxios.get(`${orgPath(getOrgId())}/remediation`).catch(() => ({ data: [] })),
  triggerRemediation: (actionId, data) => coreAxios.post(`${orgPath(getOrgId())}/remediation`, data),
};

export { getOrgId, CORE_BASE_URL };
export default legacyApi;
