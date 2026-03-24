/**
 * NotificationSettings.js — Alerts & Notification settings page
 * Warm-dark amber theme matching the rest of the Resilo dashboard.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell, Mail, MessageSquare, Send, Shield, Clock, Calendar,
  Plus, Trash2, CheckCircle, XCircle, Activity,
  Edit2, Loader, RefreshCw,
  Zap, BarChart2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  notificationChannelsApi,
  alertRulesApi,
  notificationLogsApi,
  dailySummaryApi,
  metricsApi,
} from '../../services/resiloApi';

// ── Design tokens (match existing Resilo components) ──────────────────────────
const C = {
  bg:        'rgb(14,13,11)',
  surface:   'rgb(22,20,16)',
  surface2:  'rgb(31,29,24)',
  surface3:  'rgb(38,36,30)',
  border:    'rgba(42,40,32,1)',
  borderDim: 'rgba(42,40,32,0.5)',
  amber:     '#F59E0B',
  amberDim:  '#D97706',
  amberLow:  'rgba(245,158,11,0.08)',
  amberMid:  'rgba(245,158,11,0.15)',
  red:       '#F87171',
  redLow:    'rgba(248,113,113,0.08)',
  teal:      '#2DD4BF',
  tealLow:   'rgba(45,212,191,0.08)',
  yellow:    '#FDE047',
  text1:     'rgb(245,240,232)',
  text2:     'rgb(168,159,140)',
  text3:     'rgb(107,99,87)',
  mono:      "'IBM Plex Mono', monospace",
  ui:        "'Outfit', sans-serif",
};

const SEV_COLOR = {
  critical: '#F87171',
  high:     '#FB923C',
  medium:   '#FDE047',
  low:      '#4ADE80',
  info:     '#60A5FA',
};

const BUILTIN_RULES = [
  { id: '__cpu_high',  name: 'CPU High',      metric: 'cpu',    threshold: 85, severity: 'high',     cooldown_minutes: 5, builtin: true },
  { id: '__cpu_crit',  name: 'CPU Critical',  metric: 'cpu',    threshold: 95, severity: 'critical', cooldown_minutes: 5, builtin: true },
  { id: '__mem_high',  name: 'Memory High',   metric: 'memory', threshold: 80, severity: 'high',     cooldown_minutes: 5, builtin: true },
  { id: '__mem_crit',  name: 'Memory Critical',metric:'memory', threshold: 92, severity: 'critical', cooldown_minutes: 5, builtin: true },
  { id: '__disk_high', name: 'Disk High',     metric: 'disk',   threshold: 85, severity: 'high',     cooldown_minutes: 5, builtin: true },
  { id: '__disk_crit', name: 'Disk Critical', metric: 'disk',   threshold: 95, severity: 'critical', cooldown_minutes: 5, builtin: true },
];

const CHANNEL_META = {
  email:    { icon: Mail,           label: 'Email / SMTP'  },
  slack:    { icon: MessageSquare,  label: 'Slack Webhook' },
  telegram: { icon: Send,           label: 'Telegram Bot'  },
};

const fmtTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const fmtPct = (v) => (v == null ? '—' : `${Number(v).toFixed(1)}%`);

// ── Tiny shared UI primitives ─────────────────────────────────────────────────

function Pill({ color, children }) {
  return (
    <span style={{
      fontFamily: C.mono, fontSize: 10, letterSpacing: '0.08em',
      padding: '2px 8px', borderRadius: 20,
      background: `${color}22`, color, border: `1px solid ${color}44`,
    }}>{children}</span>
  );
}

function StatCard({ icon: Icon, label, value, sub, color = C.amber }) {
  return (
    <div style={{
      flex: 1, minWidth: 140,
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: '16px 18px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Icon size={14} color={color} />
        <span style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.1em', color: C.text3 }}>{label}</span>
      </div>
      <div style={{ fontFamily: C.mono, fontSize: 22, color, letterSpacing: '-0.02em', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontFamily: C.ui, fontSize: 11, color: C.text3, marginTop: 5 }}>{sub}</div>}
    </div>
  );
}

function Spinner({ size = 14 }) {
  return <Loader size={size} color={C.amber} style={{ animation: 'spin 1s linear infinite' }} />;
}

function SectionHeader({ title, sub, action }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 16 }}>
      <div>
        <div style={{ fontFamily: C.ui, fontSize: 15, fontWeight: 600, color: C.text1 }}>{title}</div>
        {sub && <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 3 }}>{sub}</div>}
      </div>
      {action}
    </div>
  );
}

function Btn({ children, onClick, variant = 'primary', small, disabled, loading, icon: Icon, style: sx }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: small ? '5px 12px' : '8px 16px',
    borderRadius: 6, cursor: disabled || loading ? 'not-allowed' : 'pointer',
    fontSize: small ? 12 : 13, fontFamily: C.ui, fontWeight: 500,
    border: 'none', transition: 'opacity 0.15s',
    opacity: disabled || loading ? 0.55 : 1,
    ...sx,
  };
  const variants = {
    primary:  { background: C.amber,   color: '#0C0B09' },
    ghost:    { background: 'transparent', color: C.text2, border: `1px solid ${C.border}` },
    danger:   { background: 'transparent', color: C.red,   border: `1px solid rgba(248,113,113,0.3)` },
  };
  return (
    <button style={{ ...base, ...variants[variant] }} onClick={onClick} disabled={disabled || loading}>
      {loading ? <Spinner size={12} /> : Icon ? <Icon size={12} /> : null}
      {children}
    </button>
  );
}

function FormRow({ label, children, mono }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontFamily: C.mono, fontSize: 10, letterSpacing: '0.1em', color: C.text3, marginBottom: 6 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function Input({ value, onChange, placeholder, type = 'text', style: sx }) {
  return (
    <input
      type={type} value={value} onChange={onChange} placeholder={placeholder}
      style={{
        width: '100%', background: C.surface2, border: `1px solid ${C.border}`,
        borderRadius: 6, padding: '7px 10px', color: C.text1,
        fontFamily: C.mono, fontSize: 12, outline: 'none',
        boxSizing: 'border-box', ...sx,
      }}
    />
  );
}

function Select({ value, onChange, children, style: sx }) {
  return (
    <select
      value={value} onChange={onChange}
      style={{
        width: '100%', background: C.surface2, border: `1px solid ${C.border}`,
        borderRadius: 6, padding: '7px 10px', color: C.text1,
        fontFamily: C.mono, fontSize: 12, outline: 'none',
        boxSizing: 'border-box', ...sx,
      }}
    >{children}</select>
  );
}

// ── Tab: Channels ─────────────────────────────────────────────────────────────

function ChannelForm({ initial, onSave, onCancel, saving }) {
  const [type, setType]     = useState(initial?.channel_type || 'email');
  const [label, setLabel]   = useState(initial?.label || '');
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [sevs, setSevs]     = useState(initial?.severities || ['critical','high','medium','low','info']);
  const [cfg, setCfg]       = useState(initial?.config || {});

  const toggleSev = (s) =>
    setSevs(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);

  const setC = (k) => (e) => setCfg(prev => ({ ...prev, [k]: e.target.value }));

  return (
    <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 10, padding: 20, marginBottom: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <FormRow label="CHANNEL TYPE">
          <Select value={type} onChange={e => { setType(e.target.value); setCfg({}); }}>
            <option value="email">Email / SMTP</option>
            <option value="slack">Slack Webhook</option>
            <option value="telegram">Telegram Bot</option>
          </Select>
        </FormRow>
        <FormRow label="LABEL (optional)">
          <Input value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Ops Team Email" />
        </FormRow>
      </div>

      {type === 'email' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <FormRow label="SMTP HOST">
            <Input value={cfg.smtp_host||''} onChange={setC('smtp_host')} placeholder="smtp.gmail.com" />
          </FormRow>
          <FormRow label="SMTP PORT">
            <Input value={cfg.smtp_port||''} onChange={setC('smtp_port')} placeholder="587" />
          </FormRow>
          <FormRow label="USERNAME">
            <Input value={cfg.username||''} onChange={setC('username')} placeholder="you@example.com" />
          </FormRow>
          <FormRow label="PASSWORD">
            <Input value={cfg.password||''} onChange={setC('password')} type="password" placeholder="••••••••" />
          </FormRow>
          <FormRow label="FROM ADDRESS">
            <Input value={cfg.from_email||''} onChange={setC('from_email')} placeholder="alerts@example.com" />
          </FormRow>
          <FormRow label="TO ADDRESS(ES) — comma separated">
            <Input value={cfg.to_emails||''} onChange={setC('to_emails')} placeholder="ops@example.com" />
          </FormRow>
        </div>
      )}
      {type === 'slack' && (
        <FormRow label="WEBHOOK URL">
          <Input value={cfg.webhook_url||''} onChange={setC('webhook_url')} placeholder="https://hooks.slack.com/services/…" />
        </FormRow>
      )}
      {type === 'telegram' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <FormRow label="BOT TOKEN">
            <Input value={cfg.bot_token||''} onChange={setC('bot_token')} type="password" placeholder="123456:ABC…" />
          </FormRow>
          <FormRow label="CHAT ID">
            <Input value={cfg.chat_id||''} onChange={setC('chat_id')} placeholder="-1001234567890" />
          </FormRow>
        </div>
      )}

      <div style={{ marginBottom: 14 }}>
        <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.1em', color: C.text3, marginBottom: 8 }}>SEVERITY FILTER</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['critical','high','medium','low','info'].map(s => (
            <button key={s} onClick={() => toggleSev(s)} style={{
              padding: '3px 10px', borderRadius: 20, cursor: 'pointer',
              fontFamily: C.mono, fontSize: 10, letterSpacing: '0.08em',
              border: `1px solid ${SEV_COLOR[s]}66`,
              background: sevs.includes(s) ? `${SEV_COLOR[s]}22` : 'transparent',
              color: sevs.includes(s) ? SEV_COLOR[s] : C.text3,
            }}>{s.toUpperCase()}</button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <Btn onClick={() => onSave({ channel_type: type, label, enabled, severities: sevs, config: cfg })} loading={saving}>
          Save Channel
        </Btn>
        <Btn variant="ghost" onClick={onCancel}>Cancel</Btn>
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontFamily: C.ui, fontSize: 12, color: C.text2 }}>
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} style={{ accentColor: C.amber }} />
          Enabled
        </label>
      </div>
    </div>
  );
}

function ChannelCard({ ch, onEdit, onDelete, onTest }) {
  const [testing, setTesting]     = useState(false);
  const [testResult, setTestResult] = useState(null); // {ok, error?}
  const Meta = CHANNEL_META[ch.channel_type] || CHANNEL_META.email;
  const Icon = Meta.icon;

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const r = await onTest(ch.id);
      setTestResult(r);
    } catch (e) {
      setTestResult({ ok: false, error: e.message });
    } finally { setTesting(false); }
    setTimeout(() => setTestResult(null), 6000);
  };

  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderLeft: `3px solid ${ch.enabled ? C.amber : C.border}`,
      borderRadius: 10, padding: '16px 20px', marginBottom: 10,
      display: 'flex', alignItems: 'flex-start', gap: 16,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 8, flexShrink: 0,
        background: ch.enabled ? C.amberLow : C.surface2,
        border: `1px solid ${ch.enabled ? 'rgba(245,158,11,0.2)' : C.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={16} color={ch.enabled ? C.amber : C.text3} />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
          <span style={{ fontFamily: C.ui, fontSize: 14, fontWeight: 600, color: C.text1 }}>
            {ch.label || Meta.label}
          </span>
          <Pill color={ch.enabled ? C.amber : C.text3}>{ch.enabled ? 'ENABLED' : 'DISABLED'}</Pill>
          <Pill color={C.text3}>{ch.channel_type.toUpperCase()}</Pill>
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
          {(ch.severities || []).map(s => (
            <span key={s} style={{ fontFamily: C.mono, fontSize: 9, color: SEV_COLOR[s] || C.text3 }}>
              {s}
            </span>
          ))}
        </div>

        {ch.last_delivery && (
          <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
            Last delivery: {fmtTime(ch.last_delivery)}
          </div>
        )}

        {testResult && (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 6,
            fontFamily: C.mono, fontSize: 11,
            color: testResult.ok ? C.teal : C.red,
          }}>
            {testResult.ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
            {testResult.ok ? 'Test notification sent' : testResult.error || 'Send failed'}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
        <Btn small variant="ghost" onClick={handleTest} loading={testing} icon={Zap}>Test</Btn>
        <Btn small variant="ghost" onClick={() => onEdit(ch)} icon={Edit2} />
        <Btn small variant="danger" onClick={() => onDelete(ch.id)} icon={Trash2} />
      </div>
    </div>
  );
}

function ChannelsTab({ orgId }) {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing]   = useState(null);
  const [saving, setSaving]     = useState(false);

  const load = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try { setChannels(await notificationChannelsApi.list(orgId)); } catch { setChannels([]); }
    setLoading(false);
  }, [orgId]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (body) => {
    setSaving(true);
    try {
      if (editing) {
        await notificationChannelsApi.update(orgId, editing.id, body);
      } else {
        await notificationChannelsApi.create(orgId, body);
      }
      setShowForm(false); setEditing(null);
      await load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Remove this channel?')) return;
    await notificationChannelsApi.remove(orgId, id);
    await load();
  };

  const handleTest = (id) => notificationChannelsApi.test(orgId, id);

  const handleEdit = (ch) => { setEditing(ch); setShowForm(true); };

  return (
    <div>
      <SectionHeader
        title="Notification Channels"
        sub="Configure where alerts are delivered: email, Slack, or Telegram."
        action={
          !showForm && (
            <Btn icon={Plus} onClick={() => { setEditing(null); setShowForm(true); }}>Add Channel</Btn>
          )
        }
      />

      {showForm && (
        <ChannelForm
          initial={editing}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditing(null); }}
          saving={saving}
        />
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spinner size={20} /></div>
      ) : channels.length === 0 ? (
        <EmptyState icon={Bell} title="No channels configured" sub="Add a channel to start receiving alerts." />
      ) : (
        channels.map(ch => (
          <ChannelCard key={ch.id} ch={ch} onEdit={handleEdit} onDelete={handleDelete} onTest={handleTest} />
        ))
      )}
    </div>
  );
}

// ── Tab: Alert Rules ──────────────────────────────────────────────────────────

function RuleRow({ rule, onEdit, onDelete, onToggle }) {
  const isBuiltin = rule.builtin;
  return (
    <tr style={{ borderBottom: `1px solid ${C.borderDim}` }}>
      <td style={{ padding: '10px 12px', fontFamily: C.ui, fontSize: 13, color: C.text1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {isBuiltin && <Shield size={11} color={C.text3} />}
          {rule.name}
        </div>
      </td>
      <td style={{ padding: '10px 12px', fontFamily: C.mono, fontSize: 11, color: C.text2 }}>{rule.metric}</td>
      <td style={{ padding: '10px 12px', fontFamily: C.mono, fontSize: 12, color: C.amber }}>&gt; {rule.threshold}%</td>
      <td style={{ padding: '10px 12px' }}>
        <Pill color={SEV_COLOR[rule.severity] || C.text3}>{rule.severity?.toUpperCase()}</Pill>
      </td>
      <td style={{ padding: '10px 12px', fontFamily: C.mono, fontSize: 11, color: C.text3 }}>{rule.cooldown_minutes}m</td>
      <td style={{ padding: '10px 12px' }}>
        {isBuiltin ? (
          <Pill color={C.text3}>SYSTEM</Pill>
        ) : (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={rule.enabled ?? true} onChange={() => onToggle(rule)}
              style={{ accentColor: C.amber }} />
            <span style={{ fontFamily: C.ui, fontSize: 11, color: C.text3 }}>
              {rule.enabled ? 'on' : 'off'}
            </span>
          </label>
        )}
      </td>
      <td style={{ padding: '10px 12px' }}>
        {!isBuiltin && (
          <div style={{ display: 'flex', gap: 6 }}>
            <Btn small variant="ghost" icon={Edit2} onClick={() => onEdit(rule)} />
            <Btn small variant="danger" icon={Trash2} onClick={() => onDelete(rule.id)} />
          </div>
        )}
      </td>
    </tr>
  );
}

function RuleForm({ initial, onSave, onCancel, saving }) {
  const [name, setName]         = useState(initial?.name || '');
  const [metric, setMetric]     = useState(initial?.metric || 'cpu');
  const [threshold, setThreshold] = useState(initial?.threshold ?? 85);
  const [severity, setSeverity] = useState(initial?.severity || 'high');
  const [cooldown, setCooldown] = useState(initial?.cooldown_minutes ?? 5);
  const [enabled]               = useState(initial?.enabled ?? true);  // eslint-disable-line no-unused-vars

  return (
    <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 10, padding: 20, marginBottom: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        <FormRow label="RULE NAME">
          <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. CPU Spike" />
        </FormRow>
        <FormRow label="METRIC">
          <Select value={metric} onChange={e => setMetric(e.target.value)}>
            <option value="cpu">CPU</option>
            <option value="memory">Memory</option>
            <option value="disk">Disk</option>
          </Select>
        </FormRow>
        <FormRow label="THRESHOLD (%)">
          <Input type="number" value={threshold} onChange={e => setThreshold(Number(e.target.value))} />
        </FormRow>
        <FormRow label="SEVERITY">
          <Select value={severity} onChange={e => setSeverity(e.target.value)}>
            {['critical','high','medium','low','info'].map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
        </FormRow>
        <FormRow label="COOLDOWN (minutes)">
          <Input type="number" value={cooldown} onChange={e => setCooldown(Number(e.target.value))} />
        </FormRow>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <Btn loading={saving} onClick={() => onSave({ name, metric, threshold, severity, cooldown_minutes: cooldown, enabled })}>
          Save Rule
        </Btn>
        <Btn variant="ghost" onClick={onCancel}>Cancel</Btn>
      </div>
    </div>
  );
}

function RulesTab({ orgId }) {
  const [rules, setRules]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving]   = useState(false);

  const load = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try { setRules(await alertRulesApi.list(orgId)); } catch { setRules([]); }
    setLoading(false);
  }, [orgId]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (body) => {
    setSaving(true);
    try {
      if (editing) await alertRulesApi.update(orgId, editing.id, body);
      else         await alertRulesApi.create(orgId, body);
      setShowForm(false); setEditing(null);
      await load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this rule?')) return;
    await alertRulesApi.remove(orgId, id);
    await load();
  };

  const handleToggle = async (rule) => {
    await alertRulesApi.update(orgId, rule.id, { enabled: !rule.enabled });
    await load();
  };

  const allRules = [...BUILTIN_RULES, ...rules];

  return (
    <div>
      <SectionHeader
        title="Alert Rules"
        sub="System rules are read-only. Add custom rules to supplement built-in thresholds."
        action={!showForm && <Btn icon={Plus} onClick={() => { setEditing(null); setShowForm(true); }}>Add Rule</Btn>}
      />

      {showForm && (
        <RuleForm
          initial={editing}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditing(null); }}
          saving={saving}
        />
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spinner size={20} /></div>
      ) : (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}`, background: C.surface2 }}>
                {['Rule','Metric','Threshold','Severity','Cooldown','Status','Actions'].map(h => (
                  <th key={h} style={{
                    padding: '10px 12px', textAlign: 'left',
                    fontFamily: C.mono, fontSize: 10, letterSpacing: '0.1em',
                    color: C.text3, fontWeight: 500,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allRules.map(r => (
                <RuleRow key={r.id} rule={r}
                  onEdit={r => { setEditing(r); setShowForm(true); }}
                  onDelete={handleDelete}
                  onToggle={handleToggle}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Tab: History ──────────────────────────────────────────────────────────────

function HistoryTab({ orgId }) {
  const [logs, setLogs]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [filter, setFilter]     = useState({ status: '', channel_type: '' });

  const load = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      setLogs(await notificationLogsApi.list(orgId, {
        status:      filter.status      || undefined,
        channelType: filter.channel_type || undefined,
        limit: 100,
      }));
    } catch { setLogs([]); }
    setLoading(false);
  }, [orgId, filter]);

  useEffect(() => { load(); }, [load]);

  const delivered = logs.filter(l => l.status === 'sent').length;
  const failed    = logs.filter(l => l.status === 'failed').length;

  return (
    <div>
      <SectionHeader
        title="Notification History"
        sub="Delivery log for all dispatched alert and summary notifications."
        action={<Btn small variant="ghost" icon={RefreshCw} onClick={load}>Refresh</Btn>}
      />

      {/* Summary strip */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        <div style={{ background: C.tealLow, border: `1px solid rgba(45,212,191,0.2)`, borderRadius: 8, padding: '8px 16px',
          fontFamily: C.mono, fontSize: 12, color: C.teal }}>
          <CheckCircle size={11} style={{ display: 'inline', marginRight: 6 }} />
          {delivered} delivered
        </div>
        <div style={{ background: C.redLow, border: `1px solid rgba(248,113,113,0.2)`, borderRadius: 8, padding: '8px 16px',
          fontFamily: C.mono, fontSize: 12, color: C.red }}>
          <XCircle size={11} style={{ display: 'inline', marginRight: 6 }} />
          {failed} failed
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <Select value={filter.status} onChange={e => setFilter(p => ({ ...p, status: e.target.value }))} style={{ width: 140 }}>
          <option value="">All statuses</option>
          <option value="sent">Sent</option>
          <option value="failed">Failed</option>
        </Select>
        <Select value={filter.channel_type} onChange={e => setFilter(p => ({ ...p, channel_type: e.target.value }))} style={{ width: 160 }}>
          <option value="">All channels</option>
          <option value="email">Email</option>
          <option value="slack">Slack</option>
          <option value="telegram">Telegram</option>
        </Select>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spinner size={20} /></div>
      ) : logs.length === 0 ? (
        <EmptyState icon={Clock} title="No history yet" sub="Notifications will appear here once dispatched." />
      ) : (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}`, background: C.surface2 }}>
                {['Time','Type','Channel','Recipient','Status','Detail'].map(h => (
                  <th key={h} style={{
                    padding: '10px 12px', textAlign: 'left',
                    fontFamily: C.mono, fontSize: 10, letterSpacing: '0.1em', color: C.text3, fontWeight: 500,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id} style={{ borderBottom: `1px solid ${C.borderDim}` }}>
                  <td style={{ padding: '9px 12px', fontFamily: C.mono, fontSize: 11, color: C.text3 }}>{fmtTime(log.sent_at)}</td>
                  <td style={{ padding: '9px 12px' }}>
                    <Pill color={log.notification_type === 'alert' ? C.amber : C.teal}>
                      {(log.notification_type || 'alert').toUpperCase()}
                    </Pill>
                  </td>
                  <td style={{ padding: '9px 12px', fontFamily: C.mono, fontSize: 11, color: C.text2 }}>{log.channel_type}</td>
                  <td style={{ padding: '9px 12px', fontFamily: C.mono, fontSize: 11, color: C.text2, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.recipient || '—'}
                  </td>
                  <td style={{ padding: '9px 12px' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: C.mono, fontSize: 11,
                      color: log.status === 'sent' ? C.teal : C.red }}>
                      {log.status === 'sent' ? <CheckCircle size={11} /> : <XCircle size={11} />}
                      {log.status}
                    </span>
                  </td>
                  <td style={{ padding: '9px 12px', fontFamily: C.mono, fontSize: 10, color: C.text3, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.error || log.subject || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Tab: Daily Summary ────────────────────────────────────────────────────────

function DailySummaryTab({ orgId }) {
  const [sending, setSending]   = useState(false);
  const [result, setResult]     = useState(null);
  const [metrics, setMetrics]   = useState([]);
  const [mLoading, setMLoading] = useState(true);

  useEffect(() => {
    if (!orgId) return;
    setMLoading(true);
    metricsApi.getLatest(orgId)
      .then(d => setMetrics(Array.isArray(d) ? d : []))
      .catch(() => setMetrics([]))
      .finally(() => setMLoading(false));
  }, [orgId]);

  const handleSend = async () => {
    setSending(true); setResult(null);
    try {
      const r = await dailySummaryApi.send(orgId);
      setResult({ ok: true, msg: r?.message || 'Daily summary dispatched.' });
    } catch (e) {
      setResult({ ok: false, msg: e?.response?.data?.detail || e.message });
    }
    setSending(false);
    setTimeout(() => setResult(null), 8000);
  };

  // Aggregate across all agents
  const agg = metrics.reduce((acc, m) => {
    const snap = m.latest || m;
    if (snap.cpu_percent    != null) { acc.cpuSum    += snap.cpu_percent;    acc.cpuN++; }
    if (snap.memory_percent != null) { acc.memSum    += snap.memory_percent; acc.memN++; }
    if (snap.disk_percent   != null) { acc.diskSum   += snap.disk_percent;   acc.diskN++; }
    return acc;
  }, { cpuSum: 0, cpuN: 0, memSum: 0, memN: 0, diskSum: 0, diskN: 0 });

  const avgCpu  = agg.cpuN  ? agg.cpuSum  / agg.cpuN  : null;
  const avgMem  = agg.memN  ? agg.memSum  / agg.memN  : null;
  const avgDisk = agg.diskN ? agg.diskSum / agg.diskN : null;

  return (
    <div>
      <SectionHeader
        title="Daily Summary"
        sub="Send an on-demand summary of the last 24 h across all monitored agents."
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Left: controls */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <Calendar size={16} color={C.amber} />
            <span style={{ fontFamily: C.ui, fontSize: 14, fontWeight: 600, color: C.text1 }}>Schedule</span>
          </div>

          <div style={{ background: C.surface2, borderRadius: 8, padding: '12px 16px', marginBottom: 20 }}>
            <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.1em', color: C.text3, marginBottom: 6 }}>AUTOMATIC DISPATCH</div>
            <div style={{ fontFamily: C.ui, fontSize: 13, color: C.text2 }}>
              Daily summaries are automatically sent at <span style={{ color: C.amber, fontFamily: C.mono }}>08:00 UTC</span> each morning
              to all enabled channels.
            </div>
          </div>

          <div style={{ background: C.surface2, borderRadius: 8, padding: '12px 16px', marginBottom: 20 }}>
            <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.1em', color: C.text3, marginBottom: 6 }}>INCLUDED IN SUMMARY</div>
            <ul style={{ margin: 0, padding: '0 0 0 16px', fontFamily: C.ui, fontSize: 13, color: C.text2, lineHeight: 1.8 }}>
              <li>Average CPU / memory / disk across all agents</li>
              <li>Total alerts fired in the last 24 h</li>
              <li>Open vs resolved incident count</li>
              <li>Agent uptime and online / offline status</li>
            </ul>
          </div>

          <Btn icon={Send} onClick={handleSend} loading={sending} disabled={!orgId}>
            Send Summary Now
          </Btn>

          {result && (
            <div style={{
              marginTop: 14, display: 'flex', alignItems: 'center', gap: 8,
              fontFamily: C.mono, fontSize: 12,
              color: result.ok ? C.teal : C.red,
            }}>
              {result.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
              {result.msg}
            </div>
          )}
        </div>

        {/* Right: live metric preview */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <BarChart2 size={16} color={C.amber} />
            <span style={{ fontFamily: C.ui, fontSize: 14, fontWeight: 600, color: C.text1 }}>Current Snapshot</span>
            {mLoading && <Spinner />}
          </div>

          {mLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spinner size={20} /></div>
          ) : metrics.length === 0 ? (
            <EmptyState icon={Activity} title="No agents reporting" sub="Deploy a remote agent to see live metrics." small />
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 16 }}>
                {[
                  { label: 'AVG CPU',    val: avgCpu,  color: avgCpu  > 80 ? C.red : C.amber },
                  { label: 'AVG MEM',    val: avgMem,  color: avgMem  > 80 ? C.red : C.teal  },
                  { label: 'AVG DISK',   val: avgDisk, color: avgDisk > 85 ? C.red : C.text2 },
                ].map(({ label, val, color }) => (
                  <div key={label} style={{ background: C.surface2, borderRadius: 8, padding: '12px 14px' }}>
                    <div style={{ fontFamily: C.mono, fontSize: 9, letterSpacing: '0.1em', color: C.text3, marginBottom: 6 }}>{label}</div>
                    <div style={{ fontFamily: C.mono, fontSize: 20, color }}>{fmtPct(val)}</div>
                  </div>
                ))}
              </div>

              <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.08em', color: C.text3, marginBottom: 8 }}>
                AGENTS ({metrics.length})
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
                {metrics.map((m, i) => {
                  const snap = m.latest || m;
                  const label = m.agent_label || m.hostname || `Agent ${i + 1}`;
                  const cpu   = snap.cpu_percent;
                  const mem   = snap.memory_percent;
                  return (
                    <div key={m.agent_id || i} style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      background: C.surface3, borderRadius: 6, padding: '8px 12px',
                    }}>
                      <div style={{ width: 6, height: 6, borderRadius: '50%', background: cpu > 85 || mem > 80 ? C.red : C.teal, flexShrink: 0 }} />
                      <span style={{ flex: 1, fontFamily: C.ui, fontSize: 12, color: C.text2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {label}
                      </span>
                      <span style={{ fontFamily: C.mono, fontSize: 11, color: cpu > 85 ? C.red : C.text2 }}>CPU {fmtPct(cpu)}</span>
                      <span style={{ fontFamily: C.mono, fontSize: 11, color: mem > 80 ? C.red : C.text3 }}>MEM {fmtPct(mem)}</span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ icon: Icon, title, sub, small }) {
  return (
    <div style={{ textAlign: 'center', padding: small ? 20 : 48 }}>
      <Icon size={small ? 20 : 28} color={C.text3} style={{ marginBottom: 10 }} />
      <div style={{ fontFamily: C.ui, fontSize: small ? 13 : 15, color: C.text2, marginBottom: 4 }}>{title}</div>
      {sub && <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3 }}>{sub}</div>}
    </div>
  );
}

// ── Root component ────────────────────────────────────────────────────────────

const TABS = [
  { id: 'channels', label: 'Channels',      icon: Bell      },
  { id: 'rules',    label: 'Alert Rules',   icon: Shield    },
  { id: 'history',  label: 'History',       icon: Clock     },
  { id: 'summary',  label: 'Daily Summary', icon: Calendar  },
];

export default function NotificationSettings() {
  const { user } = useAuth();
  const orgId = user?.org_id || null;

  const [tab, setTab]         = useState('channels');
  const [stats, setStats]     = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    if (!orgId) return;
    Promise.all([
      notificationChannelsApi.list(orgId).catch(() => []),
      alertRulesApi.list(orgId).catch(() => []),
      notificationLogsApi.list(orgId, { limit: 200 }).catch(() => []),
    ]).then(([channels, rules, logs]) => {
      const active24h = logs.filter(l => {
        if (!l.sent_at) return false;
        return Date.now() - new Date(l.sent_at).getTime() < 86_400_000;
      });
      const sent24h   = active24h.filter(l => l.status === 'sent').length;
      const total24h  = active24h.length;
      setStats({
        activeChannels: channels.filter(c => c.enabled).length,
        totalRules:     BUILTIN_RULES.length + rules.length,
        delivered24h:   sent24h,
        successRate:    total24h > 0 ? Math.round((sent24h / total24h) * 100) : null,
      });
    }).finally(() => setStatsLoading(false));
  }, [orgId]);

  return (
    <div style={{ maxWidth: 1080, paddingBottom: 60 }}>
      {/* Page header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <Bell size={18} color={C.amber} />
          <h1 style={{ margin: 0, fontFamily: C.ui, fontSize: 22, fontWeight: 700, color: C.text1 }}>
            Notifications
          </h1>
        </div>
        <p style={{ margin: 0, fontFamily: C.ui, fontSize: 13, color: C.text3 }}>
          Manage alert channels, custom rules, delivery history, and daily digest settings.
        </p>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 28, flexWrap: 'wrap' }}>
        <StatCard icon={Bell}         label="ACTIVE CHANNELS" value={statsLoading ? '—' : stats?.activeChannels ?? 0} sub="email · slack · telegram" />
        <StatCard icon={Shield}       label="ALERT RULES"     value={statsLoading ? '—' : stats?.totalRules ?? 0}     sub={`${BUILTIN_RULES.length} system + custom`} color={C.teal} />
        <StatCard icon={CheckCircle}  label="DELIVERED 24H"   value={statsLoading ? '—' : stats?.delivered24h ?? 0}   sub="across all channels" color={C.teal} />
        <StatCard icon={Activity}     label="SUCCESS RATE"    value={statsLoading ? '—' : stats?.successRate != null ? `${stats.successRate}%` : '—'} sub="last 200 dispatches" color={stats?.successRate < 90 ? C.red : C.amber} />
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 24, borderBottom: `1px solid ${C.border}` }}>
        {TABS.map(({ id, label, icon: Icon }) => {
          const active = tab === id;
          return (
            <button key={id} onClick={() => setTab(id)} style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '9px 16px', cursor: 'pointer', background: 'none',
              border: 'none', borderBottom: active ? `2px solid ${C.amber}` : '2px solid transparent',
              marginBottom: -1,
              fontFamily: C.ui, fontSize: 13, fontWeight: active ? 600 : 400,
              color: active ? C.amber : C.text3,
              transition: 'color 0.15s',
            }}>
              <Icon size={13} />
              {label}
            </button>
          );
        })}
      </div>

      {/* Tab panels */}
      {tab === 'channels' && <ChannelsTab orgId={orgId} />}
      {tab === 'rules'    && <RulesTab    orgId={orgId} />}
      {tab === 'history'  && <HistoryTab  orgId={orgId} />}
      {tab === 'summary'  && <DailySummaryTab orgId={orgId} />}
    </div>
  );
}
