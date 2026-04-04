import React, { useState, useEffect, useCallback, useRef } from 'react';
import { userApi } from '../services/api';
import {
  agentsApi, metricsApi, alertsApi, alertRulesApi,
  notificationChannelsApi, notificationLogsApi, dailySummaryApi,
  getOrgId,
} from '../services/resiloApi';
import { useAuth } from '../context/AuthContext';
import {
  Server, Users, RefreshCw, CheckCircle2, AlertTriangle,
  WifiOff, Activity, ChevronDown, ChevronUp, Clock, Circle,
  Bell, BellOff, Mail, Hash, Send, Trash2, Plus, Pencil,
  CheckCheck, X, Shield, BarChart2, Layers,
  ToggleLeft, ToggleRight, Eye, EyeOff,
} from 'lucide-react';

// ── Design tokens ─────────────────────────────────────────────────────────────
const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };
const UI      = { fontFamily: "'Outfit', sans-serif" };

const C = {
  online:   '#2DD4BF',
  warning:  '#F59E0B',
  offline:  '#6B6357',
  critical: '#F87171',
  info:     '#60A5FA',
  text:     '#F5F0E8',
  sub:      '#A89F8C',
  muted:    '#6B6357',
  border:   'rgba(42,40,32,0.9)',
  panel:    'rgb(22,20,16)',
  row:      'rgba(42,40,32,0.18)',
  rowHov:   'rgba(42,40,32,0.38)',
  input:    'rgba(42,40,32,0.55)',
  accent:   '#2DD4BF',
};

const PANEL = {
  background:   C.panel,
  border:       `1px solid ${C.border}`,
  borderRadius: '12px',
  boxShadow:    '0 4px 24px rgba(0,0,0,0.3)',
};

const SEVERITY_COLOR = {
  critical: C.critical,
  high:     C.warning,
  medium:   '#FBBF24',
  low:      C.online,
  info:     C.info,
};

