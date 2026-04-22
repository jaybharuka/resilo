/**
 * InfraHub.js — Unified Infrastructure Command Center
 * Merges Fleet (monitoring agents) + Team (users) into one page.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import AgentDashboard from './AgentDashboard';
import { userApi } from '../services/api';
import {
  agentsApi, metricsApi, alertsApi, wmiApi,
  getOrgId,
} from '../services/resiloApi';
import { useAuth } from '../context/AuthContext';
import {
  Server, Users, WifiOff, AlertTriangle, CheckCircle2, RefreshCw,
  Plus, Copy, Terminal, Key, UserPlus, Trash2,
  Activity, Layers, Eye, EyeOff,
  Zap, Globe, Clock, ArrowUpRight, Monitor, Wifi,
  Search, ChevronDown, Square, CheckSquare, X,
} from 'lucide-react';

// ─── Design Tokens ────────────────────────────────────────────────────────────
const F = {
  display: "'Bebas Neue', sans-serif",
  mono:    "'IBM Plex Mono', monospace",
  ui:      "'Outfit', sans-serif",
};

const C = {
  bg:       'rgb(10, 9, 7)',
  panel:    'rgb(18, 17, 13)',
  panelAlt: 'rgb(22, 21, 17)',
  border:   'rgba(48,44,36,0.9)',
  borderLt: 'rgba(72,66,52,0.6)',
  text:     '#F5F0E8',
  sub:      '#A89F8C',
  muted:    '#6B6357',
  dim:      '#3A342D',
  amber:    '#F59E0B',
  amberLt:  '#FCD34D',
  teal:     '#2DD4BF',
  red:      '#F87171',
  blue:     '#60A5FA',
  green:    '#34D399',
  online:   '#2DD4BF',
  warning:  '#F59E0B',
  offline:  '#6B6357',
  critical: '#F87171',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
const mono  = (extra = {}) => ({ fontFamily: F.mono,    ...extra });
const disp  = (extra = {}) => ({ fontFamily: F.display, ...extra });
const ui    = (extra = {}) => ({ fontFamily: F.ui,      ...extra });

function deriveStatus(lastSeen) {
  if (!lastSeen) return 'offline';
  const s = (Date.now() - new Date(lastSeen).getTime()) / 1000;
  if (s <= 30)  return 'online';
  if (s <= 120) return 'warning';
  return 'offline';
}

function relTime(ts) {
  if (!ts) return 'never';
  const d = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (d < 5)    return 'just now';
  if (d < 60)   return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

function metricColor(v) {
  if (v == null) return C.muted;
  if (v > 85) return C.red;
  if (v > 65) return C.amber;
  return C.teal;
}

function getCurrentUser() {
  try { return JSON.parse(localStorage.getItem('aiops:user') || 'null'); } catch { return null; }
}

function getToken() {
  try { return localStorage.getItem('aiops:token') || ''; } catch { return ''; }
}

// ─── Primitive UI ─────────────────────────────────────────────────────────────
function Pulse({ color = C.teal, size = 8 }) {
  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{
        position: 'absolute',
        width: size * 2.2, height: size * 2.2, borderRadius: '50%',
        background: color, opacity: 0.25,
        animation: 'hub-pulse 2s cubic-bezier(0.4,0,0.6,1) infinite',
      }} />
      <span style={{ width: size, height: size, borderRadius: '50%', background: color, position: 'relative', flexShrink: 0 }} />
    </span>
  );
}

function StatusDot({ status }) {
  const color = status === 'online' ? C.teal : status === 'warning' ? C.amber : C.muted;
  return status === 'online'
    ? <Pulse color={color} size={7} />
    : <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block', flexShrink: 0 }} />;
}

function Tag({ children, color = C.teal }) {
  return (
    <span style={{
      ...mono(), fontSize: '9px', letterSpacing: '0.08em',
      color, background: `${color}18`, border: `1px solid ${color}30`,
      padding: '2px 7px', borderRadius: 6, whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

function Btn({ children, onClick, variant = 'primary', size = 'md', disabled, style: sx }) {
  const sizes = { sm: { padding: '5px 11px', fontSize: '9px' }, md: { padding: '7px 14px', fontSize: '10px' }, lg: { padding: '10px 20px', fontSize: '11px' } };
  const vars = {
    primary: { bg: `${C.amber}18`, border: `1px solid ${C.amber}40`, color: C.amber },
    ghost:   { bg: 'transparent',  border: `1px solid ${C.border}`,   color: C.sub  },
    danger:  { bg: `${C.red}14`,   border: `1px solid ${C.red}30`,    color: C.red  },
    teal:    { bg: `${C.teal}14`,  border: `1px solid ${C.teal}30`,   color: C.teal },
  };
  const v = vars[variant] || vars.primary;
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      ...mono(), ...sizes[size],
      letterSpacing: '0.08em', cursor: disabled ? 'not-allowed' : 'pointer',
      borderRadius: 7, opacity: disabled ? 0.45 : 1,
      whiteSpace: 'nowrap', transition: 'all 0.15s',
      ...v, ...sx,
    }}>
      {children}
    </button>
  );
}

function MetricBar({ label, value }) {
  const color = metricColor(value);
  const pct = value != null ? Math.min(100, Math.max(0, value)) : 0;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ ...mono(), fontSize: '9px', color: C.muted, letterSpacing: '0.07em' }}>{label}</span>
        <span style={{ ...mono(), fontSize: '10px', color: value != null ? C.sub : C.muted }}>
          {value != null ? `${Math.round(value)}%` : 'N/A'}
        </span>
      </div>
      <div style={{ height: 3, borderRadius: 2, background: C.border, overflow: 'hidden', position: 'relative' }}>
        <div style={{
          position: 'absolute', left: 0, top: 0, height: '100%',
          width: `${pct}%`, background: color, borderRadius: 2,
          transition: 'width 0.7s ease',
          boxShadow: `0 0 6px ${color}60`,
        }} />
      </div>
    </div>
  );
}

function Skeleton({ w = '100%', h = 14, r = 4 }) {
  return <div className="animate-pulse" style={{ width: w, height: h, borderRadius: r, background: 'rgba(42,40,32,0.4)' }} />;
}

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard?.writeText(text).catch(() => {}); setCopied(true); setTimeout(() => setCopied(false), 2000); }} style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      ...mono(), fontSize: '9px', letterSpacing: '0.06em',
      background: 'transparent', border: 'none', cursor: 'pointer',
      color: copied ? C.teal : C.muted, transition: 'color 0.2s', padding: '4px 6px',
    }}>
      <Copy size={11} /> {copied ? 'COPIED' : 'COPY'}
    </button>
  );
}

// ─── Agent Card ───────────────────────────────────────────────────────────────
function AgentCard({ agent, users, onDelete, onClick, selected, onSelect }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting,   setDeleting]   = useState(false);
  const status = deriveStatus(agent.last_seen);
  const sc = status === 'online' ? C.teal : status === 'warning' ? C.amber : C.muted;
  const m = agent.metrics || {};
  const cpu  = m.cpu  ?? m.cpu_percent  ?? null;
  const mem  = m.memory ?? m.memory_percent ?? null;
  const disk = m.disk ?? m.disk_percent ?? null;
  const owner = users?.find(u => u.id === agent.owner_user_id);
  const osInfo = m.os || agent.os || null;
  const isWmi  = agent.platform_info?.source === 'wmi' || agent.source === 'wmi';

  return (
    <div
      onClick={() => !confirming && onClick?.(agent)}
      style={{
        background: selected ? `${C.amber}08` : C.panel,
        border: `1px solid ${selected ? C.amber + '50' : C.border}`,
        borderRadius: 10, overflow: 'hidden',
        transition: 'border-color 0.2s, box-shadow 0.2s, background 0.15s',
        cursor: onClick ? 'pointer' : 'default',
      }}
      onMouseEnter={e => { if (!selected) { e.currentTarget.style.borderColor = `${sc}40`; e.currentTarget.style.boxShadow = `0 0 20px ${sc}12`; }}}
      onMouseLeave={e => { if (!selected) { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = 'none'; }}}>
      {/* Header */}
      <div style={{ padding: '10px 14px 10px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 9 }}>
        {onSelect && (
          <button
            onClick={e => { e.stopPropagation(); onSelect(agent.id); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: selected ? C.amber : C.dim, flexShrink: 0, display: 'flex', transition: 'color 0.15s' }}
          >
            {selected ? <CheckSquare size={14} /> : <Square size={14} />}
          </button>
        )}
        <StatusDot status={status} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ ...ui({ fontWeight: 600, fontSize: '13px', color: C.text }), overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {agent.label || agent.id}
          </div>
          {owner && <div style={{ ...mono({ fontSize: '9px', color: C.muted }) }}>{owner.username}</div>}
        </div>
        {isWmi && <Tag color={C.blue}>WMI</Tag>}
        <Tag color={sc}>{status.toUpperCase()}</Tag>
      </div>

      {/* Metrics */}
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <MetricBar label="CPU"  value={cpu} />
        <MetricBar label="MEM"  value={mem} />
        <MetricBar label="DISK" value={disk} />
      </div>

      {/* Footer */}
      <div style={{
        padding: '9px 16px', borderTop: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'rgba(0,0,0,0.2)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          {osInfo && <span style={{ ...mono({ fontSize: '9px', color: C.muted }) }}>{osInfo}</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Clock size={9} color={C.muted} />
          <span style={{ ...mono({ fontSize: '9px', color: C.muted }) }}>{relTime(agent.last_seen)}</span>
          {onDelete && (
            confirming ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }} onClick={e => e.stopPropagation()}>
                <span style={{ ...mono({ fontSize: '9px', color: C.red }) }}>DELETE?</span>
                <button
                  disabled={deleting}
                  onClick={async (e) => { e.stopPropagation(); setDeleting(true); await onDelete(agent.id); }}
                  style={{ background: `${C.red}18`, border: `1px solid ${C.red}35`, color: C.red, borderRadius: 5, padding: '2px 8px', cursor: 'pointer', ...mono({ fontSize: '9px' }) }}
                >
                  {deleting ? '…' : 'YES'}
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.muted, borderRadius: 5, padding: '2px 8px', cursor: 'pointer', ...mono({ fontSize: '9px' }) }}
                >
                  NO
                </button>
              </div>
            ) : (
              <button
                onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
                title="Delete agent"
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.dim, padding: '2px 4px', display: 'flex', alignItems: 'center', transition: 'color 0.15s' }}
                onMouseEnter={e => { e.currentTarget.style.color = C.red; }}
                onMouseLeave={e => { e.currentTarget.style.color = C.dim; }}
              >
                <Trash2 size={12} />
              </button>
            )
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Register Agent Modal ─────────────────────────────────────────────────────
function RegisterModal({ orgId, onClose, onCreated }) {
  const [label, setLabel]     = useState('');
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState('');
  const [created, setCreated] = useState(null);
  const [showKey, setShowKey] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const submit = async () => {
    if (!label.trim()) return;
    setBusy(true); setError('');
    try {
      const res = await agentsApi.create(orgId, label.trim());
      setCreated(res);
      onCreated?.();
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to register');
    } finally { setBusy(false); }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000, display: 'flex',
      alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)',
    }} onClick={() => !created && onClose()}>
      <div style={{
        background: C.panel, border: `1px solid ${C.border}`,
        borderRadius: 14, padding: '28px', width: '100%', maxWidth: 460,
        display: 'flex', flexDirection: 'column', gap: 20,
        boxShadow: '0 32px 80px rgba(0,0,0,0.7)',
      }} onClick={e => e.stopPropagation()}>

        {!created ? (
          <>
            {/* Form */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 9, background: `${C.teal}14`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Plus size={16} color={C.teal} />
              </div>
              <div>
                <div style={{ ...mono({ fontSize: '11px', letterSpacing: '0.1em', color: C.sub }) }}>REGISTER MONITORING AGENT</div>
                <div style={{ ...ui({ fontSize: '11px', color: C.muted }), marginTop: 2 }}>Creates an API key for a new monitored host</div>
              </div>
            </div>

            <div>
              <label style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted, display: 'block', marginBottom: 7 }) }}>AGENT LABEL</label>
              <input
                ref={inputRef}
                value={label}
                onChange={e => setLabel(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onClose(); }}
                placeholder="e.g. prod-web-01, staging-db, my-laptop"
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: 'rgba(42,40,32,0.5)', border: `1px solid ${C.border}`,
                  borderRadius: 8, padding: '10px 13px',
                  ...ui({ fontSize: '13px', color: C.text }), outline: 'none',
                  transition: 'border-color 0.15s',
                }}
                onFocus={e => { e.target.style.borderColor = `${C.teal}50`; }}
                onBlur={e => { e.target.style.borderColor = C.border; }}
              />
            </div>

            {error && (
              <div style={{ ...mono({ fontSize: '10px', color: C.red }), background: `${C.red}10`, border: `1px solid ${C.red}20`, borderRadius: 7, padding: '8px 12px' }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn variant="ghost" onClick={onClose}>CANCEL</Btn>
              <Btn variant="teal" disabled={!label.trim() || busy} onClick={submit}>
                <Server size={11} /> {busy ? 'REGISTERING…' : 'REGISTER AGENT'}
              </Btn>
            </div>
          </>
        ) : (
          <>
            {/* Key reveal */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <CheckCircle2 size={22} color={C.teal} />
              <div>
                <div style={{ ...mono({ fontSize: '11px', letterSpacing: '0.1em', color: C.teal }) }}>AGENT REGISTERED</div>
                <div style={{ ...ui({ fontSize: '11px', color: C.muted }), marginTop: 2 }}>{created.label}</div>
              </div>
            </div>

            <div style={{ background: `${C.amber}0c`, border: `1px solid ${C.amber}25`, borderRadius: 8, padding: '10px 14px', ...ui({ fontSize: '12px', color: C.amber }) }}>
              ⚠ Copy your API key now. It will <strong>not</strong> be shown again after closing.
            </div>

            {/* API Key */}
            <div>
              <div style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted, marginBottom: 7 }) }}>API KEY</div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'rgba(0,0,0,0.35)', border: `1px solid ${C.teal}30`,
                borderRadius: 8, padding: '10px 14px',
                ...mono({ fontSize: '11px', color: C.teal }), wordBreak: 'break-all',
              }}>
                <Key size={12} color={C.teal} style={{ flexShrink: 0 }} />
                <span style={{ flex: 1, userSelect: 'all', filter: showKey ? 'none' : 'blur(5px)', transition: 'filter 0.2s' }}>
                  {created.api_key}
                </span>
                <button onClick={() => setShowKey(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.muted, padding: 4 }}>
                  {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
                <CopyBtn text={created.api_key} />
              </div>
            </div>

            {/* Install command */}
            <div>
              <div style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted, marginBottom: 7 }) }}>INSTALL COMMAND</div>
              <div style={{
                background: 'rgba(0,0,0,0.35)', border: `1px solid ${C.border}`,
                borderRadius: 8, padding: '10px 14px',
                ...mono({ fontSize: '10px', color: C.sub }), lineHeight: 1.7,
                wordBreak: 'break-all', userSelect: 'all', position: 'relative',
              }}>
                <div style={{ position: 'absolute', top: 8, right: 10 }}><CopyBtn text={created.install_cmd} /></div>
                {created.install_cmd}
              </div>
            </div>

            <Btn variant="ghost" onClick={onClose} style={{ alignSelf: 'flex-end' }}>
              DONE
            </Btn>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Invite User Modal ────────────────────────────────────────────────────────