const SEVERITY_EMOJI = {
  critical: '🔴',
  high:     '🟠',
  medium:   '🟡',
  low:      '🟢',
  info:     'ℹ️',
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function deriveStatus(lastSeen) {
  if (!lastSeen) return 'offline';
  const diff = (Date.now() - new Date(lastSeen).getTime()) / 1000;
  if (diff <= 30)  return 'online';
  if (diff <= 120) return 'warning';
  return 'offline';
}

function relativeTime(ts) {
  if (!ts) return 'never';
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 5)    return 'just now';
  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function metricColor(val) {
  if (val == null) return C.muted;
  if (val > 80) return C.critical;
  if (val > 60) return C.warning;
  return C.online;
}

function fmtDate(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtDateTime(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function getCurrentUser() {
  try {
    const raw = localStorage.getItem('aiops:user');
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

// ── Primitive components ──────────────────────────────────────────────────────

function Skeleton({ width = '100%', height = 14, radius = 4 }) {
  return (
    <div className="animate-pulse" style={{
      width, height, borderRadius: radius,
      background: 'rgba(42,40,32,0.5)', display: 'inline-block',
    }} />
  );
}

function SeverityBadge({ severity }) {
  const color = SEVERITY_COLOR[severity] || C.sub;
  return (
    <span style={{
      ...MONO, fontSize: '9px', letterSpacing: '0.08em',
      color, background: `${color}18`,
      padding: '2px 7px', borderRadius: 10,
    }}>
      {SEVERITY_EMOJI[severity]} {(severity || 'unknown').toUpperCase()}
    </span>
  );
}

function MetricBadge({ metric }) {
  const MAP = { cpu: C.critical, memory: C.warning, disk: C.info };
  const color = MAP[metric] || C.sub;
  return (
    <span style={{
      ...MONO, fontSize: '9px', letterSpacing: '0.08em',
      color, background: `${color}18`,
      padding: '2px 7px', borderRadius: 10,
    }}>
      {(metric || '').toUpperCase()}
    </span>
  );
}

function RoleBadge({ role }) {
  const cfg = {
    admin:    { color: C.critical, bg: `${C.critical}14` },
    manager:  { color: C.warning,  bg: `${C.warning}14`  },
    employee: { color: C.online,   bg: `${C.online}14`   },
  }[role?.toLowerCase()] || { color: C.sub, bg: `${C.sub}14` };
  return (
    <span style={{
      ...MONO, fontSize: '9px', letterSpacing: '0.08em',
      color: cfg.color, background: cfg.bg,
      padding: '2px 7px', borderRadius: 10,
    }}>
      {(role || 'USER').toUpperCase()}
    </span>
  );
}

function StatCard({ icon: Icon, label, value, color, loading }) {
  return (
    <div style={{ ...PANEL, padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '14px', flex: 1, minWidth: 0 }}>
      <div style={{
        width: 40, height: 40, borderRadius: '10px',
        background: `${color}14`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={18} color={color} />
      </div>
      <div style={{ minWidth: 0 }}>
        {loading ? <Skeleton width={32} height={22} radius={4} /> : (
          <div style={{ ...DISPLAY, fontSize: '1.9rem', color: C.text, lineHeight: 1 }}>{value}</div>
        )}
        <div style={{ ...MONO, fontSize: '10px', color: C.muted, letterSpacing: '0.08em', marginTop: 3 }}>{label}</div>
      </div>
    </div>
  );
}

function MetricBar({ label, value, metric }) {
  const color = metricColor(value);
  const pct = value != null ? Math.min(100, Math.max(0, value)) : 0;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ ...MONO, fontSize: '9px', color: C.muted, letterSpacing: '0.08em' }}>{label}</span>
        <span style={{ ...MONO, fontSize: '11px', color: value != null ? C.sub : C.muted }}>
          {value != null ? `${value.toFixed(1)}%` : 'N/A'}
        </span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: 'rgba(42,40,32,0.8)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct}%`, background: color, borderRadius: 2,
          transition: 'width 0.6s ease',
        }} />
      </div>
    </div>
  );
}

function AgentCard({ agent, users = [] }) {
  const [expanded, setExpanded] = useState(false);
  const status = deriveStatus(agent.last_seen);
  const m = agent.metrics || {};
  const statusColor = status === 'online' ? C.online : status === 'warning' ? C.warning : C.offline;
  const StatusIcon  = status === 'online' ? CheckCircle2 : status === 'warning' ? AlertTriangle : WifiOff;
  const owner = users.find(u => u.id === agent.owner_user_id);
  const extraKeys = Object.entries(m).filter(([k]) =>
    !['agent_id','cpu','memory','disk','cpu_percent','memory_percent','disk_percent','timestamp','id'].includes(k)
    && typeof m[k] === 'number'
  );
  const cpu  = m.cpu  ?? m.cpu_percent  ?? null;
  const mem  = m.memory ?? m.memory_percent ?? null;
  const disk = m.disk ?? m.disk_percent ?? null;

  return (
    <div style={{ ...PANEL, display: 'flex', flexDirection: 'column', overflow: 'hidden', transition: 'box-shadow 0.2s' }}>
      <div style={{
        padding: '14px 16px', borderBottom: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <StatusIcon size={15} color={statusColor} style={{ flexShrink: 0 }} />
          <div style={{ minWidth: 0 }}>
            <span style={{ ...UI, fontWeight: 600, fontSize: '14px', color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
              {agent.label || agent.id}
            </span>
            {owner && (
              <span style={{ ...MONO, fontSize: '9px', color: C.muted }}>
                {owner.full_name || owner.username}
              </span>
            )}
          </div>
        </div>
        <span style={{
          ...MONO, fontSize: '9px', letterSpacing: '0.08em',
          color: statusColor, background: `${statusColor}14`,
          padding: '2px 7px', borderRadius: 10, flexShrink: 0,
        }}>
          {status.toUpperCase()}
        </span>
      </div>
      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <MetricBar label="CPU"    value={cpu}  metric="cpu"    />
        <MetricBar label="MEMORY" value={mem}  metric="memory" />
        <MetricBar label="DISK"   value={disk} metric="disk"   />
      </div>
      <div style={{
        padding: '10px 16px', borderTop: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <Clock size={11} color={C.muted} />
          <span style={{ ...MONO, fontSize: '10px', color: C.muted }}>{relativeTime(agent.last_seen)}</span>
        </div>
        {extraKeys.length > 0 && (
          <button onClick={() => setExpanded(e => !e)} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 3, color: C.sub, padding: 0,
          }}>
            <span style={{ ...MONO, fontSize: '9px' }}>{expanded ? 'LESS' : 'MORE'}</span>
            {expanded ? <ChevronUp size={12} color={C.sub} /> : <ChevronDown size={12} color={C.sub} />}
          </button>
        )}
      </div>
      {expanded && extraKeys.length > 0 && (
        <div style={{
          padding: '12px 16px', borderTop: `1px solid ${C.border}`,
          background: 'rgba(42,40,32,0.15)',
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px',
        }}>
          {extraKeys.map(([k, v]) => (
            <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span style={{ ...MONO, fontSize: '9px', color: C.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {k.replace(/_/g, ' ')}
              </span>
              <span style={{ ...MONO, fontSize: '11px', color: C.sub }}>
                {typeof v === 'number' ? v.toFixed(v % 1 !== 0 ? 1 : 0) : String(v)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AgentSkeleton() {
  return (
    <div style={{ ...PANEL, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Skeleton width="55%" height={14} /><Skeleton width="18%" height={14} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Skeleton width="100%" height={4} />
        <Skeleton width="100%" height={4} />
        <Skeleton width="100%" height={4} />
      </div>
      <Skeleton width="30%" height={10} />
    </div>
  );
}

function UserRow({ user }) {
  const initials  = (user.full_name || user.username || '?').charAt(0).toUpperCase();
  const roleColor = { admin: C.critical, manager: C.warning, employee: C.online }[user.role?.toLowerCase()] || C.sub;
  const isActive  = user.is_active !== false;
  return (
    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
      <td style={{ padding: '11px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8,
            background: `${roleColor}14`, color: roleColor,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            ...MONO, fontSize: '13px', fontWeight: 700, flexShrink: 0,
          }}>{initials}</div>
          <div>
            <div style={{ ...UI, fontSize: '13px', fontWeight: 500, color: C.text }}>{user.full_name || user.username}</div>
            <div style={{ ...MONO, fontSize: '10px', color: C.muted }}>{user.email}</div>
          </div>
        </div>
      </td>
      <td style={{ padding: '11px 8px' }}><RoleBadge role={user.role} /></td>
      <td style={{ padding: '11px 8px', textAlign: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, justifyContent: 'center' }}>
          <Circle size={6} fill={isActive ? C.online : C.muted} color="transparent" />
          <span style={{ ...MONO, fontSize: '10px', color: isActive ? C.online : C.muted }}>
            {isActive ? 'ACTIVE' : 'INACTIVE'}
          </span>
        </div>
      </td>
      <td style={{ padding: '11px 0', textAlign: 'right' }}>
        <span style={{ ...MONO, fontSize: '10px', color: C.muted }}>{fmtDate(user.created_at)}</span>
      </td>
    </tr>
  );
}

// ── Tab navigation ────────────────────────────────────────────────────────────

const TABS = [
  { id: 'fleet',         label: 'FLEET',         icon: Server   },
  { id: 'alerts',        label: 'ALERTS',         icon: AlertTriangle },
  { id: 'notifications', label: 'NOTIFICATIONS',  icon: Bell     },
  { id: 'users',         label: 'USERS',          icon: Users,  adminOnly: true },
];

function TabNav({ active, onChange, isAdmin, alertCount = 0 }) {
  return (
    <div style={{ display: 'flex', gap: 2, borderBottom: `1px solid ${C.border}`, paddingBottom: 0 }}>
      {TABS.filter(t => !t.adminOnly || isAdmin).map(t => {
        const isActive = active === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            style={{
              background:   'none',
              border:       'none',
              borderBottom: isActive ? `2px solid ${C.accent}` : '2px solid transparent',
              padding:      '10px 18px',
              cursor:       'pointer',
              display:      'flex', alignItems: 'center', gap: 6,
              color:        isActive ? C.accent : C.sub,
              transition:   'color 0.15s',
              position:     'relative',
            }}
          >
            <t.icon size={13} />
            <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.08em' }}>{t.label}</span>
            {t.id === 'alerts' && alertCount > 0 && (
              <span style={{
                ...MONO, fontSize: '8px',
                background: C.critical, color: '#fff',
                borderRadius: 10, padding: '1px 5px', marginLeft: 2,
              }}>
                {alertCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Panel header ──────────────────────────────────────────────────────────────
function PanelHeader({ icon: Icon, iconColor, title, count, countColor, action }) {
  return (
    <div style={{
      padding: '14px 20px', borderBottom: `1px solid ${C.border}`,
      display: 'flex', alignItems: 'center', gap: 10,
    }}>
      <Icon size={15} color={iconColor || C.online} />
      <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: C.sub }}>{title}</span>
      {count != null && (
        <span style={{
          ...MONO, fontSize: '9px',
          color: countColor || C.online, background: `${countColor || C.online}14`,
          padding: '2px 8px', borderRadius: 10, marginLeft: 'auto',
        }}>
          {count}
        </span>
      )}
      {action && <div style={{ marginLeft: count != null ? 8 : 'auto' }}>{action}</div>}
    </div>
  );
}

// ── Btn ───────────────────────────────────────────────────────────────────────
function Btn({ children, onClick, color = C.accent, disabled, small, danger, outline }) {
  const bg     = danger ? C.critical : outline ? 'transparent' : color;
  const border = danger ? C.critical : color;
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background:   outline ? 'transparent' : `${bg}18`,
        border:       `1px solid ${border}40`,
        borderRadius: 8,
        padding:      small ? '4px 10px' : '6px 14px',
        cursor:       disabled ? 'not-allowed' : 'pointer',
        display:      'flex', alignItems: 'center', gap: 5,
        color:        danger ? C.critical : outline ? C.sub : color,
        opacity:      disabled ? 0.5 : 1,
        transition:   'background 0.15s',
        ...MONO, fontSize: small ? '9px' : '10px',
        whiteSpace:   'nowrap',
      }}
    >
      {children}
    </button>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function Modal({ title, onClose, children, wide }) {
  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
      padding: 16,
    }}>
      <div style={{
        ...PANEL,
        width: '100%', maxWidth: wide ? 640 : 480,
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        <div style={{
          padding: '14px 20px', borderBottom: `1px solid ${C.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ ...MONO, fontSize: '11px', color: C.sub, letterSpacing: '0.1em' }}>{title}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.muted, padding: 0 }}>
            <X size={16} color={C.muted} />
          </button>
        </div>
        <div style={{ padding: '20px' }}>{children}</div>
      </div>
    </div>
  );
}

function Field({ label, children, hint }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ ...MONO, fontSize: '9px', color: C.sub, letterSpacing: '0.08em' }}>{label}</label>
      {children}
      {hint && <span style={{ ...MONO, fontSize: '9px', color: C.muted }}>{hint}</span>}
    </div>
  );
}

const INPUT_STYLE = {
  background: C.input,
  border: `1px solid ${C.border}`,
  borderRadius: 8,
  padding: '8px 12px',
  color: C.text,
  ...UI, fontSize: '13px',
  width: '100%',
  boxSizing: 'border-box',
  outline: 'none',
};

const SELECT_STYLE = { ...INPUT_STYLE };

// ── Alert Rules Panel ─────────────────────────────────────────────────────────
const BLANK_RULE = {
  name: '', metric: 'cpu', threshold: 85, severity: 'high',
  cooldown_minutes: 15, enabled: true, agent_id: null, notify_channels: null,
};

function AlertRulesPanel({ rules, agents, loading, onRefresh, orgId }) {
  const [modal, setModal]   = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm]     = useState(BLANK_RULE);
  const [saving, setSaving] = useState(false);
  const [err, setErr]       = useState('');

  function openCreate() { setEditing(null); setForm(BLANK_RULE); setErr(''); setModal(true); }
  function openEdit(r) { setEditing(r); setForm({ ...r }); setErr(''); setModal(true); }

  async function handleSave() {
    if (!form.name.trim()) { setErr('Name is required.'); return; }
    if (form.threshold <= 0 || form.threshold > 100) { setErr('Threshold must be 1–100.'); return; }
    setSaving(true); setErr('');
    try {
      if (editing) {
        await alertRulesApi.update(orgId, editing.id, form);
      } else {
        await alertRulesApi.create(orgId, form);
      }
      setModal(false);
      onRefresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this alert rule?')) return;
    try { await alertRulesApi.remove(orgId, id); onRefresh(); }
    catch { alert('Delete failed.'); }
  }

  async function handleToggle(r) {
    try { await alertRulesApi.update(orgId, r.id, { enabled: !r.enabled }); onRefresh(); }
    catch { alert('Update failed.'); }
  }

  return (
    <>
      <div style={PANEL}>
        <PanelHeader
          icon={Shield} iconColor={C.warning} title="ALERT RULES"
          count={`${rules.length} RULE${rules.length !== 1 ? 'S' : ''}`} countColor={C.warning}
          action={
            <Btn onClick={openCreate} color={C.warning} small>
              <Plus size={10} /> ADD RULE
            </Btn>
          }
        />
        <div style={{ padding: '4px 20px 20px', overflowX: 'auto' }}>
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 16 }}>
              {[1,2,3].map(i => <Skeleton key={i} width="100%" height={36} radius={6} />)}
            </div>
          ) : rules.length === 0 ? (
            <div style={{ padding: '40px 0', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
              <Shield size={28} color={C.muted} />
              <span style={{ ...MONO, fontSize: '11px', color: C.muted }}>NO ALERT RULES CONFIGURED</span>
              <span style={{ fontSize: '12px', color: C.muted }}>Add rules to trigger alerts when metrics exceed thresholds.</span>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
              <thead>
                <tr>
                  {['NAME','METRIC','THRESHOLD','SEVERITY','COOLDOWN','SCOPE','ENABLED',''].map((h, i) => (
                    <th key={h+i} style={{
                      ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: C.muted,
                      padding: '10px 8px', borderBottom: `1px solid ${C.border}`,
                      textAlign: 'left', fontWeight: 500, whiteSpace: 'nowrap',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rules.map(r => (
                  <tr key={r.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td style={{ padding: '10px 8px', ...UI, fontSize: '13px', color: C.text, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</td>
                    <td style={{ padding: '10px 8px' }}><MetricBadge metric={r.metric} /></td>
                    <td style={{ padding: '10px 8px', ...MONO, fontSize: '11px', color: C.sub }}>≥{r.threshold}%</td>
                    <td style={{ padding: '10px 8px' }}><SeverityBadge severity={r.severity} /></td>
                    <td style={{ padding: '10px 8px', ...MONO, fontSize: '10px', color: C.muted }}>{r.cooldown_minutes}m</td>
                    <td style={{ padding: '10px 8px', ...MONO, fontSize: '10px', color: C.muted }}>
                      {r.agent_id ? (agents.find(a => a.id === r.agent_id)?.label || r.agent_id.slice(0,8)) : 'ALL'}
                    </td>
                    <td style={{ padding: '10px 8px' }}>
                      <button onClick={() => handleToggle(r)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                        {r.enabled
                          ? <ToggleRight size={20} color={C.online} />
                          : <ToggleLeft  size={20} color={C.muted} />}
                      </button>
                    </td>
                    <td style={{ padding: '10px 8px' }}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <Btn onClick={() => openEdit(r)} small outline color={C.sub}><Pencil size={10} /></Btn>
                        <Btn onClick={() => handleDelete(r.id)} small danger><Trash2 size={10} /></Btn>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {modal && (
        <Modal title={editing ? 'EDIT ALERT RULE' : 'CREATE ALERT RULE'} onClose={() => setModal(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Field label="RULE NAME">
              <input style={INPUT_STYLE} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. High CPU Warning" />
            </Field>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="METRIC">
                <select style={SELECT_STYLE} value={form.metric} onChange={e => setForm(f => ({ ...f, metric: e.target.value }))}>
                  <option value="cpu">CPU</option>
                  <option value="memory">Memory</option>
                  <option value="disk">Disk</option>
                </select>
              </Field>
              <Field label="THRESHOLD (%)">
                <input style={INPUT_STYLE} type="number" min={1} max={100} step={1}
                  value={form.threshold} onChange={e => setForm(f => ({ ...f, threshold: parseFloat(e.target.value) || 0 }))} />
              </Field>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="SEVERITY">
                <select style={SELECT_STYLE} value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}>
                  {['critical','high','medium','low','info'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="COOLDOWN (MINUTES)">
                <input style={INPUT_STYLE} type="number" min={1} max={1440}
                  value={form.cooldown_minutes} onChange={e => setForm(f => ({ ...f, cooldown_minutes: parseInt(e.target.value) || 15 }))} />
              </Field>
            </div>
            <Field label="APPLIES TO AGENT" hint="Leave empty to apply to all agents in the org">
              <select style={SELECT_STYLE} value={form.agent_id || ''} onChange={e => setForm(f => ({ ...f, agent_id: e.target.value || null }))}>
                <option value="">All agents</option>
                {agents.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
            </Field>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ ...MONO, fontSize: '10px', color: C.sub }}>ENABLED</span>
              <button onClick={() => setForm(f => ({ ...f, enabled: !f.enabled }))} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                {form.enabled ? <ToggleRight size={24} color={C.online} /> : <ToggleLeft size={24} color={C.muted} />}
              </button>
            </div>
            {err && <span style={{ ...MONO, fontSize: '10px', color: C.critical }}>{err}</span>}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Btn onClick={() => setModal(false)} outline>CANCEL</Btn>
              <Btn onClick={handleSave} disabled={saving} color={C.warning}>
                {saving ? 'SAVING…' : editing ? 'SAVE CHANGES' : 'CREATE RULE'}
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

// ── Active Alerts Panel ───────────────────────────────────────────────────────

function ActiveAlertsPanel({ alerts, agents, loading, onRefresh, orgId }) {
  const [filter, setFilter] = useState('open');
  const [updating, setUpdating] = useState(null);

  const displayed = alerts.filter(a => filter === 'all' || a.status === filter);

  async function updateStatus(id, status) {
    setUpdating(id);
    try {
      await alertsApi.update(orgId, id, { status });
      onRefresh();
    } catch { alert('Update failed.'); }
    finally { setUpdating(null); }
  }

  return (
    <div style={PANEL}>
      <PanelHeader
        icon={AlertTriangle} iconColor={C.critical} title="ACTIVE ALERTS"
        count={`${alerts.filter(a => a.status === 'open').length} OPEN`} countColor={C.critical}
        action={
          <div style={{ display: 'flex', gap: 4 }}>
            {['open','acknowledged','resolved','all'].map(f => (
              <button key={f} onClick={() => setFilter(f)} style={{
                background: filter === f ? `${C.accent}18` : 'none',
                border: `1px solid ${filter === f ? C.accent : C.border}`,
                borderRadius: 6, padding: '3px 8px', cursor: 'pointer',
                color: filter === f ? C.accent : C.muted,
                ...MONO, fontSize: '9px', letterSpacing: '0.05em',
              }}>
                {f.toUpperCase()}
              </button>
            ))}
          </div>
        }
      />
      <div style={{ padding: '4px 20px 20px', overflowX: 'auto' }}>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 16 }}>
            {[1,2,3].map(i => <Skeleton key={i} width="100%" height={40} radius={6} />)}
          </div>
        ) : displayed.length === 0 ? (
          <div style={{ padding: '40px 0', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <CheckCircle2 size={28} color={C.online} />
            <span style={{ ...MONO, fontSize: '11px', color: C.muted }}>
              {filter === 'open' ? 'NO OPEN ALERTS' : 'NO ALERTS FOUND'}
            </span>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
            <thead>
              <tr>
                {['AGENT','CATEGORY','VALUE','SEVERITY','CREATED','STATUS',''].map((h,i) => (
                  <th key={h+i} style={{
                    ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: C.muted,
                    padding: '10px 8px', borderBottom: `1px solid ${C.border}`,
                    textAlign: 'left', fontWeight: 500, whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayed.map(a => {
                const agentLabel = agents.find(ag => ag.id === a.agent_id)?.label || a.agent_id?.slice(0,8) || '—';
                const statusColor = { open: C.critical, acknowledged: C.warning, resolved: C.online }[a.status] || C.muted;
                return (
                  <tr key={a.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td style={{ padding: '10px 8px', ...UI, fontSize: '12px', color: C.text, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{agentLabel}</td>
                    <td style={{ padding: '10px 8px' }}><MetricBadge metric={a.category} /></td>
                    <td style={{ padding: '10px 8px', ...MONO, fontSize: '11px', color: SEVERITY_COLOR[a.severity] || C.sub }}>
                      {a.metric_value != null ? `${a.metric_value.toFixed(1)}%` : '—'}
                      {a.threshold != null && <span style={{ color: C.muted }}> / {a.threshold}%</span>}
                    </td>
                    <td style={{ padding: '10px 8px' }}><SeverityBadge severity={a.severity} /></td>
                    <td style={{ padding: '10px 8px', ...MONO, fontSize: '10px', color: C.muted, whiteSpace: 'nowrap' }}>
                      {relativeTime(a.created_at)}
                    </td>
                    <td style={{ padding: '10px 8px' }}>
                      <span style={{
                        ...MONO, fontSize: '9px',
                        color: statusColor, background: `${statusColor}14`,
                        padding: '2px 7px', borderRadius: 10,
                      }}>
                        {(a.status || '').toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '10px 8px' }}>
                      <div style={{ display: 'flex', gap: 5 }}>
                        {a.status === 'open' && (
                          <Btn onClick={() => updateStatus(a.id, 'acknowledged')} small color={C.warning}
                            disabled={updating === a.id}>
                            <CheckCheck size={10} /> ACK
                          </Btn>
                        )}
                        {a.status !== 'resolved' && (
                          <Btn onClick={() => updateStatus(a.id, 'resolved')} small color={C.online}
                            disabled={updating === a.id}>
                            <CheckCircle2 size={10} /> RESOLVE
                          </Btn>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Notification Channels Panel ───────────────────────────────────────────────
const BLANK_CHANNEL = {
  channel_type: 'email', label: '', enabled: true, severities: null,
  config: { email: '', smtp_host: 'smtp.gmail.com', smtp_port: 587, smtp_user: '', smtp_password: '', smtp_from: '' },
};

function ChannelIcon({ type }) {
  if (type === 'email')    return <Mail    size={14} color={C.info}    />;
  if (type === 'slack')    return <Hash    size={14} color={C.warning} />;
  if (type === 'telegram') return <Send    size={14} color={C.online}  />;
  return <Bell size={14} color={C.sub} />;
}

const SEV_ALL = ['critical','high','medium','low','info'];

function SeverityCheckboxes({ value, onChange }) {
  const active = value || SEV_ALL;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {SEV_ALL.map(s => {
        const on = active.includes(s);
        const col = SEVERITY_COLOR[s];
        return (
          <button
            key={s}
            onClick={() => {
              if (on && active.length === 1) return; // prevent empty
              onChange(on ? active.filter(x => x !== s) : [...active, s]);
            }}
            style={{
              border: `1px solid ${on ? col : C.border}`,
              borderRadius: 8, padding: '3px 8px', cursor: 'pointer',
              background: on ? `${col}18` : 'transparent',
              color: on ? col : C.muted,
              ...MONO, fontSize: '9px',
            }}
          >{SEVERITY_EMOJI[s]} {s}</button>
        );
      })}
      <button
        onClick={() => onChange(null)}
        style={{
          border: `1px solid ${value === null ? C.accent : C.border}`,
          borderRadius: 8, padding: '3px 8px', cursor: 'pointer',
          background: value === null ? `${C.accent}18` : 'transparent',
          color: value === null ? C.accent : C.muted,
          ...MONO, fontSize: '9px',
        }}
      >ALL</button>
    </div>
  );
}

function NotificationChannelsPanel({ channels, loading, onRefresh, orgId }) {
  const [modal, setModal]     = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm]       = useState(BLANK_CHANNEL);
  const [saving, setSaving]   = useState(false);
  const [testing, setTesting] = useState(null);
  const [testResult, setTestResult] = useState({});
  const [err, setErr]         = useState('');
  const [showPasswords, setShowPasswords] = useState({});

  function openCreate() {
    setEditing(null);
    setForm({ ...BLANK_CHANNEL, config: { ...BLANK_CHANNEL.config } });
    setErr(''); setModal(true);
  }
  function openEdit(ch) {
    setEditing(ch);
    setForm({ channel_type: ch.channel_type, label: ch.label || '', enabled: ch.enabled, severities: ch.severities, config: { ...ch.config } });
    setErr(''); setModal(true);
  }

  function setConfig(k, v) {
    setForm(f => ({ ...f, config: { ...f.config, [k]: v } }));
  }

  function switchType(type) {
    const defaults = {
      email:    { email: '', smtp_host: 'smtp.gmail.com', smtp_port: 587, smtp_user: '', smtp_password: '', smtp_from: '' },
      slack:    { webhook_url: '' },
      telegram: { bot_token: '', chat_id: '' },
    };
    setForm(f => ({ ...f, channel_type: type, config: defaults[type] || {} }));
  }

  async function handleSave() {
    const t = form.channel_type;
    if (t === 'email' && !form.config.email) { setErr('Recipient email is required.'); return; }
    if (t === 'slack' && !form.config.webhook_url) { setErr('Webhook URL is required.'); return; }
    if (t === 'telegram' && (!form.config.bot_token || !form.config.chat_id)) { setErr('Bot token and Chat ID are required.'); return; }
    setSaving(true); setErr('');
    try {
      const payload = {
        channel_type: form.channel_type,
        label: form.label || undefined,
        config: form.config,
        enabled: form.enabled,
        severities: form.severities,
      };
      if (editing) { await notificationChannelsApi.update(orgId, editing.id, payload); }
      else         { await notificationChannelsApi.create(orgId, payload); }
      setModal(false); onRefresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Save failed.');
    } finally { setSaving(false); }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this notification channel?')) return;
    try { await notificationChannelsApi.remove(orgId, id); onRefresh(); }
    catch { alert('Delete failed.'); }
  }

  async function handleTest(id) {
    setTesting(id); setTestResult(r => ({ ...r, [id]: null }));
    try {
      const res = await notificationChannelsApi.test(orgId, id);
      setTestResult(r => ({ ...r, [id]: res.ok ? 'sent' : res.error || 'failed' }));
    } catch { setTestResult(r => ({ ...r, [id]: 'failed' })); }
    finally { setTesting(null); }
  }

  async function handleToggle(ch) {
    try { await notificationChannelsApi.update(orgId, ch.id, { enabled: !ch.enabled }); onRefresh(); }
    catch { alert('Update failed.'); }
  }

  return (
    <>
      <div style={PANEL}>
        <PanelHeader
          icon={Bell} iconColor={C.info} title="MY NOTIFICATION CHANNELS"
          count={`${channels.length} CHANNEL${channels.length !== 1 ? 'S' : ''}`} countColor={C.info}
          action={
            <Btn onClick={openCreate} color={C.info} small>
              <Plus size={10} /> ADD CHANNEL
            </Btn>
          }
        />
        <div style={{ padding: channels.length === 0 ? '0' : '4px 20px 20px' }}>
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '16px 20px' }}>
              {[1,2].map(i => <Skeleton key={i} width="100%" height={52} radius={8} />)}
            </div>
          ) : channels.length === 0 ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
              <BellOff size={28} color={C.muted} />
              <span style={{ ...MONO, fontSize: '11px', color: C.muted }}>NO NOTIFICATION CHANNELS</span>
              <span style={{ fontSize: '12px', color: C.muted, maxWidth: 280 }}>
                Add a channel to receive alerts via Email, Slack, or Telegram.
              </span>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
              {channels.map(ch => {
                const tr = testResult[ch.id];
                return (
                  <div key={ch.id} style={{
                    background: 'rgba(42,40,32,0.18)',
                    border: `1px solid ${C.border}`,
                    borderRadius: 10,
                    padding: '14px 16px',
                    display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
                  }}>
                    <ChannelIcon type={ch.channel_type} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ ...UI, fontSize: '13px', color: C.text, fontWeight: 500 }}>
                        {ch.label || ch.channel_type}
                      </div>
                      <div style={{ ...MONO, fontSize: '10px', color: C.muted, marginTop: 2 }}>
                        {ch.channel_type === 'email'    && (ch.config?.email || '—')}
                        {ch.channel_type === 'slack'    && 'Slack webhook'}
                        {ch.channel_type === 'telegram' && `Chat ID: ${ch.config?.chat_id || '—'}`}
                        {' · '}
                        <span style={{ color: ch.severities ? C.warning : C.muted }}>
                          {ch.severities ? ch.severities.join(', ') : 'all severities'}
                        </span>
                      </div>
                    </div>
                    {tr && (
                      <span style={{
                        ...MONO, fontSize: '9px',
                        color: tr === 'sent' ? C.online : C.critical,
                        background: tr === 'sent' ? `${C.online}14` : `${C.critical}14`,
                        padding: '2px 7px', borderRadius: 10,
                      }}>
                        {tr === 'sent' ? 'TEST SENT' : `FAILED: ${tr}`}
                      </span>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <button onClick={() => handleToggle(ch)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                        {ch.enabled ? <ToggleRight size={20} color={C.online} /> : <ToggleLeft size={20} color={C.muted} />}
                      </button>
                      <Btn onClick={() => handleTest(ch.id)} small color={C.info} disabled={testing === ch.id}>
                        {testing === ch.id ? 'TESTING…' : 'TEST'}
                      </Btn>
                      <Btn onClick={() => openEdit(ch)} small outline color={C.sub}><Pencil size={10} /></Btn>
                      <Btn onClick={() => handleDelete(ch.id)} small danger><Trash2 size={10} /></Btn>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {modal && (
        <Modal title={editing ? 'EDIT CHANNEL' : 'ADD NOTIFICATION CHANNEL'} onClose={() => setModal(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Field label="CHANNEL TYPE">
              <div style={{ display: 'flex', gap: 8 }}>
                {['email','slack','telegram'].map(t => (
                  <button key={t} onClick={() => !editing && switchType(t)} style={{
                    flex: 1, border: `1px solid ${form.channel_type === t ? C.accent : C.border}`,
                    borderRadius: 8, padding: '8px 4px', cursor: editing ? 'default' : 'pointer',
                    background: form.channel_type === t ? `${C.accent}18` : 'transparent',
                    color: form.channel_type === t ? C.accent : C.muted,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                    ...MONO, fontSize: '9px',
                  }}>
                    <ChannelIcon type={t} />
                    {t.toUpperCase()}
                  </button>
                ))}
              </div>
            </Field>

            <Field label="LABEL (OPTIONAL)">
              <input style={INPUT_STYLE} value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} placeholder="e.g. Ops Team Email" />
            </Field>

            {form.channel_type === 'email' && (
              <>
                <Field label="RECIPIENT EMAIL">
                  <input style={INPUT_STYLE} type="email" value={form.config.email || ''} onChange={e => setConfig('email', e.target.value)} placeholder="ops@company.com" />
                </Field>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                  <Field label="SMTP HOST">
                    <input style={INPUT_STYLE} value={form.config.smtp_host || ''} onChange={e => setConfig('smtp_host', e.target.value)} placeholder="smtp.gmail.com" />
                  </Field>
                  <Field label="SMTP PORT">
                    <input style={INPUT_STYLE} type="number" value={form.config.smtp_port || 587} onChange={e => setConfig('smtp_port', parseInt(e.target.value) || 587)} />
                  </Field>
                </div>
                <Field label="SMTP USERNAME">
                  <input style={INPUT_STYLE} value={form.config.smtp_user || ''} onChange={e => setConfig('smtp_user', e.target.value)} placeholder="your-email@gmail.com" />
                </Field>
                <Field label="SMTP PASSWORD">
                  <div style={{ position: 'relative' }}>
                    <input style={{ ...INPUT_STYLE, paddingRight: 40 }}
                      type={showPasswords.smtp ? 'text' : 'password'}
                      value={form.config.smtp_password || ''} onChange={e => setConfig('smtp_password', e.target.value)} placeholder="App password" />
                    <button onClick={() => setShowPasswords(p => ({ ...p, smtp: !p.smtp }))}
                      style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer' }}>
                      {showPasswords.smtp ? <EyeOff size={14} color={C.muted} /> : <Eye size={14} color={C.muted} />}
                    </button>
                  </div>
                </Field>
                <Field label="FROM ADDRESS (OPTIONAL)">
                  <input style={INPUT_STYLE} value={form.config.smtp_from || ''} onChange={e => setConfig('smtp_from', e.target.value)} placeholder="Resilo AIOps <alerts@company.com>" />
                </Field>
              </>
            )}

            {form.channel_type === 'slack' && (
              <Field label="WEBHOOK URL" hint="Create an Incoming Webhook in your Slack workspace settings">
                <input style={INPUT_STYLE} value={form.config.webhook_url || ''} onChange={e => setConfig('webhook_url', e.target.value)} placeholder="https://hooks.slack.com/services/..." />
              </Field>
            )}

            {form.channel_type === 'telegram' && (
              <>
                <Field label="BOT TOKEN" hint="Create a bot via @BotFather on Telegram">
                  <div style={{ position: 'relative' }}>
                    <input style={{ ...INPUT_STYLE, paddingRight: 40 }}
                      type={showPasswords.tg ? 'text' : 'password'}
                      value={form.config.bot_token || ''} onChange={e => setConfig('bot_token', e.target.value)} placeholder="123456789:ABC..." />
                    <button onClick={() => setShowPasswords(p => ({ ...p, tg: !p.tg }))}
                      style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer' }}>
                      {showPasswords.tg ? <EyeOff size={14} color={C.muted} /> : <Eye size={14} color={C.muted} />}
                    </button>
                  </div>
                </Field>
                <Field label="CHAT ID" hint="Your chat or group ID (use @userinfobot to find it)">
                  <input style={INPUT_STYLE} value={form.config.chat_id || ''} onChange={e => setConfig('chat_id', e.target.value)} placeholder="-100123456789" />
                </Field>
              </>
            )}

            <Field label="NOTIFY FOR SEVERITIES">
              <SeverityCheckboxes
                value={form.severities}
                onChange={v => setForm(f => ({ ...f, severities: v }))}
              />
            </Field>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ ...MONO, fontSize: '10px', color: C.sub }}>ENABLED</span>
              <button onClick={() => setForm(f => ({ ...f, enabled: !f.enabled }))} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                {form.enabled ? <ToggleRight size={24} color={C.online} /> : <ToggleLeft size={24} color={C.muted} />}
              </button>
            </div>

            {err && <span style={{ ...MONO, fontSize: '10px', color: C.critical }}>{err}</span>}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Btn onClick={() => setModal(false)} outline>CANCEL</Btn>
              <Btn onClick={handleSave} disabled={saving} color={C.info}>
                {saving ? 'SAVING…' : editing ? 'SAVE CHANGES' : 'ADD CHANNEL'}
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

// ── Notification Logs Panel ───────────────────────────────────────────────────

function NotifLogsPanel({ logs, loading, onRefresh }) {
  return (
    <div style={PANEL}>
      <PanelHeader
        icon={Layers} iconColor={C.sub} title="NOTIFICATION HISTORY"
        count={`${logs.length} ENTRIES`} countColor={C.sub}
        action={<Btn onClick={onRefresh} small outline><RefreshCw size={10} /> REFRESH</Btn>}
      />
      <div style={{ padding: '4px 20px 20px', overflowX: 'auto' }}>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 16 }}>
            {[1,2,3].map(i => <Skeleton key={i} width="100%" height={32} radius={6} />)}
          </div>
        ) : logs.length === 0 ? (
          <div style={{ padding: '40px 0', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <Layers size={28} color={C.muted} />
            <span style={{ ...MONO, fontSize: '11px', color: C.muted }}>NO NOTIFICATION HISTORY</span>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
            <thead>
              <tr>
                {['SENT AT','TYPE','CHANNEL','RECIPIENT','SUBJECT','STATUS'].map((h,i) => (
                  <th key={h+i} style={{
                    ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: C.muted,
                    padding: '10px 8px', borderBottom: `1px solid ${C.border}`,
                    textAlign: 'left', fontWeight: 500, whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map(l => {
                const statusColor = l.status === 'sent' ? C.online : C.critical;
                return (
                  <tr key={l.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td style={{ padding: '9px 8px', ...MONO, fontSize: '10px', color: C.muted, whiteSpace: 'nowrap' }}>{fmtDateTime(l.sent_at)}</td>
                    <td style={{ padding: '9px 8px' }}>
                      <span style={{
                        ...MONO, fontSize: '9px',
                        color: l.notification_type === 'alert' ? C.warning : C.info,
                        background: l.notification_type === 'alert' ? `${C.warning}14` : `${C.info}14`,
                        padding: '2px 6px', borderRadius: 8,
                      }}>
                        {(l.notification_type || 'alert').toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '9px 8px' }}><ChannelIcon type={l.channel_type} /></td>
                    <td style={{ padding: '9px 8px', ...MONO, fontSize: '10px', color: C.sub, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {l.recipient || '—'}
                    </td>
                    <td style={{ padding: '9px 8px', ...UI, fontSize: '12px', color: C.sub, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {l.subject || '—'}
                    </td>
                    <td style={{ padding: '9px 8px' }}>
                      <span style={{
                        ...MONO, fontSize: '9px',
                        color: statusColor, background: `${statusColor}14`,
                        padding: '2px 6px', borderRadius: 8,
                      }}>
                        {(l.status || '').toUpperCase()}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Daily Summary Card ────────────────────────────────────────────────────────
function DailySummaryCard({ orgId }) {
  const [sending, setSending] = useState(false);
  const [result, setResult]   = useState(null);

  async function sendSummary() {
    setSending(true); setResult(null);
    try {
      await dailySummaryApi.send(orgId);
      setResult({ ok: true, msg: 'Daily summary dispatched to all channels.' });
    } catch (e) {
      setResult({ ok: false, msg: e?.response?.data?.detail || 'Dispatch failed.' });
    } finally { setSending(false); }
  }

  return (
    <div style={{ ...PANEL, padding: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: `${C.accent}14`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <BarChart2 size={18} color={C.accent} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ ...UI, fontSize: '14px', color: C.text, fontWeight: 600 }}>Daily Operations Summary</div>
          <div style={{ ...MONO, fontSize: '10px', color: C.muted, marginTop: 3 }}>
            Auto-dispatches at {process.env.REACT_APP_SUMMARY_HOUR || '08'}:00 UTC · Covers last 24 h of metrics and incidents
          </div>
        </div>
        <Btn onClick={sendSummary} disabled={sending} color={C.accent}>
          <Send size={12} /> {sending ? 'SENDING…' : 'SEND NOW'}
        </Btn>
      </div>
      {result && (
        <div style={{
          marginTop: 12, padding: '8px 12px', borderRadius: 8,
          background: result.ok ? `${C.online}14` : `${C.critical}14`,
          ...MONO, fontSize: '10px',
          color: result.ok ? C.online : C.critical,
        }}>
          {result.msg}
        </div>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function TeamAndDevices() {
  const { role } = useAuth();
  const isAdmin  = role === 'admin';
  const orgId    = getOrgId();
  const me       = getCurrentUser();

  const [activeTab,   setActiveTab]   = useState('fleet');
  const [agents,      setAgents]      = useState([]);
  const [users,       setUsers]       = useState([]);
  const [openAlerts,  setOpenAlerts]  = useState([]);
  const [alertRules,  setAlertRules]  = useState([]);
  const [channels,    setChannels]    = useState([]);
  const [notifLogs,   setNotifLogs]   = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [refreshing,  setRefreshing]  = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);
  const intervalRef = useRef(null);

  // ── Register-agent modal state ────────────────────────────────────────────
  const [showRegister,  setShowRegister]  = useState(false);
  const [regLabel,      setRegLabel]      = useState('');
  const [regBusy,       setRegBusy]       = useState(false);
  const [regError,      setRegError]      = useState('');
  const [createdAgent,  setCreatedAgent]  = useState(null); // holds { label, api_key, install_cmd }

  const handleRegisterAgent = useCallback(async () => {
    if (!regLabel.trim()) return;
    setRegBusy(true);
    setRegError('');
    try {
      const result = await agentsApi.create(orgId, regLabel.trim());
      setCreatedAgent(result);
      setShowRegister(false);
      setRegLabel('');
      fetchCore();
    } catch (err) {
      setRegError(err?.response?.data?.detail || err?.message || 'Failed to register agent');
    } finally {
      setRegBusy(false);
    }
  }, [orgId, regLabel, fetchCore]);

  const fetchCore = useCallback(async () => {
    try {
      const [rawAgents, rawMetrics, rawAlerts] = await Promise.all([
        agentsApi.list(orgId).catch(() => []),
        metricsApi.getLatest(orgId).catch(() => []),
        alertsApi.list(orgId).catch(() => []),
      ]);
      const metricsMap = {};
      (Array.isArray(rawMetrics) ? rawMetrics : []).forEach(m => {
        if (m?.agent_id) metricsMap[m.agent_id] = m;
      });
      const merged = (Array.isArray(rawAgents) ? rawAgents : []).map(a => ({
        ...a, metrics: metricsMap[a.id] || {},
      }));
      setAgents(merged);
      setOpenAlerts(Array.isArray(rawAlerts) ? rawAlerts : []);
    } catch (err) {
      console.error('[TeamAndDevices] core fetch error:', err);
    }
  }, [orgId]);

  const fetchAdmin = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const [rawUsers, rawRules, rawLogs] = await Promise.all([
        userApi.list().catch(() => []),
        alertRulesApi.list(orgId).catch(() => []),
        notificationLogsApi.list(orgId, { limit: 100 }).catch(() => []),
      ]);
      setUsers(Array.isArray(rawUsers) ? rawUsers : []);
      setAlertRules(Array.isArray(rawRules) ? rawRules : []);
      setNotifLogs(Array.isArray(rawLogs) ? rawLogs : []);
    } catch (err) {
      console.error('[TeamAndDevices] admin fetch error:', err);
    }
  }, [isAdmin, orgId]);

  const fetchChannels = useCallback(async () => {
    try {
      const raw = await notificationChannelsApi.list(orgId).catch(() => []);
      // Non-admins only see their own channels
      const filtered = isAdmin ? raw : raw.filter(ch => !ch.user_id || ch.user_id === me?.id);
      setChannels(Array.isArray(filtered) ? filtered : []);
    } catch (err) {
      console.error('[TeamAndDevices] channels fetch error:', err);
    }
  }, [orgId, isAdmin, me?.id]);

  const fetchAll = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    await Promise.all([fetchCore(), fetchAdmin(), fetchChannels()]);
    setLastRefresh(new Date());
    setLoading(false);
    setRefreshing(false);
  }, [fetchCore, fetchAdmin, fetchChannels]);

  useEffect(() => {
    fetchAll();
    return () => {};
  }, [fetchAll]);

  // Stats
  const total   = agents.length;
  const online  = agents.filter(a => deriveStatus(a.last_seen) === 'online').length;
  const warning = agents.filter(a => deriveStatus(a.last_seen) === 'warning').length;
  const openCount = openAlerts.filter(a => a.status === 'open').length;

  const stats = [
    { label: 'TOTAL AGENTS', value: total,   icon: Server,        color: C.sub     },
    { label: 'ONLINE',       value: online,  icon: Activity,      color: C.online  },
    { label: 'WARNING',      value: warning, icon: AlertTriangle, color: C.warning },
    { label: 'OPEN ALERTS',  value: openCount, icon: Bell,        color: openCount > 0 ? C.critical : C.muted },
  ];

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px', color: C.text, ...UI }}>

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', margin: 0, lineHeight: 1 }}>
            {isAdmin ? 'Users & Devices' : 'Devices'}
          </h1>
          <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: C.muted, marginTop: 6, marginBottom: 0 }}>
            RESOURCE MANAGEMENT
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {lastRefresh && (
            <span style={{ ...MONO, fontSize: '10px', color: C.muted }}>
              UPDATED {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => fetchAll(true)}
            disabled={refreshing}
            style={{
              background: 'none', border: `1px solid ${C.border}`, borderRadius: 8,
              padding: '6px 10px', cursor: refreshing ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 6,
              color: C.sub, opacity: refreshing ? 0.5 : 1, transition: 'opacity 0.2s',
            }}
          >
            <RefreshCw size={13} color={C.sub} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
            <span style={{ ...MONO, fontSize: '10px' }}>REFRESH</span>
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {stats.map(s => <StatCard key={s.label} {...s} loading={loading} />)}
      </div>

      {/* Tab navigation */}
      <TabNav active={activeTab} onChange={setActiveTab} isAdmin={isAdmin} alertCount={openCount} />

      {/* ── REGISTER AGENT MODAL ── */}
      {showRegister && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => { setShowRegister(false); setRegError(''); setRegLabel(''); }}>
          <div style={{
            ...PANEL, padding: '28px', width: '100%', maxWidth: 420,
            display: 'flex', flexDirection: 'column', gap: 16,
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Server size={16} color={C.accent} />
              <span style={{ ...MONO, fontSize: '12px', letterSpacing: '0.1em', color: C.sub }}>REGISTER MONITORING AGENT</span>
            </div>
            <p style={{ ...UI, fontSize: '12px', color: C.muted, margin: 0 }}>
              Give this agent a descriptive name (e.g. the hostname or service it will monitor).
              An API key will be generated — save it immediately.
            </p>
            <div>
              <label style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: C.muted, display: 'block', marginBottom: 6 }}>
                AGENT LABEL
              </label>
              <input
                autoFocus
                value={regLabel}
                onChange={e => setRegLabel(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleRegisterAgent(); if (e.key === 'Escape') { setShowRegister(false); setRegLabel(''); } }}
                placeholder="e.g. prod-server-01"
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: C.input, border: `1px solid ${C.border}`,
                  borderRadius: 8, padding: '9px 12px',
                  ...UI, fontSize: '13px', color: C.text, outline: 'none',
                }}
              />
            </div>
            {regError && (
              <div style={{ ...MONO, fontSize: '11px', color: C.critical, background: `${C.critical}12`, padding: '7px 10px', borderRadius: 6 }}>
                {regError}
              </div>
            )}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Btn outline color={C.muted} small onClick={() => { setShowRegister(false); setRegLabel(''); setRegError(''); }}>CANCEL</Btn>
              <Btn small disabled={!regLabel.trim() || regBusy} onClick={handleRegisterAgent}>
                <Plus size={11} /> {regBusy ? 'REGISTERING…' : 'REGISTER'}
              </Btn>
            </div>
          </div>
        </div>
      )}

      {/* ── CREATED AGENT KEY MODAL ── */}
      {createdAgent && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            ...PANEL, padding: '28px', width: '100%', maxWidth: 520,
            display: 'flex', flexDirection: 'column', gap: 16,
            border: `1px solid ${C.online}30`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <CheckCircle2 size={16} color={C.online} />
              <span style={{ ...MONO, fontSize: '12px', letterSpacing: '0.1em', color: C.online }}>AGENT REGISTERED</span>
            </div>
            <div style={{ background: `${C.warning}12`, border: `1px solid ${C.warning}30`, borderRadius: 8, padding: '10px 14px', ...UI, fontSize: '12px', color: C.warning }}>
              ⚠ Copy the API key now. It will <strong>not</strong> be shown again.
            </div>
            <div>
              <div style={{ ...MONO, fontSize: '10px', color: C.muted, marginBottom: 6, letterSpacing: '0.1em' }}>AGENT LABEL</div>
              <div style={{ ...UI, fontSize: '13px', color: C.text }}>{createdAgent.label}</div>
            </div>
            <div>
              <div style={{ ...MONO, fontSize: '10px', color: C.muted, marginBottom: 6, letterSpacing: '0.1em' }}>API KEY</div>
              <div style={{
                background: C.input, border: `1px solid ${C.online}40`, borderRadius: 8,
                padding: '10px 14px', ...MONO, fontSize: '11px', color: C.online,
                wordBreak: 'break-all', userSelect: 'all',
              }}>
                {createdAgent.api_key}
              </div>
            </div>
            <div>
              <div style={{ ...MONO, fontSize: '10px', color: C.muted, marginBottom: 6, letterSpacing: '0.1em' }}>INSTALL COMMAND</div>
              <div style={{
                background: C.input, border: `1px solid ${C.border}`, borderRadius: 8,
                padding: '10px 14px', ...MONO, fontSize: '10px', color: C.sub,
                wordBreak: 'break-all', userSelect: 'all', lineHeight: 1.6,
              }}>
                {createdAgent.install_cmd}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Btn small onClick={() => { navigator.clipboard?.writeText(createdAgent.api_key).catch(() => {}); }}>
                COPY KEY
              </Btn>
              <Btn small outline color={C.muted} onClick={() => setCreatedAgent(null)}>DONE</Btn>
            </div>
          </div>
        </div>
      )}

      {/* ── FLEET TAB ── */}
      {activeTab === 'fleet' && (
        <div style={PANEL}>
          <PanelHeader
            icon={Server} iconColor={C.online} title="FLEET STATUS"
            count={loading ? undefined : `${total} AGENT${total !== 1 ? 'S' : ''}`}
            action={isAdmin && (
              <Btn small onClick={() => { setShowRegister(true); setRegError(''); setRegLabel(''); }}>
                <Plus size={11} /> ADD AGENT
              </Btn>
            )}
          />
          <div style={{ padding: '20px' }}>
            {loading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {[1,2,3].map(i => <AgentSkeleton key={i} />)}
              </div>
            ) : agents.length === 0 ? (
              <div style={{ padding: '40px 0', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                <Server size={28} color={C.muted} />
                <span style={{ ...MONO, fontSize: '11px', color: C.muted }}>NO AGENTS REGISTERED</span>
                <span style={{ fontSize: '12px', color: C.muted, maxWidth: 280 }}>
                  Deploy the remote agent on a machine to start monitoring.
                </span>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {agents.map(a => <AgentCard key={a.id} agent={a} users={users} />)}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── ALERTS TAB ── */}
      {activeTab === 'alerts' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <ActiveAlertsPanel
            alerts={openAlerts}
            agents={agents}
            loading={loading}
            onRefresh={() => fetchCore()}
            orgId={orgId}
          />
          {isAdmin && (
            <AlertRulesPanel
              rules={alertRules}
              agents={agents}
              loading={loading}
              onRefresh={() => fetchAdmin()}
              orgId={orgId}
            />
          )}
        </div>
      )}

      {/* ── NOTIFICATIONS TAB ── */}
      {activeTab === 'notifications' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <NotificationChannelsPanel
            channels={channels}
            loading={loading}
            onRefresh={() => fetchChannels()}
            orgId={orgId}
          />
          {isAdmin && <DailySummaryCard orgId={orgId} />}
          {isAdmin && (
            <NotifLogsPanel
              logs={notifLogs}
              loading={loading}
              onRefresh={() => fetchAdmin()}
            />
          )}
        </div>
      )}

      {/* ── USERS TAB (admin only) ── */}
      {activeTab === 'users' && isAdmin && (
        <div style={PANEL}>
          <PanelHeader
            icon={Users} iconColor={C.warning} title="REGISTERED USERS"
            count={`${users.length} USER${users.length !== 1 ? 'S' : ''}`} countColor={C.warning}
          />
          <div style={{ padding: '4px 20px 16px' }}>
            {loading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 16 }}>
                {[1,2,3].map(i => <Skeleton key={i} width="100%" height={40} radius={6} />)}
              </div>
            ) : users.length === 0 ? (
              <div style={{ padding: '40px 0', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                <Users size={28} color={C.muted} />
                <span style={{ ...MONO, fontSize: '11px', color: C.muted }}>NO USERS FOUND</span>
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    {['USER','ROLE','STATUS','JOINED'].map((h, i) => (
                      <th key={h} style={{
                        ...MONO, fontSize: '9px', letterSpacing: '0.08em',
                        color: C.muted, paddingBottom: 12, paddingTop: 14,
                        borderBottom: `1px solid ${C.border}`,
                        textAlign: i === 2 ? 'center' : i === 3 ? 'right' : 'left',
                        fontWeight: 500,
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {users.map((u, i) => <UserRow key={u.id || i} user={u} />)}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