function InviteModal({ onClose }) {
  const [form, setForm]   = useState({ email: '', username: '', full_name: '', password: '', role: 'employee' });
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState('');
  const [done, setDone]   = useState(false);

  const submit = async () => {
    if (!form.email || !form.password || !form.username) { setError('Email, username and password are required'); return; }
    setBusy(true); setError('');
    try {
      await userApi.create({ ...form, must_change_password: false });
      setDone(true);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.response?.data?.error || e?.message || 'Failed to create user');
    } finally { setBusy(false); }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000, display: 'flex',
      alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)',
    }} onClick={onClose}>
      <div style={{
        background: C.panel, border: `1px solid ${C.border}`,
        borderRadius: 14, padding: '28px', width: '100%', maxWidth: 420,
        display: 'flex', flexDirection: 'column', gap: 18,
        boxShadow: '0 32px 80px rgba(0,0,0,0.7)',
      }} onClick={e => e.stopPropagation()}>

        {!done ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 9, background: `${C.amber}14`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <UserPlus size={16} color={C.amber} />
              </div>
              <div style={{ ...mono({ fontSize: '11px', letterSpacing: '0.1em', color: C.sub }) }}>ADD TEAM MEMBER</div>
            </div>

            {[
              { key: 'full_name', label: 'FULL NAME', placeholder: 'Jane Smith', type: 'text' },
              { key: 'username',  label: 'USERNAME',  placeholder: 'jsmith',     type: 'text' },
              { key: 'email',     label: 'EMAIL',     placeholder: 'jane@co.com',type: 'email' },
              { key: 'password',  label: 'TEMP PASSWORD', placeholder: '••••••••', type: 'password' },
            ].map(({ key, label, placeholder, type }) => (
              <div key={key}>
                <label style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted, display: 'block', marginBottom: 6 }) }}>{label}</label>
                <input type={type} value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                  placeholder={placeholder}
                  style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(42,40,32,0.5)', border: `1px solid ${C.border}`, borderRadius: 8, padding: '9px 12px', ...ui({ fontSize: '13px', color: C.text }), outline: 'none' }}
                  onFocus={e => { e.target.style.borderColor = `${C.amber}50`; }}
                  onBlur={e => { e.target.style.borderColor = C.border; }}
                />
              </div>
            ))}

            <div>
              <label style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted, display: 'block', marginBottom: 6 }) }}>ROLE</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} style={{
                width: '100%', background: 'rgba(42,40,32,0.5)', border: `1px solid ${C.border}`, borderRadius: 8,
                padding: '9px 12px', ...ui({ fontSize: '13px', color: C.text }), outline: 'none',
              }}>
                {['employee','manager','admin'].map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase()+r.slice(1)}</option>)}
              </select>
            </div>

            {error && <div style={{ ...mono({ fontSize: '10px', color: C.red }), background: `${C.red}10`, borderRadius: 7, padding: '8px 12px' }}>{error}</div>}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn variant="ghost" onClick={onClose}>CANCEL</Btn>
              <Btn disabled={busy} onClick={submit}><UserPlus size={11} /> {busy ? 'ADDING…' : 'ADD USER'}</Btn>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center', padding: '12px 0' }}>
            <CheckCircle2 size={40} color={C.teal} />
            <div style={{ ...mono({ fontSize: '12px', letterSpacing: '0.1em', color: C.teal }) }}>USER ADDED</div>
            <div style={{ ...ui({ fontSize: '13px', color: C.sub, textAlign: 'center' })}}>
              {form.full_name || form.username} has been added with the {form.role} role.
            </div>
            <Btn variant="ghost" onClick={onClose}>CLOSE</Btn>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Connection Guide ─────────────────────────────────────────────────────────
function ConnectGuide({ orgId, onRegister }) {
  const steps = [
    {
      num: '01', icon: Key, color: C.amber,
      title: 'Register an Agent',
      desc: 'Click "Add Agent" to generate a unique API key for the machine you want to monitor. The key is shown once — save it immediately.',
      action: <Btn variant="primary" onClick={onRegister}><Plus size={11} /> ADD AGENT</Btn>,
    },
    {
      num: '02', icon: Terminal, color: C.teal,
      title: 'Run the Agent Script',
      desc: 'Copy the install command from the registration modal and run it on the target machine. Python 3.8+ and psutil are required.',
      code: 'pip install psutil requests\npython app/integrations/remote_agent.py',
    },
    {
      num: '03', icon: Activity, color: C.blue,
      title: 'Watch Metrics Flow In',
      desc: 'The agent will start reporting CPU, memory, disk, and network metrics every 10 seconds. It will appear in the Fleet tab as Online.',
    },
    {
      num: '04', icon: Globe, color: C.green,
      title: 'Set Up Alerts',
      desc: 'Head to the Alerts tab in the main Devices page to configure threshold alerts (e.g. CPU > 80%) and notification channels.',
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ ...mono({ fontSize: '10px', letterSpacing: '0.12em', color: C.muted }), marginBottom: 4 }}>
        HOW TO CONNECT A MONITORING AGENT
      </div>
      {steps.map((s, i) => (
        <div key={i} style={{
          background: C.panel, border: `1px solid ${C.border}`,
          borderRadius: 10, padding: '18px 20px',
          display: 'flex', gap: 16, alignItems: 'flex-start',
          transition: 'border-color 0.2s',
        }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = `${s.color}40`; }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10, flexShrink: 0,
            background: `${s.color}14`, border: `1px solid ${s.color}25`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <s.icon size={17} color={s.color} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
              <span style={{ ...mono({ fontSize: '9px', color: s.color, letterSpacing: '0.1em' }) }}>{s.num}</span>
              <span style={{ ...ui({ fontSize: '14px', fontWeight: 600, color: C.text }) }}>{s.title}</span>
            </div>
            <p style={{ ...ui({ fontSize: '12px', color: C.sub, lineHeight: 1.6 }), margin: '0 0 10px' }}>{s.desc}</p>
            {s.code && (
              <div style={{
                background: 'rgba(0,0,0,0.4)', border: `1px solid ${C.border}`, borderRadius: 7,
                padding: '10px 14px', ...mono({ fontSize: '10px', color: C.sub }), lineHeight: 1.8,
                position: 'relative', display: 'flex', alignItems: 'flex-start', gap: 8,
              }}>
                <Terminal size={11} color={C.muted} style={{ marginTop: 2, flexShrink: 0 }} />
                <pre style={{ margin: 0, ...mono({ fontSize: '10px' }), whiteSpace: 'pre-wrap', flex: 1 }}>{s.code}</pre>
                <CopyBtn text={s.code} />
              </div>
            )}
            {s.action && s.action}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── User Row ─────────────────────────────────────────────────────────────────
function UserRow({ user, onToggle, onRoleChange, onDelete, isMe, selected, onSelect }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting,   setDeleting]   = useState(false);
  const [roleChanging, setRoleChanging] = useState(false);
  const roleColors = { admin: C.red, manager: C.amber, employee: C.teal };
  const rc = roleColors[user.role] || C.sub;
  const initials = (user.full_name || user.username || 'U').split(' ').map(w => w[0]).join('').slice(0,2).toUpperCase();

  const handleRoleChange = async (newRole) => {
    if (newRole === user.role || !onRoleChange) return;
    setRoleChanging(true);
    await onRoleChange(user, newRole);
    setRoleChanging(false);
  };

  return (
    <tr
      style={{ borderBottom: `1px solid ${C.border}`, transition: 'background 0.15s', background: selected ? `${C.amber}06` : 'transparent' }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = 'rgba(42,40,32,0.2)'; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = 'transparent'; }}>
      {/* Bulk checkbox */}
      {onSelect && (
        <td style={{ padding: '0 4px 0 12px', width: 28 }}>
          <button onClick={() => onSelect(user.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: selected ? C.amber : C.dim, display: 'flex', padding: 4 }}>
            {selected ? <CheckSquare size={14} /> : <Square size={14} />}
          </button>
        </td>
      )}
      {/* Avatar + Name */}
      <td style={{ padding: '10px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8, flexShrink: 0,
            background: `${rc}14`, border: `1px solid ${rc}25`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            ...mono({ fontSize: '11px', color: rc }),
          }}>{initials}</div>
          <div>
            <div style={{ ...ui({ fontSize: '13px', fontWeight: 500, color: C.text }) }}>
              {user.full_name || user.username}
              {isMe && <span style={{ ...mono({ fontSize: '8px', color: C.amber }), marginLeft: 6, padding: '1px 5px', background: `${C.amber}14`, borderRadius: 4 }}>YOU</span>}
            </div>
            <div style={{ ...mono({ fontSize: '10px', color: C.muted }) }}>{user.email}</div>
          </div>
        </div>
      </td>
      {/* Role — inline select */}
      <td style={{ padding: '10px 8px' }}>
        {isMe ? (
          <Tag color={rc}>{(user.role || 'USER').toUpperCase()}</Tag>
        ) : (
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <select
              value={user.role || 'employee'}
              disabled={roleChanging}
              onChange={e => handleRoleChange(e.target.value)}
              style={{
                ...mono({ fontSize: '9px', letterSpacing: '0.07em' }),
                background: `${rc}14`, border: `1px solid ${rc}28`,
                color: rc, borderRadius: 5, padding: '3px 20px 3px 7px',
                cursor: 'pointer', appearance: 'none', outline: 'none',
                opacity: roleChanging ? 0.5 : 1,
              }}
            >
              <option value="admin">ADMIN</option>
              <option value="manager">MANAGER</option>
              <option value="employee">EMPLOYEE</option>
            </select>
            <ChevronDown size={9} color={rc} style={{ position: 'absolute', right: 5, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
          </div>
        )}
      </td>
      {/* Status */}
      <td style={{ padding: '10px 8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: user.is_active !== false ? C.teal : C.muted, display: 'inline-block' }} />
          <span style={{ ...mono({ fontSize: '9px', color: C.sub, letterSpacing: '0.06em' }) }}>
            {user.is_active !== false ? 'ACTIVE' : 'INACTIVE'}
          </span>
        </div>
      </td>
      {/* Last login */}
      <td style={{ padding: '10px 8px', ...mono({ fontSize: '9px', color: C.muted }) }}>
        {user.last_login ? relTime(user.last_login) : <span style={{ color: C.dim }}>never</span>}
      </td>
      {/* Actions */}
      <td style={{ padding: '10px 16px', textAlign: 'right' }}>
        {!isMe && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
            <Btn variant={user.is_active !== false ? 'ghost' : 'teal'} size="sm" onClick={() => onToggle(user)}>
              {user.is_active !== false ? 'DEACTIVATE' : 'ACTIVATE'}
            </Btn>
            {onDelete && (
              confirming ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ ...mono({ fontSize: '9px', color: C.red }) }}>DELETE?</span>
                  <button disabled={deleting} onClick={async () => { setDeleting(true); await onDelete(user.id); }}
                    style={{ background: `${C.red}18`, border: `1px solid ${C.red}35`, color: C.red, borderRadius: 5, padding: '2px 8px', cursor: 'pointer', ...mono({ fontSize: '9px' }) }}>
                    {deleting ? '…' : 'YES'}
                  </button>
                  <button onClick={() => setConfirming(false)}
                    style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.muted, borderRadius: 5, padding: '2px 8px', cursor: 'pointer', ...mono({ fontSize: '9px' }) }}>
                    NO
                  </button>
                </div>
              ) : (
                <button onClick={() => setConfirming(true)} title="Delete user"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.dim, padding: '4px', display: 'flex', alignItems: 'center', transition: 'color 0.15s' }}
                  onMouseEnter={e => { e.currentTarget.style.color = C.red; }}
                  onMouseLeave={e => { e.currentTarget.style.color = C.dim; }}>
                  <Trash2 size={13} />
                </button>
              )
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

// ─── WMI Row (inline test result + inline delete confirm) ─────────────────────
function WMIRow({ target: t, orgId, onDelete, onRefresh }) {
  const [testing,    setTesting]    = useState(false);
  const [testResult, setTestResult] = useState(null); // { ok, text }
  const [confirming, setConfirming] = useState(false);
  const [deleting,   setDeleting]   = useState(false);
  const sc = t.last_status === 'ok' ? C.teal : t.last_status === 'pending' ? C.amber : C.red;

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const r = await wmiApi.test(orgId, t.id);
      setTestResult({ ok: r.success, text: r.message || (r.success ? 'Connected' : 'Failed') });
      onRefresh();
    } catch (e) {
      setTestResult({ ok: false, text: e?.response?.data?.detail || 'Test failed' });
    } finally { setTesting(false); }
    setTimeout(() => setTestResult(null), 6000);
  };

  const handleDelete = async () => {
    setDeleting(true);
    try { await wmiApi.remove(orgId, t.id); onDelete(t.id); }
    catch (e) { console.error(e); setDeleting(false); setConfirming(false); }
  };

  return (
    <tr className="hub-row" style={{ borderBottom: `1px solid ${C.border}20` }}>
      <td style={{ padding: '10px 16px' }}>
        <span style={{
          ...mono({ fontSize: '9px', letterSpacing: '0.08em' }),
          color: sc, background: sc + '18', border: `1px solid ${sc}30`,
          padding: '2px 7px', borderRadius: 5,
        }}>{(t.last_status || 'pending').toUpperCase()}</span>
      </td>
      <td style={{ padding: '10px 16px', ...ui({ fontSize: '13px', color: C.text }) }}>{t.label}</td>
      <td style={{ padding: '10px 16px', ...mono({ fontSize: '10px', color: C.sub }) }}>{t.host}:{t.port}</td>
      <td style={{ padding: '10px 16px', ...mono({ fontSize: '10px', color: C.muted }) }}>{relTime(t.last_polled)}</td>
      <td style={{ padding: '10px 16px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <Btn variant="ghost" size="sm" onClick={handleTest} disabled={testing}>
              {testing
                ? <RefreshCw size={9} style={{ animation: 'spin 1s linear infinite' }} />
                : <><Wifi size={10} /> TEST</>}
            </Btn>
            {confirming ? (
              <>
                <span style={{ ...mono({ fontSize: '9px', color: C.red }) }}>REMOVE?</span>
                <Btn variant="danger" size="sm" onClick={handleDelete} disabled={deleting}>
                  {deleting ? '…' : 'YES'}
                </Btn>
                <Btn variant="ghost" size="sm" onClick={() => setConfirming(false)}>NO</Btn>
              </>
            ) : (
              <Btn variant="danger" size="sm" onClick={() => setConfirming(true)}>
                <Trash2 size={10} />
              </Btn>
            )}
          </div>
          {testResult && (
            <span style={{ ...mono({ fontSize: '9px', color: testResult.ok ? C.teal : C.red }), letterSpacing: '0.04em' }}>
              {testResult.ok ? '✓' : '✗'} {testResult.text}
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── WMI Add Machine Modal ────────────────────────────────────────────────────
function WMIModal({ orgId, onClose, onCreated }) {
  // step: 'idle' | 'generating' | 'waiting' | 'done' | 'expired' | 'error'
  const [step,       setStep]     = useState('idle');
  const [invite,     setInvite]   = useState(null);   // { invite_id, connect_command, expires_at }
  const [result,     setResult]   = useState(null);   // { machine_label, registered_agent_id }
  const [copied,     setCopied]   = useState(false);
  const [error,      setError]    = useState('');
  const [countdown,  setCountdown] = useState(0);     // seconds remaining
  const pollRef  = useRef(null);
  const timerRef = useRef(null);

  // Cleanup on unmount
  useEffect(() => () => {
    clearInterval(pollRef.current);
    clearInterval(timerRef.current);
  }, []);

  const generate = async () => {
    setStep('generating'); setError('');
    try {
      const data = await wmiApi.createInvite(orgId);
      setInvite(data);
      const expMs = new Date(data.expires_at).getTime();
      setCountdown(Math.max(0, Math.round((expMs - Date.now()) / 1000)));
      setStep('waiting');

      setCountdown(0);
    } catch (e) {
      setStep('error');
      setError(e?.response?.data?.detail || e?.message || 'Failed to generate invite');
    }
  };

  const copyCmd = () => {
    if (!invite?.connect_command) return;
    navigator.clipboard.writeText(invite.connect_command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const reset = () => {
    clearInterval(pollRef.current);
    clearInterval(timerRef.current);
    setStep('idle'); setInvite(null); setResult(null); setError(''); setCopied(false); setCountdown(0);
  };

  const fmtCountdown = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000, display: 'flex',
      alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(6px)',
    }} onClick={() => step !== 'waiting' && onClose()}>
      <div style={{
        background: C.panel, border: `1px solid ${C.border}`,
        borderRadius: 16, padding: '28px 30px', width: '100%', maxWidth: 540,
        display: 'flex', flexDirection: 'column', gap: 22,
        boxShadow: '0 40px 100px rgba(0,0,0,0.75)',
      }} onClick={e => e.stopPropagation()}>

        {/* ── Header ── */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 11, flexShrink: 0,
            background: `linear-gradient(135deg, ${C.blue}20, ${C.teal}15)`,
            border: `1px solid ${C.blue}30`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Monitor size={18} color={C.blue} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ ...mono({ fontSize: '11px', letterSpacing: '0.12em', color: C.blue }) }}>
              ADD WINDOWS MACHINE
            </div>
            <div style={{ ...ui({ fontSize: '12px', color: C.sub, marginTop: 3, lineHeight: 1.5 }) }}>
              Zero-input agentless onboarding — user runs one command, machine registers automatically.
            </div>
          </div>
          {step !== 'waiting' && (
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.muted, padding: 4, marginTop: -2 }}>
              <X size={15} />
            </button>
          )}
        </div>

        {/* ── IDLE: explain + generate button ── */}
        {step === 'idle' && (
          <>
            {/* How it works */}
            <div style={{
              background: 'rgba(96,165,250,0.05)', border: `1px solid ${C.blue}20`,
              borderRadius: 10, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10,
            }}>
              <div style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.blue }) }}>HOW IT WORKS</div>
              {[
                ['1', 'Click Generate — a secure one-time token is created (expires in 30 min)'],
                ['2', 'Copy the one-line command and send it to the user (email / Slack / Teams)'],
                ['3', 'User opens PowerShell as Administrator, pastes and runs the command'],
                ['4', 'The machine auto-configures WinRM, creates a monitoring account, and registers here instantly'],
              ].map(([n, text]) => (
                <div key={n} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <div style={{
                    width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
                    background: `${C.blue}18`, border: `1px solid ${C.blue}30`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    ...mono({ fontSize: '10px', color: C.blue }),
                  }}>{n}</div>
                  <div style={{ ...ui({ fontSize: '12px', color: C.sub, lineHeight: 1.55 }) }}>{text}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn variant="ghost" onClick={onClose}>CANCEL</Btn>
              <Btn variant="teal" onClick={generate}>
                <Key size={12} /> GENERATE BOOTSTRAP COMMAND
              </Btn>
            </div>
          </>
        )}

        {/* ── GENERATING spinner ── */}
        {step === 'generating' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0' }}>
            <RefreshCw size={16} color={C.teal} style={{ animation: 'spin 1s linear infinite' }} />
            <span style={{ ...mono({ fontSize: '11px', color: C.sub }) }}>Generating secure token…</span>
          </div>
        )}

        {/* ── WAITING: show command + live polling indicator ── */}
        {step === 'waiting' && invite && (
          <>
            {/* Countdown */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              background: countdown < 120 ? `${C.amber}0a` : `${C.teal}08`,
              border: `1px solid ${countdown < 120 ? C.amber : C.teal}25`,
              borderRadius: 9, padding: '9px 14px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Clock size={12} color={countdown < 120 ? C.amber : C.teal} />
                <span style={{ ...mono({ fontSize: '10px', color: countdown < 120 ? C.amber : C.teal }) }}>
                  TOKEN EXPIRES IN
                </span>
              </div>
              <span style={{ ...mono({ fontSize: '14px', letterSpacing: '0.05em', color: countdown < 120 ? C.amber : C.teal }) }}>
                {fmtCountdown(countdown)}
              </span>
            </div>

            {/* Step 1: command block */}
            <div>
              <div style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted, marginBottom: 8 }) }}>
                STEP 1 — SEND THIS COMMAND TO THE USER (COPY → PASTE IN POWERSHELL AS ADMIN)
              </div>
              <div style={{
                background: 'rgba(0,0,0,0.45)', border: `1px solid ${C.teal}30`,
                borderRadius: 9, padding: '12px 14px',
                display: 'flex', flexDirection: 'column', gap: 10,
              }}>
                <div style={{
                  ...mono({ fontSize: '12px', color: C.teal, lineHeight: 1.6, wordBreak: 'break-all' }),
                }}>
                  {invite.connect_command}
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Btn variant={copied ? 'teal' : 'ghost'} onClick={copyCmd}>
                    <Copy size={11} /> {copied ? 'COPIED!' : 'COPY COMMAND'}
                  </Btn>
                </div>
              </div>
            </div>

            {/* Step 2: waiting indicator */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 14,
              background: `${C.blue}07`, border: `1px solid ${C.blue}18`,
              borderRadius: 10, padding: '14px 16px',
            }}>
              <div style={{ position: 'relative', width: 20, height: 20, flexShrink: 0 }}>
                <div style={{
                  position: 'absolute', inset: 0, borderRadius: '50%',
                  border: `2px solid ${C.blue}40`,
                  animation: 'pulse-ring 1.8s ease-out infinite',
                }} />
                <div style={{
                  position: 'absolute', inset: 4, borderRadius: '50%',
                  background: C.blue, opacity: 0.8,
                  animation: 'pulse-dot 1.8s ease-out infinite',
                }} />
              </div>
              <div>
                <div style={{ ...mono({ fontSize: '10px', letterSpacing: '0.08em', color: C.blue }) }}>
                  WAITING FOR MACHINE TO CONNECT…
                </div>
                <div style={{ ...ui({ fontSize: '11px', color: C.muted, marginTop: 3 }) }}>
                  Polling every 3 seconds. This dialog will update automatically.
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Btn variant="ghost" onClick={() => { reset(); onClose(); }}>CANCEL</Btn>
            </div>
          </>
        )}

        {/* ── DONE: machine registered ── */}
        {step === 'done' && result && (
          <>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 14,
              background: `${C.teal}0d`, border: `1px solid ${C.teal}30`,
              borderRadius: 12, padding: '16px 18px',
            }}>
              <CheckCircle2 size={26} color={C.teal} style={{ flexShrink: 0 }} />
              <div>
                <div style={{ ...mono({ fontSize: '12px', letterSpacing: '0.08em', color: C.teal }) }}>
                  MACHINE REGISTERED
                </div>
                <div style={{ ...ui({ fontSize: '13px', color: C.text, marginTop: 4 }) }}>
                  {result.machine_label}
                </div>
                <div style={{ ...mono({ fontSize: '10px', color: C.muted, marginTop: 3 }) }}>
                  WinRM polling active — metrics will appear in Fleet within 30s
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Btn variant="teal" onClick={onClose}>DONE</Btn>
            </div>
          </>
        )}

        {/* ── EXPIRED ── */}
        {step === 'expired' && (
          <>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12,
              background: `${C.amber}0a`, border: `1px solid ${C.amber}30`,
              borderRadius: 10, padding: '14px 16px',
            }}>
              <AlertTriangle size={20} color={C.amber} />
              <div>
                <div style={{ ...mono({ fontSize: '11px', color: C.amber }) }}>TOKEN EXPIRED</div>
                <div style={{ ...ui({ fontSize: '12px', color: C.sub, marginTop: 3 }) }}>
                  The 30-minute window closed before the machine connected. Generate a new token.
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn variant="ghost" onClick={onClose}>CLOSE</Btn>
              <Btn variant="primary" onClick={reset}>
                <RefreshCw size={11} /> GENERATE NEW TOKEN
              </Btn>
            </div>
          </>
        )}

        {/* ── ERROR ── */}
        {step === 'error' && (
          <>
            <div style={{
              ...mono({ fontSize: '10px', color: C.red }),
              background: `${C.red}0d`, border: `1px solid ${C.red}25`,
              borderRadius: 8, padding: '10px 14px',
            }}>
              {error}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn variant="ghost" onClick={onClose}>CLOSE</Btn>
              <Btn variant="primary" onClick={reset}>RETRY</Btn>
            </div>
          </>
        )}
      </div>
      <style>{`
        @keyframes pulse-ring {
          0%   { transform: scale(0.6); opacity: 1; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 0.8; }
          50%       { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}


// ─── Main Component ───────────────────────────────────────────────────────────
const TABS = [
  { id: 'fleet',   icon: Server,   label: 'FLEET'      },
  { id: 'team',    icon: Users,    label: 'TEAM'        },
  { id: 'connect', icon: Zap,      label: 'CONNECTION'  },
];

export default function InfraHub() {
  const { role } = useAuth();
  const isAdmin = role === 'admin';
  const orgId   = getOrgId();
  const me      = getCurrentUser();

  const [tab,        setTab]        = useState('fleet');
  const [agents,     setAgents]     = useState([]);
  const [users,      setUsers]      = useState([]);
  const [alerts,     setAlerts]     = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastAt,     setLastAt]     = useState(null);

  const [showRegister,  setShowRegister]  = useState(false);
  const [showInvite,    setShowInvite]    = useState(false);
  const [showWMI,       setShowWMI]       = useState(false);
  const [wmiTargets,    setWmiTargets]    = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);

  // ── Search / filter ──
  const [agentSearch,  setAgentSearch]  = useState('');
  const [agentFilter,  setAgentFilter]  = useState('all'); // all | online | warning | offline

  // ── Bulk selection ──
  const [selAgents, setSelAgents] = useState(new Set());
  const [selUsers,  setSelUsers]  = useState(new Set());

  // ── Local agent (one-click Monitor This Machine) ──
  const [localAgents,  setLocalAgents]  = useState([]);
  const [launching,    setLaunching]    = useState(false);
  const [launchErr,    setLaunchErr]    = useState('');

  const intervalRef = useRef(null);

  // ── Fetch ──
  const fetchAll = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const [rawAgents, rawMetrics, rawAlerts, rawUsers] = await Promise.allSettled([
        agentsApi.list(orgId),
        metricsApi.getLatest(orgId),
        alertsApi.list(orgId),
        isAdmin ? userApi.list() : Promise.resolve([]),
      ]);

      const agentList  = rawAgents.value  || [];
      const metricList = rawMetrics.value || [];
      const alertList  = rawAlerts.value  || [];
      const userList   = rawUsers.value   || [];

      // Build metrics map from separate call, then fall back to embedded metrics in agent response
      const mMap = {};
      metricList.forEach(m => { if (m?.agent_id) mMap[m.agent_id] = m; });
      setAgents(agentList.map(a => ({
        ...a,
        metrics: mMap[a.id] || a.metrics || {},
      })));
      setAlerts(Array.isArray(alertList) ? alertList : []);
      setUsers(Array.isArray(userList)  ? userList  : []);
      setLastAt(new Date());
    } catch (err) {
      console.error('[InfraHub] fetch error', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [orgId, isAdmin]);

  const fetchLocalAgents = useCallback(async () => {
    try {
      const res = await axios.get('/api/local-agent/status');
      setLocalAgents(res.data.agents || []);
    } catch (_) {}
  }, []);

  const fetchWmiTargets = useCallback(async () => {
    if (!orgId) return;
    try {
      const list = await wmiApi.list(orgId);
      setWmiTargets(Array.isArray(list) ? list : []);
    } catch (_) {}
  }, [orgId]);

  const launchLocal = useCallback(async () => {
    setLaunching(true); setLaunchErr('');
    try {
      await axios.post('/api/local-agent/launch', { org_id: orgId, token: getToken() });
      await fetchLocalAgents();
      await fetchAll();
    } catch (e) {
      setLaunchErr(e?.response?.data?.error || e?.message || 'Launch failed');
    } finally { setLaunching(false); }
  }, [orgId, fetchLocalAgents, fetchAll]);

  const stopLocal = useCallback(async (agentId) => {
    try {
      await axios.delete(`/api/local-agent/stop/${agentId}`);
      await fetchLocalAgents();
    } catch (_) {}
  }, [fetchLocalAgents]);

  useEffect(() => {
    fetchAll();
    fetchLocalAgents();
    fetchWmiTargets();
    return () => {};
  }, [fetchAll, fetchLocalAgents, fetchWmiTargets]);

  const handleToggleUser = async (user) => {
    try {
      await userApi.update(user.id, { is_active: !user.is_active });
      setUsers(prev => prev.map(u => u.id === user.id ? { ...u, is_active: !u.is_active } : u));
    } catch (e) { console.error(e); }
  };

  const handleDeleteUser = async (userId) => {
    try {
      await userApi.deactivate(userId);
      setUsers(prev => prev.filter(u => u.id !== userId));
    } catch (e) { console.error(e); }
  };

  const handleDeleteAgent = async (agentId) => {
    try {
      await agentsApi.remove(orgId, agentId);
      setAgents(prev => prev.filter(a => a.id !== agentId));
      setSelAgents(prev => { const n = new Set(prev); n.delete(agentId); return n; });
    } catch (e) { console.error(e); }
  };

  const handleRoleChange = async (user, newRole) => {
    try {
      await userApi.update(user.id, { role: newRole });
      setUsers(prev => prev.map(u => u.id === user.id ? { ...u, role: newRole } : u));
    } catch (e) { console.error(e); }
  };

  const toggleAgentSel = (id) => setSelAgents(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleUserSel = (id) => setSelUsers(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  const bulkDeleteAgents = async () => {
    const ids = [...selAgents];
    await Promise.allSettled(ids.map(id => agentsApi.remove(orgId, id)));
    setAgents(prev => prev.filter(a => !ids.includes(a.id)));
    setSelAgents(new Set());
  };

  const bulkDeactivateUsers = async () => {
    const ids = [...selUsers];
    await Promise.allSettled(ids.map(id => userApi.update(id, { is_active: false })));
    setUsers(prev => prev.map(u => ids.includes(u.id) ? { ...u, is_active: false } : u));
    setSelUsers(new Set());
  };

  const bulkDeleteUsers = async () => {
    const ids = [...selUsers];
    await Promise.allSettled(ids.map(id => userApi.deactivate(id)));
    setUsers(prev => prev.filter(u => !ids.includes(u.id)));
    setSelUsers(new Set());
  };

  // ── Filtered agents ──
  const filteredAgents = agents.filter(a => {
    const name = (a.label || a.id || '').toLowerCase();
    const host = (a.platform_info?.hostname || '').toLowerCase();
    const q    = agentSearch.toLowerCase();
    const matchesSearch = !q || name.includes(q) || host.includes(q);
    const matchesFilter = agentFilter === 'all' || deriveStatus(a.last_seen) === agentFilter;
    return matchesSearch && matchesFilter;
  });

  // ── Stats ──
  const total   = agents.length;
  const online  = agents.filter(a => deriveStatus(a.last_seen) === 'online').length;
  const offline = agents.filter(a => deriveStatus(a.last_seen) === 'offline').length;
  const openAlerts = alerts.filter(a => a.status === 'open').length;

  const statItems = [
    { label: 'TOTAL AGENTS',  val: total,      color: C.sub,   icon: Server    },
    { label: 'ONLINE',        val: online,     color: C.teal,  icon: Activity  },
    { label: 'OFFLINE',       val: offline,    color: C.muted, icon: WifiOff   },
    { label: 'OPEN ALERTS',   val: openAlerts, color: openAlerts > 0 ? C.red : C.muted, icon: AlertTriangle },
    ...(isAdmin ? [{ label: 'TEAM SIZE', val: users.length, color: C.amber, icon: Users }] : []),
  ];

  // ── Render ──
  return (
    <>
      {/* CSS animations */}
      <style>{`
        @keyframes hub-pulse {
          0%, 100% { transform: scale(1); opacity: 0.25; }
          50%       { transform: scale(2); opacity: 0; }
        }
        @keyframes hub-fadein {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .hub-row:hover td { background: rgba(42,40,32,0.18); }
      `}</style>

      <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 22, color: C.text, ...ui() }}>

        {/* ── Page Header ── */}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <Layers size={18} color={C.amber} />
              <span style={{ ...mono({ fontSize: '10px', letterSpacing: '0.14em', color: C.muted }) }}>FLEET MANAGEMENT</span>
            </div>
            <h1 style={{ ...disp({ fontSize: '2.4rem', letterSpacing: '0.05em', lineHeight: 1 }), margin: 0, color: C.text }}>
              USERS & DEVICES
            </h1>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {lastAt && (
              <span style={{ ...mono({ fontSize: '9px', color: C.dim }) }}>
                UPDATED {lastAt.toLocaleTimeString()}
              </span>
            )}
            <button onClick={() => fetchAll(true)} disabled={refreshing} style={{
              background: 'none', border: `1px solid ${C.border}`, borderRadius: 7,
              padding: '6px 10px', cursor: refreshing ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 5,
              color: C.sub, opacity: refreshing ? 0.5 : 1, transition: 'opacity 0.2s',
            }}>
              <RefreshCw size={12} color={C.sub} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
              <span style={{ ...mono({ fontSize: '9px', letterSpacing: '0.08em' }) }}>REFRESH</span>
            </button>
          </div>
        </div>

        {/* ── Stats Ribbon ── */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {statItems.map(s => (
            <div key={s.label} style={{
              flex: '1 1 120px', background: C.panel, border: `1px solid ${C.border}`,
              borderRadius: 10, padding: '14px 16px',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <div style={{ width: 34, height: 34, borderRadius: 9, background: `${s.color}14`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <s.icon size={15} color={s.color} />
              </div>
              <div>
                {loading
                  ? <Skeleton w={28} h={20} r={4} />
                  : <div style={{ ...disp({ fontSize: '1.7rem', lineHeight: 1, color: C.text }) }}>{s.val}</div>
                }
                <div style={{ ...mono({ fontSize: '9px', color: C.muted, letterSpacing: '0.07em' }), marginTop: 2 }}>{s.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* ── Tab Bar ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, borderBottom: `1px solid ${C.border}` }}>
          {TABS.filter(t => t.id !== 'team' || isAdmin).map(t => {
            const active = tab === t.id;
            return (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 18px', background: 'none', border: 'none',
                borderBottom: active ? `2px solid ${C.amber}` : '2px solid transparent',
                cursor: 'pointer', color: active ? C.amber : C.sub,
                ...mono({ fontSize: '10px', letterSpacing: '0.08em' }),
                transition: 'color 0.15s', marginBottom: '-1px',
              }}>
                <t.icon size={13} />
                {t.label}
                {t.id === 'fleet' && total > 0 && (
                  <span style={{ ...mono({ fontSize: '8px' }), background: `${C.teal}18`, color: C.teal, padding: '1px 5px', borderRadius: 5 }}>
                    {total}
                  </span>
                )}
              </button>
            );
          })}

          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            {tab === 'fleet' && isAdmin && (
              <>
                <Btn variant="ghost" size="sm" onClick={() => setShowWMI(true)}>
                  <Monitor size={11} /> ADD WINDOWS MACHINE
                </Btn>
                <Btn variant="teal" size="sm" onClick={() => setShowRegister(true)}>
                  <Plus size={11} /> ADD AGENT
                </Btn>
              </>
            )}
            {tab === 'team' && isAdmin && (
              <Btn variant="primary" size="sm" onClick={() => setShowInvite(true)}>
                <UserPlus size={11} /> ADD USER
              </Btn>
            )}
          </div>
        </div>

        {/* ── FLEET TAB ── */}
        {tab === 'fleet' && (
          <div style={{ animation: 'hub-fadein 0.2s ease', display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* ── Monitor This Machine (one-click) ── */}
            {(() => {
              const running = localAgents.filter(a => a.running);
              const anyRunning = running.length > 0;
              return (
                <div style={{
                  background: C.panel,
                  border: `1px solid ${anyRunning ? C.teal + '40' : C.border}`,
                  borderRadius: 11, padding: '16px 20px',
                  display: 'flex', alignItems: 'center', gap: 14,
                  transition: 'border-color 0.3s',
                }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                    background: anyRunning ? `${C.teal}14` : `${C.amber}14`,
                    border: `1px solid ${anyRunning ? C.teal + '30' : C.amber + '25'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Zap size={17} color={anyRunning ? C.teal : C.amber} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ ...ui({ fontSize: '14px', fontWeight: 600, color: C.text }) }}>
                      Monitor This Machine
                    </div>
                    <div style={{ ...ui({ fontSize: '11px', color: C.muted }), marginTop: 2 }}>
                      {anyRunning
                        ? `Agent running on this machine — reporting metrics now.`
                        : 'One click to register & start a monitoring agent on this machine.'}
                    </div>
                    {launchErr && (
                      <div style={{ ...mono({ fontSize: '10px', color: C.red }), marginTop: 5 }}>{launchErr}</div>
                    )}
                  </div>
                  {anyRunning ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                      <Pulse color={C.teal} size={6} />
                      <span style={{ ...mono({ fontSize: '9px', color: C.teal, letterSpacing: '0.07em' }) }}>RUNNING</span>
                      <Btn variant="ghost" size="sm" onClick={() => running.forEach(a => stopLocal(a.agent_id))}>
                        STOP
                      </Btn>
                    </div>
                  ) : (
                    <Btn variant="primary" size="md" disabled={launching} onClick={launchLocal} style={{ flexShrink: 0 }}>
                      <Zap size={12} /> {launching ? 'LAUNCHING…' : 'LAUNCH NOW'}
                    </Btn>
                  )}
                </div>
              );
            })()}

            {/* ── Search + Filter bar ── */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 160 }}>
                <Search size={12} color={C.muted} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                <input
                  value={agentSearch}
                  onChange={e => setAgentSearch(e.target.value)}
                  placeholder="Search by name or hostname…"
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: C.panel, border: `1px solid ${C.border}`,
                    borderRadius: 7, padding: '7px 10px 7px 28px',
                    ...mono({ fontSize: '11px', color: C.text }),
                    outline: 'none',
                  }}
                  onFocus={e => { e.target.style.borderColor = `${C.amber}50`; }}
                  onBlur={e => { e.target.style.borderColor = C.border; }}
                />
                {agentSearch && (
                  <button onClick={() => setAgentSearch('')}
                    style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: C.muted, padding: 0 }}>
                    <X size={11} />
                  </button>
                )}
              </div>
              {['all', 'online', 'warning', 'offline'].map(f => (
                <button key={f} onClick={() => setAgentFilter(f)} style={{
                  ...mono({ fontSize: '9px', letterSpacing: '0.08em' }),
                  padding: '6px 12px', borderRadius: 6, cursor: 'pointer', border: '1px solid',
                  borderColor: agentFilter === f ? (f === 'online' ? C.teal : f === 'warning' ? C.amber : f === 'offline' ? C.muted : C.amber) + '60' : C.border,
                  background: agentFilter === f ? (f === 'online' ? C.teal : f === 'warning' ? C.amber : f === 'offline' ? C.muted : C.amber) + '14' : 'transparent',
                  color: agentFilter === f ? (f === 'online' ? C.teal : f === 'warning' ? C.amber : f === 'offline' ? C.sub : C.amber) : C.muted,
                  transition: 'all 0.15s',
                }}>{f.toUpperCase()}</button>
              ))}
              {agents.length > 0 && (
                <button onClick={() => setSelAgents(selAgents.size === agents.length ? new Set() : new Set(agents.map(a => a.id)))}
                  style={{ ...mono({ fontSize: '9px', letterSpacing: '0.07em' }), padding: '6px 12px', borderRadius: 6, cursor: 'pointer', border: `1px solid ${C.border}`, background: 'transparent', color: C.muted, display: 'flex', alignItems: 'center', gap: 5 }}>
                  {selAgents.size === agents.length ? <CheckSquare size={11} /> : <Square size={11} />}
                  {selAgents.size === agents.length ? 'DESELECT ALL' : 'SELECT ALL'}
                </button>
              )}
            </div>

            {/* ── Bulk action bar for agents ── */}
            {selAgents.size > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                background: `${C.amber}0e`, border: `1px solid ${C.amber}30`,
                borderRadius: 9, padding: '10px 16px',
              }}>
                <span style={{ ...mono({ fontSize: '10px', color: C.amber }) }}>{selAgents.size} SELECTED</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                  <Btn variant="danger" size="sm" onClick={bulkDeleteAgents}>
                    <Trash2 size={10} /> DELETE SELECTED
                  </Btn>
                  <Btn variant="ghost" size="sm" onClick={() => setSelAgents(new Set())}>
                    <X size={10} /> CLEAR
                  </Btn>
                </div>
              </div>
            )}

            {loading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {[1,2,3].map(i => (
                  <div key={i} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <Skeleton w="60%" h={16} /><Skeleton h={4} /><Skeleton h={4} /><Skeleton h={4} />
                  </div>
                ))}
              </div>
            ) : filteredAgents.length === 0 ? (
              <div style={{
                background: C.panel, border: `1px dashed ${C.border}`,
                borderRadius: 12, padding: '40px 32px', textAlign: 'center',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
              }}>
                <div style={{ width: 56, height: 56, borderRadius: 14, background: `${C.teal}10`, border: `1px solid ${C.teal}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Server size={24} color={C.teal} />
                </div>
                <div style={{ ...mono({ fontSize: '11px', letterSpacing: '0.1em', color: C.muted }) }}>
                  {agentSearch || agentFilter !== 'all' ? 'NO MATCHES' : 'NO REMOTE AGENTS YET'}
                </div>
                <div style={{ ...ui({ fontSize: '12px', color: C.muted }), maxWidth: 300 }}>
                  {agentSearch || agentFilter !== 'all'
                    ? 'Try a different search or filter.'
                    : <>Click <strong style={{ color: C.amber }}>LAUNCH NOW</strong> above to instantly start monitoring this machine, or use the Connection Guide for a remote host.</>}
                </div>
                {!agentSearch && agentFilter === 'all' && isAdmin && (
                  <Btn variant="teal" onClick={() => setTab('connect')}>
                    <ArrowUpRight size={11} /> CONNECTION GUIDE
                  </Btn>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {filteredAgents.map(a => (
                  <AgentCard
                    key={a.id} agent={a} users={users}
                    onDelete={isAdmin ? handleDeleteAgent : null}
                    onClick={setSelectedAgent}
                    selected={selAgents.has(a.id)}
                    onSelect={isAdmin ? toggleAgentSel : null}
                  />
                ))}
              </div>
            )}

            {/* ── WMI Targets ── */}
            {isAdmin && wmiTargets.length === 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 14,
                background: C.panel, border: `1px dashed ${C.blue}30`,
                borderRadius: 10, padding: '14px 18px',
              }}>
                <div style={{ width: 36, height: 36, borderRadius: 9, background: `${C.blue}12`, border: `1px solid ${C.blue}25`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Monitor size={15} color={C.blue} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ ...ui({ fontSize: '13px', fontWeight: 500, color: C.sub }) }}>Agentless Windows Monitoring</div>
                  <div style={{ ...ui({ fontSize: '11px', color: C.muted }), marginTop: 2 }}>
                    Poll any Windows machine over WinRM — no agent install needed. Just enable PowerShell remoting once.
                  </div>
                </div>
                <Btn variant="ghost" size="sm" onClick={() => setShowWMI(true)}>
                  <Monitor size={11} /> ADD WINDOWS MACHINE
                </Btn>
              </div>
            )}

            {isAdmin && wmiTargets.length > 0 && (
              <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
                <div style={{ padding: '14px 20px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Monitor size={14} color={C.blue} />
                  <span style={{ ...mono({ fontSize: '11px', letterSpacing: '0.1em', color: C.sub }) }}>WINDOWS MACHINES (WMI)</span>
                  <span style={{ marginLeft: 'auto', ...mono({ fontSize: '9px', color: C.blue }), background: `${C.blue}14`, padding: '2px 8px', borderRadius: 6 }}>
                    {wmiTargets.length} TARGET{wmiTargets.length !== 1 ? 'S' : ''}
                  </span>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                      {['STATUS', 'LABEL', 'HOST', 'LAST POLLED', 'ACTIONS'].map(h => (
                        <th key={h} style={{ ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted }), padding: '8px 16px', textAlign: 'left', fontWeight: 400 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {wmiTargets.map(t => (
                      <WMIRow
                        key={t.id}
                        target={t}
                        orgId={orgId}
                        onDelete={id => setWmiTargets(prev => prev.filter(x => x.id !== id))}
                        onRefresh={fetchWmiTargets}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── TEAM TAB ── */}
        {tab === 'team' && isAdmin && (
          <div style={{ animation: 'hub-fadein 0.2s ease', display: 'flex', flexDirection: 'column', gap: 12 }}>

            {/* Bulk action bar for users */}
            {selUsers.size > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                background: `${C.amber}0e`, border: `1px solid ${C.amber}30`,
                borderRadius: 9, padding: '10px 16px',
              }}>
                <span style={{ ...mono({ fontSize: '10px', color: C.amber }) }}>{selUsers.size} SELECTED</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                  <Btn variant="ghost" size="sm" onClick={bulkDeactivateUsers}>DEACTIVATE SELECTED</Btn>
                  <Btn variant="danger" size="sm" onClick={bulkDeleteUsers}><Trash2 size={10} /> DELETE SELECTED</Btn>
                  <Btn variant="ghost" size="sm" onClick={() => setSelUsers(new Set())}><X size={10} /> CLEAR</Btn>
                </div>
              </div>
            )}

            <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
                <Users size={14} color={C.amber} />
                <span style={{ ...mono({ fontSize: '11px', letterSpacing: '0.1em', color: C.sub }) }}>REGISTERED USERS</span>
                <button onClick={() => setSelUsers(selUsers.size === users.length ? new Set() : new Set(users.map(u => u.id)))}
                  style={{ ...mono({ fontSize: '9px' }), background: 'none', border: `1px solid ${C.border}`, borderRadius: 5, padding: '2px 8px', color: C.muted, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
                  {selUsers.size === users.length && users.length > 0 ? <CheckSquare size={10} /> : <Square size={10} />} SELECT ALL
                </button>
                <span style={{ marginLeft: 'auto', ...mono({ fontSize: '9px', color: C.amber }), background: `${C.amber}14`, padding: '2px 8px', borderRadius: 6 }}>
                  {users.length} MEMBER{users.length !== 1 ? 'S' : ''}
                </span>
              </div>
              {loading ? (
                <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[1,2,3].map(i => <Skeleton key={i} h={42} r={6} />)}
                </div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                      {['', 'USER', 'ROLE', 'STATUS', 'LAST LOGIN', ''].map((h, i) => (
                        <th key={i} style={{
                          padding: '10px 8px', ...mono({ fontSize: '9px', letterSpacing: '0.1em', color: C.muted }),
                          textAlign: i === 5 ? 'right' : 'left', fontWeight: 500,
                          ...(i === 0 ? { width: 36, padding: '10px 4px 10px 12px' } : {}),
                          ...(i === 1 ? { paddingLeft: 16 } : {}),
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.length === 0 ? (
                      <tr><td colSpan={6} style={{ padding: '30px', textAlign: 'center', ...ui({ fontSize: '13px', color: C.muted }) }}>No users found.</td></tr>
                    ) : users.map(u => (
                      <UserRow
                        key={u.id} user={u}
                        isMe={u.id === me?.id || u.email === me?.email}
                        onToggle={handleToggleUser}
                        onDelete={handleDeleteUser}
                        onRoleChange={handleRoleChange}
                        selected={selUsers.has(u.id)}
                        onSelect={toggleUserSel}
                      />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* ── CONNECTION TAB ── */}
        {tab === 'connect' && (
          <div style={{ animation: 'hub-fadein 0.2s ease' }}>
            <ConnectGuide orgId={orgId} onRegister={() => { setShowRegister(true); }} />
          </div>
        )}
      </div>

      {/* ── Modals ── */}
      {showWMI && (
        <WMIModal
          orgId={orgId}
          onClose={() => setShowWMI(false)}
          onCreated={() => { fetchWmiTargets(); fetchAll(); }}
        />
      )}
      {showRegister && (
        <RegisterModal
          orgId={orgId}
          onClose={() => setShowRegister(false)}
          onCreated={() => fetchAll()}
        />
      )}
      {showInvite && (
        <InviteModal
          onClose={() => { setShowInvite(false); fetchAll(); }}
        />
      )}

      {/* Agent detail dashboard — full-screen overlay */}
      {selectedAgent && (
        <AgentDashboard
          agent={agents.find(a => a.id === selectedAgent.id) || selectedAgent}
          orgId={orgId}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </>
  );
}
