/**
 * RemoteAgents — Admin page for managing remote push-based system agents.
 * Admin generates a token → user runs one command → live metrics appear here.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { agentApi } from '../services/api';
import { agentsApi } from '../services/resiloApi';
import InfoTip from './InfoTip';
import {
  Monitor, Plus, RefreshCw, Trash2, Copy, CheckCheck,
  Cpu, HardDrive, MemoryStick, Wifi, Terminal,
  ChevronLeft, Circle, Zap, Server, Play,
  CheckCircle, XCircle, AlertTriangle, Clock, Bot,
  RotateCcw, Flame, Layers,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

// ─── Design tokens ────────────────────────────────────────────────────────────
const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };
const UI      = { fontFamily: "'Outfit', sans-serif" };

const C = {
  bg:         'rgb(14,13,11)',
  surface:    'rgb(22,20,16)',
  surface2:   'rgb(31,29,24)',
  border:     'rgba(42,40,32,0.9)',
  amber:      '#F59E0B',
  amberAlpha: 'rgba(245,158,11,0.1)',
  teal:       '#2DD4BF',
  red:        '#F87171',
  text1:      '#F5F0E8',
  text2:      '#A89F8C',
  text3:      '#6B6357',
  text4:      '#4A443D',
};

const PANEL = {
  background:   C.surface,
  border:       `1px solid ${C.border}`,
  borderRadius: '12px',
  boxShadow:    '0 4px 24px rgba(0,0,0,0.3)',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtUptime(secs) {
  if (secs == null) return '—';
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function fmtBytes(bytes) {
  if (bytes == null) return '—';
  const gb = bytes / 1073741824;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / 1048576;
  if (mb >= 1) return `${mb.toFixed(0)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

function fmtLastSeen(ts) {
  if (!ts) return 'never';
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 5)  return 'just now';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

const STATUS_META = {
  live:    { color: C.teal,  dot: C.teal,  label: 'LIVE',    pulse: true  },
  offline: { color: C.red,   dot: C.red,   label: 'OFFLINE', pulse: false },
  pending: { color: C.amber, dot: C.amber, label: 'PENDING', pulse: true  },
};

function Bar({ pct }) {
  const color = pct >= 90 ? C.red : pct >= 75 ? C.amber : C.teal;
  return (
    <div style={{ height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden', flex: 1 }}>
      <div style={{ width: `${Math.min(100, pct || 0)}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.5s' }} />
    </div>
  );
}

function MetricPill({ icon, label, value, pct }) {
  const color = pct != null ? (pct >= 90 ? C.red : pct >= 75 ? C.amber : C.teal) : C.text3;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ color: C.text4 }}>{icon}</span>
      <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>{label}</span>
      <span style={{ ...MONO, fontSize: 11, color, fontWeight: 700 }}>{value ?? '—'}</span>
    </div>
  );
}

// ─── Copy button ──────────────────────────────────────────────────────────────
function CopyBtn({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(text).catch(() => {});
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '6px 14px', borderRadius: 6,
        background: copied ? 'rgba(45,212,191,0.12)' : C.amberAlpha,
        border: `1px solid ${copied ? 'rgba(45,212,191,0.3)' : 'rgba(245,158,11,0.3)'}`,
        color: copied ? C.teal : C.amber,
        cursor: 'pointer', transition: 'all 0.2s',
        ...MONO, fontSize: 11,
      }}
    >
      {copied ? <CheckCheck size={12} /> : <Copy size={12} />}
      {copied ? 'Copied!' : label}
    </button>
  );
}

// ─── New Agent Modal ───────────────────────────────────────────────────────────
export function NewAgentModal({ onClose, onCreated, initialLabel = '' }) {
  const [label, setLabel]       = useState(initialLabel);
  const [step, setStep]         = useState('form'); // form | ready
  const [token, setToken]       = useState('');
  const [secsLeft, setSecsLeft] = useState(300);
  const [creating, setCreating] = useState(false);
  const [error, setError]       = useState('');
  const timerRef = useRef(null);

  const backendUrl = process.env.REACT_APP_BACKEND_URL || (
    window.location.hostname === 'localhost'
      ? 'http://localhost:8000'
      : `${window.location.protocol}//${window.location.hostname}`
  );

  const agentUrl = 'https://raw.githubusercontent.com/jaybharuka/resilo/main/desktop_agent/resilo_agent.py';
  const winCmd  = token ? `pip install psutil -q; Invoke-WebRequest -Uri "${agentUrl}" -OutFile "$env:TEMP\\resilo_agent.py"; $env:RESILO_ONBOARD_TOKEN="${token}"; $env:RESILO_BACKEND_URL="${backendUrl}"; python "$env:TEMP\\resilo_agent.py"` : '';
  const unixCmd = token ? `pip install psutil -q && curl -sO /tmp/resilo_agent.py ${agentUrl} && RESILO_ONBOARD_TOKEN=${token} RESILO_BACKEND_URL=${backendUrl} python /tmp/resilo_agent.py` : '';

  const handleGenerate = async () => {
    if (!label.trim()) { setError('Enter a label for this device.'); return; }
    setCreating(true);
    setError('');
    try {
      const data = await agentApi.onboard(label.trim());
      setToken(data.token);
      setSecsLeft(data.expires_in || 300);
      setStep('ready');
      onCreated();
      timerRef.current = setInterval(() => {
        setSecsLeft(s => {
          if (s <= 1) { clearInterval(timerRef.current); return 0; }
          return s - 1;
        });
      }, 1000);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to generate token.');
    } finally {
      setCreating(false);
    }
  };

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  const expired = secsLeft === 0;
  const mins = String(Math.floor(secsLeft / 60)).padStart(2, '0');
  const secs = String(secsLeft % 60).padStart(2, '0');

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }}>
      <div style={{
        ...PANEL, width: '100%', maxWidth: 580, position: 'relative',
        animation: 'fadeUp 0.18s ease',
      }}>
        <style>{`@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}`}</style>

        {/* Header */}
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Plus size={15} color={C.amber} />
          <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
            {step === 'form' ? 'ADD DEVICE' : 'RUN ON TARGET MACHINE'}
          </span>
          <button
            onClick={onClose}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: C.text4, cursor: 'pointer', display: 'flex', padding: 4 }}
          >✕</button>
        </div>

        <div style={{ padding: '24px' }}>
          {step === 'form' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p style={{ ...UI, fontSize: 13, color: C.text2, margin: 0, lineHeight: 1.6 }}>
                Name the device you want to monitor. A one-time token will be generated — paste the run command on that machine and it connects automatically.
              </p>
              <div>
                <label style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.text4, display: 'block', marginBottom: 8 }}>
                  DEVICE NAME
                </label>
                <input
                  autoFocus
                  value={label}
                  onChange={e => setLabel(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleGenerate()}
                  placeholder="e.g. Jay's Laptop, Dev Server, Finance PC"
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: C.surface2, border: `1px solid ${C.border}`,
                    borderRadius: 8, padding: '10px 14px',
                    ...UI, fontSize: 13, color: C.text1, outline: 'none',
                  }}
                />
                {error && <p style={{ ...MONO, fontSize: 11, color: C.red, margin: '8px 0 0' }}>{error}</p>}
              </div>
              <button
                onClick={handleGenerate}
                disabled={creating}
                style={{
                  padding: '10px 0', borderRadius: 8, cursor: creating ? 'not-allowed' : 'pointer',
                  background: creating ? C.surface2 : C.amberAlpha,
                  border: `1px solid ${creating ? C.border : 'rgba(245,158,11,0.35)'}`,
                  color: creating ? C.text4 : C.amber,
                  ...MONO, fontSize: 12, letterSpacing: '0.08em',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  transition: 'all 0.15s',
                }}
              >
                <Zap size={13} />
                {creating ? 'GENERATING…' : 'GENERATE LINK'}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {/* Timer */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderRadius: 8,
                background: expired ? 'rgba(248,113,113,0.06)' : 'rgba(245,158,11,0.06)',
                border: `1px solid ${expired ? 'rgba(248,113,113,0.25)' : 'rgba(245,158,11,0.2)'}`,
              }}>
                <Clock size={13} color={expired ? C.red : C.amber} />
                <span style={{ ...MONO, fontSize: 11, color: expired ? C.red : C.amber }}>
                  {expired ? 'TOKEN EXPIRED — generate a new one' : `Token valid for ${mins}:${secs}`}
                </span>
                {expired && (
                  <button
                    onClick={() => setStep('form')}
                    style={{ marginLeft: 'auto', ...MONO, fontSize: 10, color: C.amber, background: 'transparent', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                  >Regenerate</button>
                )}
              </div>

              {/* Windows command */}
              <div>
                <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: C.text4, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Monitor size={11} /> WINDOWS — run in PowerShell or CMD
                </div>
                <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px' }}>
                  <code style={{ ...MONO, fontSize: 11, color: C.teal, lineHeight: 1.7, wordBreak: 'break-all', display: 'block' }}>
                    {winCmd}
                  </code>
                </div>
                <div style={{ marginTop: 8 }}>
                  <CopyBtn text={winCmd} label="Copy" />
                </div>
              </div>

              {/* Mac / Linux command */}
              <div>
                <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: C.text4, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Terminal size={11} /> MAC / LINUX — run in terminal
                </div>
                <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px' }}>
                  <code style={{ ...MONO, fontSize: 11, color: C.teal, lineHeight: 1.7, wordBreak: 'break-all', display: 'block' }}>
                    {unixCmd}
                  </code>
                </div>
                <div style={{ marginTop: 8 }}>
                  <CopyBtn text={unixCmd} label="Copy" />
                </div>
              </div>

              <p style={{ ...UI, fontSize: 12, color: C.text4, margin: 0, lineHeight: 1.55 }}>
                Requires Python 3.8+ and <code style={MONO}>psutil</code> on the target machine. The device appears live within seconds of running the command.
              </p>

              <button
                onClick={onClose}
                style={{ padding: '9px 0', borderRadius: 8, cursor: 'pointer', background: 'transparent', border: `1px solid ${C.border}`, color: C.text2, ...MONO, fontSize: 11, letterSpacing: '0.08em' }}
              >
                DONE
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Agent List Card ───────────────────────────────────────────────────────────
function AgentCard({ agent, onSelect, onRemove }) {
  const sm = STATUS_META[agent.status] || STATUS_META.pending;

  return (
    <div
      onClick={() => onSelect(agent)}
      style={{
        ...PANEL, padding: '18px 20px', cursor: 'pointer',
        borderTop: `2px solid ${sm.dot}`,
        transition: 'box-shadow 0.15s, border-color 0.15s',
        position: 'relative',
      }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = `0 0 0 1px ${sm.dot}40, 0 8px 32px rgba(0,0,0,0.4)`; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 4px 24px rgba(0,0,0,0.3)'; }}
    >
      {/* Status dot + label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%', background: sm.dot, flexShrink: 0,
          boxShadow: `0 0 8px ${sm.dot}80`,
          display: 'inline-block',
          animation: sm.pulse ? 'pulse 1.5s ease-in-out infinite' : 'none',
        }} />
        <span style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: sm.color }}>{sm.label}</span>
        <span style={{ marginLeft: 'auto', ...MONO, fontSize: 10, color: C.text4 }}>
          {fmtLastSeen(agent.last_seen)}
        </span>
        {/* Remove button */}
        <button
          onClick={e => { e.stopPropagation(); onRemove(agent.id); }}
          title="Revoke & remove agent"
          style={{ background: 'transparent', border: 'none', color: C.text4, cursor: 'pointer', display: 'flex', padding: 4, borderRadius: 4 }}
          onMouseEnter={e => { e.currentTarget.style.color = C.red; }}
          onMouseLeave={e => { e.currentTarget.style.color = C.text4; }}
        >
          <Trash2 size={12} />
        </button>
      </div>

      {/* Label + hostname */}
      <div style={{ marginBottom: 4 }}>
        <span style={{ ...UI, fontSize: 15, fontWeight: 700, color: C.text1 }}>{agent.label}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14 }}>
        <Monitor size={11} color={C.text4} />
        <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>{agent.hostname}</span>
        {agent.os && <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>· {agent.os}</span>}
        {agent.cpu_cores && <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>· {agent.cpu_cores} cores</span>}
      </div>

      {/* Metric bars */}
      {agent.status === 'live' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {[
            { label: 'CPU',  pct: agent.cpu,    unit: '%' },
            { label: 'MEM',  pct: agent.memory, unit: '%' },
            { label: 'DISK', pct: agent.disk,   unit: '%' },
          ].map(({ label, pct, unit }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ ...MONO, fontSize: 9, color: C.text4, width: 30 }}>{label}</span>
              <Bar pct={pct} />
              <span style={{ ...MONO, fontSize: 10, color: pct >= 90 ? C.red : pct >= 75 ? C.amber : C.teal, width: 36, textAlign: 'right' }}>
                {pct != null ? `${pct.toFixed(0)}${unit}` : '—'}
              </span>
            </div>
          ))}
        </div>
      )}

      {agent.status === 'pending' && (
        <p style={{ ...UI, fontSize: 12, color: C.text4, margin: 0 }}>
          Waiting for agent to connect — run the install command on the target machine.
        </p>
      )}

      {agent.status === 'offline' && (
        <p style={{ ...UI, fontSize: 12, color: C.text4, margin: 0 }}>
          No heartbeat received in {Math.round(_AGENT_LIVE_SECS / 60) || 1}+ minutes. Agent may be stopped.
        </p>
      )}
    </div>
  );
}

// React can't reference the backend constant so duplicate it
const _AGENT_LIVE_SECS = 12;

// ─── Command status helpers ───────────────────────────────────────────────────
const CMD_STATUS = {
  pending: { color: C.amber, icon: <Clock size={11} />,       label: 'PENDING'  },
  success: { color: C.teal,  icon: <CheckCircle size={11} />, label: 'SUCCESS'  },
  failed:  { color: C.red,   icon: <XCircle size={11} />,     label: 'FAILED'   },
  skipped: { color: C.text3, icon: <AlertTriangle size={11}/>, label: 'SKIPPED' },
};

function fmtTs(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ─── Command Center ───────────────────────────────────────────────────────────
const ACTION_META = {
  clear_cache:     { icon: <Layers size={13} />,    label: 'Clear Cache',     desc: 'Flush OS page cache & temp files',          fix: null       },
  disk_cleanup:    { icon: <HardDrive size={13} />,  label: 'Disk Cleanup',    desc: 'Delete old temp/log files (>1 day)',         fix: 'disk'     },
  free_memory:     { icon: <MemoryStick size={13}/>, label: 'Free Memory',     desc: 'Drop OS caches and release memory pages',   fix: 'memory'   },
  run_gc:          { icon: <RotateCcw size={13} />,  label: 'Run GC',          desc: 'Python garbage collection on remote procs', fix: 'memory'   },
  kill_process:    { icon: <Flame size={13} />,      label: 'Kill Process',    desc: 'Terminate a process by name or PID',        fix: null       },
  restart_service: { icon: <Server size={13} />,     label: 'Restart Service', desc: 'Restart a named system service',            fix: null       },
};

function CommandCenter({ agentId, agentStatus, metrics, onCommandSent }) {
  const [sending, setSending]   = useState({});
  const [sent, setSent]         = useState({});    // { action: 'ok' | 'err' }
  const [paramAction, setParam] = useState(null);  // action needing param input
  const [paramVal, setParamVal] = useState('');
  const [paramErr, setParamErr] = useState('');

  const NEEDS_PARAM = { kill_process: true, restart_service: true };

  const fire = async (action, params = {}) => {
    setSending(s => ({ ...s, [action]: true }));
    setSent(s => { const n = { ...s }; delete n[action]; return n; });
    try {
      await agentApi.sendCommand(agentId, action, params);
      setSent(s => ({ ...s, [action]: 'ok' }));
      onCommandSent && onCommandSent();
      setTimeout(() => setSent(s => { const n = { ...s }; delete n[action]; return n; }), 4000);
    } catch (e) {
      setSent(s => ({ ...s, [action]: 'err' }));
      setTimeout(() => setSent(s => { const n = { ...s }; delete n[action]; return n; }), 4000);
    } finally {
      setSending(s => ({ ...s, [action]: false }));
    }
  };

  const handleClick = (action) => {
    if (agentStatus !== 'live') return;
    if (NEEDS_PARAM[action]) {
      setParam(action);
      setParamVal('');
      setParamErr('');
      return;
    }
    fire(action);
  };

  const handleParamSubmit = () => {
    if (!paramVal.trim()) { setParamErr('Required'); return; }
    const params = paramAction === 'kill_process'
      ? { name: paramVal.trim() }
      : { service_name: paramVal.trim() };
    setParam(null);
    fire(paramAction, params);
  };

  // Which actions are anomaly-suggested based on live metrics
  const m   = metrics || {};
  const suggested = new Set();
  if ((m.memory || 0) >= 80) { suggested.add('free_memory'); suggested.add('run_gc'); }
  if ((m.disk   || 0) >= 80) suggested.add('disk_cleanup');
  if ((m.cpu    || 0) >= 85) suggested.add('free_memory');

  return (
    <div style={{ ...PANEL }}>
      {/* Header */}
      <div style={{ padding: '16px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
        <Bot size={14} color={C.amber} />
        <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>COMMAND CENTER</span>
        <InfoTip size={13} info="Send allowlisted remediation commands to this agent. The agent must be LIVE and have ALLOW_SYSTEM_ACTIONS=true set. Commands are queued and picked up on the next heartbeat (≤3s)." />
        {agentStatus !== 'live' && (
          <span style={{ marginLeft: 'auto', ...MONO, fontSize: 10, color: C.text4 }}>
            Agent must be LIVE to send commands
          </span>
        )}
      </div>

      {/* Param input modal (inline) */}
      {paramAction && (
        <div style={{ margin: '16px 22px', padding: '16px', borderRadius: 8, background: C.surface2, border: `1px solid ${C.border}` }}>
          <p style={{ ...MONO, fontSize: 11, color: C.amber, margin: '0 0 10px' }}>
            {paramAction === 'kill_process' ? 'Process name or PID:' : 'Service name:'}
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              autoFocus
              value={paramVal}
              onChange={e => setParamVal(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleParamSubmit(); if (e.key === 'Escape') setParam(null); }}
              placeholder={paramAction === 'kill_process' ? 'e.g. chrome or 1234' : 'e.g. nginx'}
              style={{ flex: 1, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6, padding: '8px 12px', ...MONO, fontSize: 12, color: C.text1, outline: 'none' }}
            />
            <button onClick={handleParamSubmit} style={{ padding: '8px 16px', borderRadius: 6, background: C.amberAlpha, border: '1px solid rgba(245,158,11,0.3)', color: C.amber, cursor: 'pointer', ...MONO, fontSize: 11 }}>
              Send
            </button>
            <button onClick={() => setParam(null)} style={{ padding: '8px 12px', borderRadius: 6, background: 'transparent', border: `1px solid ${C.border}`, color: C.text3, cursor: 'pointer', ...MONO, fontSize: 11 }}>
              ✕
            </button>
          </div>
          {paramErr && <p style={{ ...MONO, fontSize: 11, color: C.red, margin: '6px 0 0' }}>{paramErr}</p>}
        </div>
      )}

      {/* Action buttons grid */}
      <div style={{ padding: '16px 22px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
        {Object.entries(ACTION_META).map(([action, meta]) => {
          const isSending = sending[action];
          const isOk      = sent[action] === 'ok';
          const isErr     = sent[action] === 'err';
          const isSugg    = suggested.has(action);
          const disabled  = agentStatus !== 'live' || isSending;

          let bg     = disabled ? 'transparent' : (isSugg ? 'rgba(245,158,11,0.07)' : 'transparent');
          let border = disabled ? C.border : (isOk ? 'rgba(45,212,191,0.3)' : isErr ? 'rgba(248,113,113,0.3)' : isSugg ? 'rgba(245,158,11,0.3)' : C.border);
          let color  = disabled ? C.text4 : (isOk ? C.teal : isErr ? C.red : isSugg ? C.amber : C.text2);

          return (
            <button
              key={action}
              onClick={() => !disabled && handleClick(action)}
              disabled={disabled}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 14px',
                borderRadius: 8, cursor: disabled ? 'not-allowed' : 'pointer',
                background: bg, border: `1px solid ${border}`, color,
                textAlign: 'left', transition: 'all 0.15s', opacity: disabled ? 0.45 : 1,
                position: 'relative',
              }}
              onMouseEnter={e => { if (!disabled) { e.currentTarget.style.background = 'rgba(245,158,11,0.08)'; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.25)'; } }}
              onMouseLeave={e => { if (!disabled) { e.currentTarget.style.background = bg; e.currentTarget.style.borderColor = border; } }}
            >
              <span style={{ marginTop: 1, flexShrink: 0 }}>{meta.icon}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ ...UI, fontSize: 12, fontWeight: 600, color: 'inherit', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {meta.label}
                  {isSugg && !isOk && !isErr && (
                    <span style={{ ...MONO, fontSize: 9, color: C.amber, background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 3, padding: '1px 5px', letterSpacing: '0.06em' }}>
                      FIX
                    </span>
                  )}
                  {isOk && <span style={{ color: C.teal, fontSize: 11 }}>✓ queued</span>}
                  {isErr && <span style={{ color: C.red,  fontSize: 11 }}>✗ failed</span>}
                </div>
                <div style={{ ...UI, fontSize: 11, color: C.text4, lineHeight: 1.4 }}>{meta.desc}</div>
              </div>
              {isSending && (
                <span style={{ position: 'absolute', right: 10, top: 10, ...MONO, fontSize: 10, color: C.amber, animation: 'pulse 1s ease-in-out infinite' }}>…</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Command History Table ────────────────────────────────────────────────────
function CommandHistory({ agentId, refreshTick }) {
  const [data, setData] = useState({ pending: [], history: [], actions: {} });

  const load = useCallback(async () => {
    const d = await agentApi.getCommands(agentId);
    setData(d);
  }, [agentId]);

  useEffect(() => { load(); }, [load, refreshTick]);

  const all = [...data.pending.map(c => ({ ...c, _pending: true })), ...data.history];
  if (!all.length) {
    return (
      <div style={{ ...PANEL }}>
        <div style={{ padding: '16px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Terminal size={14} color={C.amber} />
          <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>COMMAND LOG</span>
        </div>
        <div style={{ padding: '36px 0', textAlign: 'center' }}>
          <span style={{ ...MONO, fontSize: 11, color: C.text4 }}>No commands sent yet.</span>
        </div>
      </div>
    );
  }

  return (
    <div style={{ ...PANEL, overflow: 'hidden' }}>
      <div style={{ padding: '16px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
        <Terminal size={14} color={C.amber} />
        <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>COMMAND LOG</span>
        <span style={{ marginLeft: 'auto', ...MONO, fontSize: 10, color: C.text4 }}>
          {data.pending.length > 0 && (
            <span style={{ color: C.amber }}>
              {data.pending.length} pending ·{' '}
            </span>
          )}
          {data.history.length} completed
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.border}` }}>
              {['Status', 'Action', 'Source', 'Sent', 'Result / Error'].map(h => (
                <th key={h} style={{ padding: '8px 14px', ...MONO, fontSize: 9, letterSpacing: '0.09em', color: C.text4, textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {all.slice(0, 50).map((cmd, i) => {
              const sm = CMD_STATUS[cmd.status] || CMD_STATUS.pending;
              const isLast = i === Math.min(all.length, 50) - 1;
              return (
                <tr key={cmd.id} style={{ borderBottom: isLast ? 'none' : `1px solid rgba(42,40,32,0.5)` }}>
                  <td style={{ padding: '10px 14px', whiteSpace: 'nowrap' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: sm.color }}>
                      {sm.icon}
                      <span style={{ ...MONO, fontSize: 10 }}>{sm.label}</span>
                    </span>
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    <span style={{ ...MONO, fontSize: 11, color: C.text1 }}>{cmd.action}</span>
                    {cmd.params && Object.keys(cmd.params).length > 0 && (
                      <span style={{ ...MONO, fontSize: 10, color: C.text4, marginLeft: 8 }}>
                        ({Object.values(cmd.params).join(', ')})
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '10px 14px', whiteSpace: 'nowrap' }}>
                    <span style={{
                      ...MONO, fontSize: 9, letterSpacing: '0.06em',
                      padding: '2px 6px', borderRadius: 4,
                      color: cmd.source === 'auto' ? C.amber : C.teal,
                      background: cmd.source === 'auto' ? 'rgba(245,158,11,0.1)' : 'rgba(45,212,191,0.1)',
                      border: `1px solid ${cmd.source === 'auto' ? 'rgba(245,158,11,0.2)' : 'rgba(45,212,191,0.2)'}`,
                    }}>
                      {cmd.source === 'auto' ? '⚡ AUTO' : '👤 MANUAL'}
                    </span>
                  </td>
                  <td style={{ padding: '10px 14px', whiteSpace: 'nowrap' }}>
                    <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>{fmtTs(cmd.created_at)}</span>
                  </td>
                  <td style={{ padding: '10px 14px', maxWidth: 260 }}>
                    {cmd.result && (
                      <span style={{ ...UI, fontSize: 12, color: C.teal }}>{cmd.result}</span>
                    )}
                    {cmd.error && (
                      <span style={{ ...UI, fontSize: 12, color: C.red }}>{cmd.error}</span>
                    )}
                    {!cmd.result && !cmd.error && cmd.status === 'pending' && (
                      <span style={{ ...MONO, fontSize: 10, color: C.text4, animation: 'pulse 1.5s ease-in-out infinite' }}>
                        waiting for agent…
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Agent Detail View ────────────────────────────────────────────────────────
export function AgentDetail({ agentId, onBack }) {
  const [agent, setAgent]       = useState(null);
  const [history, setHistory]   = useState([]);
  const [cmdTick, setCmdTick]   = useState(0);

  const fetchDetail = useCallback(async () => {
    try {
      const data = await agentsApi.getById(null, agentId);
      if (!data) return;
      setAgent(data);
      if (data.history && data.history.length) {
        setHistory(data.history.map(h => ({
          time: new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          cpu: h.cpu,
          memory: h.memory,
        })));
      }
    } catch {}
  }, [agentId]);

  useEffect(() => {
    fetchDetail();
    const t = setInterval(fetchDetail, 5000);
    return () => clearInterval(t);
  }, [fetchDetail]);

  if (!agent) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <span style={{ ...MONO, fontSize: 11, color: C.text4 }}>LOADING…</span>
      </div>
    );
  }

  const sm      = STATUS_META[agent.status] || STATUS_META.pending;
  const m       = agent.metrics || {};
  const info    = agent.info    || {};
  const chartData = history.length > 1 ? history : [{ time: '…', cpu: 0, memory: 0 }];

  const STATUS_COLOR = { healthy: C.teal, warning: C.amber, critical: C.red };

  // Suggested fix-action per metric
  const metricFix = {
    MEMORY: (m.memory || 0) >= 80 ? 'free_memory' : null,
    DISK:   (m.disk   || 0) >= 80 ? 'disk_cleanup' : null,
    CPU:    (m.cpu    || 0) >= 85 ? 'free_memory'  : null,
  };

  const sendFix = async (action) => {
    try { await agentsApi.sendCommand(null, agentId, action); setCmdTick(t => t + 1); } catch {}
  };

  const tiles = [
    { title: 'CPU',    value: m.cpu    != null ? m.cpu.toFixed(1)    : '—', unit: '%',      status: m.cpu    >= 90 ? 'critical' : m.cpu    >= 75 ? 'warning' : 'healthy', fix: metricFix.CPU,    info: 'Live CPU utilisation on the remote machine via psutil.' },
    { title: 'MEMORY', value: m.memory != null ? m.memory.toFixed(1) : '—', unit: '%',      status: m.memory >= 90 ? 'critical' : m.memory >= 80 ? 'warning' : 'healthy', fix: metricFix.MEMORY, info: `RAM usage. Total: ${fmtBytes(m.memory_total)}, Used: ${fmtBytes(m.memory_used)}.` },
    { title: 'DISK',   value: m.disk   != null ? m.disk.toFixed(1)   : '—', unit: '%',      status: m.disk   >= 90 ? 'critical' : m.disk   >= 80 ? 'warning' : 'healthy', fix: metricFix.DISK,   info: 'Primary partition disk usage on the remote machine.' },
    { title: 'NET IN', value: m.network_in != null ? (m.network_in / 1048576).toFixed(1) : '—', unit: 'MB', status: 'healthy', fix: null, info: 'Total bytes received since last boot (all interfaces).' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Back + header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button
          onClick={onBack}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: 'none', color: C.text3, cursor: 'pointer', ...MONO, fontSize: 11, padding: 0 }}
          onMouseEnter={e => { e.currentTarget.style.color = C.amber; }}
          onMouseLeave={e => { e.currentTarget.style.color = C.text3; }}
        >
          <ChevronLeft size={14} /> ALL AGENTS
        </button>
        <span style={{ color: C.text4 }}>·</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: sm.dot, boxShadow: `0 0 8px ${sm.dot}80`, display: 'inline-block', animation: sm.pulse ? 'pulse 1.5s ease-in-out infinite' : 'none' }} />
          <span style={{ ...UI, fontSize: 16, fontWeight: 700, color: C.text1 }}>{agent.label}</span>
          <span style={{ ...MONO, fontSize: 10, color: sm.color, background: `${sm.dot}15`, border: `1px solid ${sm.dot}40`, borderRadius: 4, padding: '2px 8px' }}>{sm.label}</span>
        </div>
        <span style={{ marginLeft: 'auto', ...MONO, fontSize: 10, color: C.text4 }}>
          {fmtLastSeen(agent.last_seen)} · {info.hostname} · {info.os}
        </span>
      </div>

      {/* Metric tiles — with inline Fix Issue button */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {tiles.map(t => {
          const col = STATUS_COLOR[t.status] || C.teal;
          const isAnomaly = t.status === 'warning' || t.status === 'critical';
          return (
            <div key={t.title} style={{ ...PANEL, padding: '18px 20px', borderTop: `2px solid ${col}`, position: 'relative' }}>
              <div style={{ position: 'absolute', top: 10, right: 10 }}>
                <InfoTip info={t.info} />
              </div>
              <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.14em', color: C.text4, marginBottom: 10 }}>{t.title}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                <span style={{ ...DISPLAY, fontSize: '2.8rem', lineHeight: 1, color: C.text1 }}>{t.value}</span>
                <span style={{ ...MONO, fontSize: 12, color: C.text3 }}>{t.unit}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: col, boxShadow: `0 0 6px ${col}80`, display: 'inline-block' }} />
                <span style={{ ...MONO, fontSize: 10, color: col, letterSpacing: '0.08em' }}>{t.status.toUpperCase()}</span>
                {/* Fix Issue button shown when anomaly + live */}
                {isAnomaly && t.fix && agent.status === 'live' && (
                  <button
                    onClick={() => sendFix(t.fix)}
                    style={{
                      marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4,
                      padding: '3px 9px', borderRadius: 4, cursor: 'pointer',
                      background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.3)',
                      color: C.red, ...MONO, fontSize: 9, letterSpacing: '0.06em',
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'rgba(248,113,113,0.2)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'rgba(248,113,113,0.1)'; }}
                    title={`Auto-fix: ${t.fix}`}
                  >
                    <Play size={9} /> FIX ISSUE
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Live chart */}
      <div style={PANEL}>
        <div style={{ padding: '16px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Circle size={8} color={C.teal} fill={C.teal} style={{ animation: 'pulse 1.5s ease-in-out infinite' }} />
          <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>LIVE PERFORMANCE</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 16 }}>
            {[['#F59E0B', 'CPU'], ['#2DD4BF', 'Memory']].map(([c, l]) => (
              <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 5, ...UI, fontSize: 12, color: C.text3 }}>
                <span style={{ width: 20, height: 2, background: c, display: 'inline-block', borderRadius: 1 }} />{l}
              </span>
            ))}
          </div>
        </div>
        <div style={{ padding: '20px 22px', height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(42,40,32,0.8)" vertical={false} />
              <XAxis dataKey="time" stroke="#3A342D" tick={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", fill: '#4A443D' }} />
              <YAxis stroke="#3A342D" tick={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", fill: '#4A443D' }} domain={[0, 100]} />
              <Tooltip
                contentStyle={{ backgroundColor: 'rgb(31,29,24)', borderColor: 'rgba(42,40,32,0.9)', borderRadius: 8, fontFamily: "'IBM Plex Mono', monospace", fontSize: 11 }}
                labelStyle={{ color: C.text2 }} itemStyle={{ color: C.text1 }}
              />
              <Line type="monotone" dataKey="cpu"    stroke="#F59E0B" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="memory" stroke="#2DD4BF" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Execution Mode Toggle */}
      <div style={{ ...PANEL, padding: '14px 22px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Zap size={13} color={C.amber} />
          <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.1em', color: C.text2 }}>EXECUTION MODE</span>
        </div>
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {[
            { key: 'dry_run',          label: 'DRY RUN',  color: C.text3 },
            { key: 'manual_approval',  label: 'APPROVAL', color: C.amber },
            { key: 'auto_safe',        label: 'AUTO SAFE', color: C.teal },
          ].map(opt => {
            const active = (agent.execution_mode || 'dry_run') === opt.key;
            return (
              <button
                key={opt.key}
                onClick={async () => { try { await agentsApi.setExecMode(null, agentId, opt.key); fetchDetail(); } catch {} }}
                style={{
                  padding: '4px 12px', borderRadius: 6, cursor: 'pointer', ...MONO, fontSize: 10,
                  background: active ? `${opt.color}20` : 'transparent',
                  border: `1px solid ${active ? opt.color : C.border}`,
                  color: active ? opt.color : C.text4,
                  transition: 'all 0.15s',
                }}
              >{opt.label}</button>
            );
          })}
        </div>
      </div>

      {/* Pending Approvals */}
      {agent.pending_approvals && agent.pending_approvals.length > 0 && (
        <div style={PANEL}>
          <div style={{ padding: '14px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
            <CheckCircle size={14} color={C.amber} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>AWAITING APPROVAL</span>
            <span style={{ marginLeft: 6, ...MONO, fontSize: 10, background: `${C.amber}18`, color: C.amber, border: `1px solid ${C.amber}40`, borderRadius: 10, padding: '1px 8px' }}>{agent.pending_approvals.length}</span>
          </div>
          <div style={{ padding: '12px 22px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {agent.pending_approvals.map(ap => (
              <div key={ap.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', borderRadius: 8, background: `${C.amber}0a`, border: `1px solid ${C.amber}30` }}>
                <div style={{ flex: 1 }}>
                  <span style={{ ...MONO, fontSize: 11, color: C.amber }}>{ap.action}</span>
                  <span style={{ ...MONO, fontSize: 11, color: C.text3 }}> → {ap.target}</span>
                  <span style={{ ...MONO, fontSize: 10, color: C.text4, marginLeft: 10 }}>{new Date(ap.created_at).toLocaleTimeString()}</span>
                </div>
                <button
                  onClick={async () => { try { await agentsApi.approveAction(agentId, ap.id); fetchDetail(); } catch {} }}
                  style={{ padding: '4px 14px', borderRadius: 6, cursor: 'pointer', background: `${C.teal}20`, border: `1px solid ${C.teal}50`, color: C.teal, ...MONO, fontSize: 10 }}
                >APPROVE</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Inline Alerts */}
      {agent.alerts && agent.alerts.length > 0 && (
        <div style={PANEL}>
          <div style={{ padding: '14px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
            <AlertTriangle size={14} color={C.red} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>ACTIVE ALERTS</span>
            <span style={{ marginLeft: 6, ...MONO, fontSize: 10, background: 'rgba(248,113,113,0.12)', color: C.red, border: `1px solid rgba(248,113,113,0.3)`, borderRadius: 10, padding: '1px 8px' }}>{agent.alerts.length}</span>
          </div>
          <div style={{ padding: '12px 22px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {agent.alerts.map(al => {
              const sev = al.severity === 'critical' ? C.red : al.severity === 'high' ? C.amber : C.teal;
              return (
                <div key={al.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 14, padding: '12px 16px', borderRadius: 8, background: `${sev}0d`, border: `1px solid ${sev}30` }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: sev, flexShrink: 0, marginTop: 4 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ ...MONO, fontSize: 11, color: sev, letterSpacing: '0.08em' }}>{al.severity.toUpperCase()}</span>
                      <span style={{ ...UI, fontSize: 13, fontWeight: 600, color: C.text1 }}>{al.title}</span>
                    </div>
                    <p style={{ ...UI, fontSize: 12, color: C.text3, margin: 0 }}>{al.detail}</p>
                    <p style={{ ...MONO, fontSize: 10, color: C.text4, margin: '4px 0 0' }}>{new Date(al.created_at).toLocaleString()}</p>
                  </div>
                  <button
                    onClick={async () => {
                      try { await agentsApi.resolveAlert(null, agentId, al.id); fetchDetail(); } catch {}
                    }}
                    style={{ flexShrink: 0, padding: '4px 12px', borderRadius: 6, background: 'transparent', border: `1px solid ${C.border}`, color: C.text3, cursor: 'pointer', ...MONO, fontSize: 10 }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = C.teal; e.currentTarget.style.color = C.teal; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.text3; }}
                  >
                    RESOLVE
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Activity Panel */}
      {agent.ai_history && agent.ai_history.length > 0 && (
        <div style={PANEL}>
          <div style={{ padding: '14px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Bot size={14} color={C.teal} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>AI DECISIONS</span>
            <span style={{ marginLeft: 6, ...MONO, fontSize: 10, background: `${C.teal}18`, color: C.teal, border: `1px solid ${C.teal}40`, borderRadius: 10, padding: '1px 8px' }}>{agent.ai_history.length}</span>
          </div>
          <div style={{ padding: '12px 22px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {agent.ai_history.map((d, i) => {
              const statusColor = d.status === 'dry_run' ? C.amber : d.status === 'queued' ? C.teal : C.text4;
              const statusLabel = d.status === 'dry_run' ? 'DRY RUN' : d.status === 'queued' ? 'QUEUED' : 'NEEDS REVIEW';
              const confPct = Math.round((d.confidence || 0) * 100);
              return (
                <div key={i} style={{ padding: '14px 16px', borderRadius: 8, background: `${C.teal}08`, border: `1px solid ${C.border}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <span style={{ ...MONO, fontSize: 10, color: C.amber, letterSpacing: '0.08em' }}>{d.alert_category?.toUpperCase()}</span>
                    <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>·</span>
                    <span style={{ ...MONO, fontSize: 10, background: `${statusColor}18`, color: statusColor, border: `1px solid ${statusColor}40`, borderRadius: 4, padding: '1px 7px' }}>{statusLabel}</span>
                    <span style={{ marginLeft: 'auto', ...MONO, fontSize: 10, color: C.text4 }}>{new Date(d.timestamp).toLocaleTimeString()}</span>
                  </div>
                  {d.root_cause && <p style={{ ...UI, fontSize: 12, color: C.text2, margin: '0 0 6px', fontWeight: 600 }}>{d.root_cause}</p>}
                  {d.summary && <p style={{ ...UI, fontSize: 12, color: C.text3, margin: '0 0 8px' }}>{d.summary}</p>}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                    {d.recommended_action && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 5, ...MONO, fontSize: 10, color: C.teal }}>
                        <Zap size={10} /> {d.recommended_action}
                      </span>
                    )}
                    <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>confidence {confPct}%</span>
                    {d.impact && <span style={{ ...MONO, fontSize: 10, color: C.text4 }}>impact {d.impact}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Learning Feedback Panel */}
      {agent.feedback && agent.feedback.length > 0 && (
        <div style={PANEL}>
          <div style={{ padding: '14px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <RotateCcw size={14} color={C.teal} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>LEARNING FEEDBACK</span>
            <span style={{ marginLeft: 6, ...MONO, fontSize: 10, background: `${C.teal}18`, color: C.teal, border: `1px solid ${C.teal}40`, borderRadius: 10, padding: '1px 8px' }}>{agent.feedback.length} outcomes</span>
            {agent.success_rates && Object.entries(agent.success_rates).map(([act, rate]) => (
              <span key={act} style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, ...MONO, fontSize: 10, color: rate >= 70 ? C.teal : rate >= 40 ? C.amber : C.red }}>
                <Flame size={10} /> {act.replace('_', ' ')} success {rate}%
              </span>
            ))}
          </div>
          <div style={{ padding: '12px 22px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {agent.feedback.map((fb, i) => {
              const ok   = fb.success;
              const col  = ok ? C.teal : C.red;
              const cpuDelta = (fb.cpu_after - fb.cpu_before).toFixed(1);
              const memDelta = (fb.memory_after - fb.memory_before).toFixed(1);
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', borderRadius: 8, background: `${col}08`, border: `1px solid ${col}25` }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: col, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <span style={{ ...MONO, fontSize: 11, color: col }}>{ok ? '✓' : '✗'}</span>
                    <span style={{ ...MONO, fontSize: 11, color: C.text2, marginLeft: 8 }}>{fb.action}</span>
                    {fb.target && <span style={{ ...MONO, fontSize: 11, color: C.text3 }}> → {fb.target}</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 16, ...MONO, fontSize: 10, color: C.text4 }}>
                    <span>CPU {fb.cpu_before}% → {fb.cpu_after}% <span style={{ color: parseFloat(cpuDelta) < 0 ? C.teal : C.red }}>{cpuDelta > 0 ? '+' : ''}{cpuDelta}%</span></span>
                    <span>MEM {fb.memory_before}% → {fb.memory_after}% <span style={{ color: parseFloat(memDelta) < 0 ? C.teal : C.red }}>{memDelta > 0 ? '+' : ''}{memDelta}%</span></span>
                    <span style={{ color: C.text4 }}>{new Date(fb.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Activity Timeline */}
      {(() => {
        const events = [
          ...(agent.alerts || []).map(a => ({ ts: a.created_at, type: 'alert', label: a.title, sub: a.detail, color: C.red })),
          ...(agent.ai_history || []).map(d => ({ ts: d.timestamp, type: 'ai', label: `AI: ${d.recommended_action || 'analyzed'}`, sub: d.root_cause, color: C.teal })),
        ].sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, 10);
        if (!events.length) return null;
        return (
          <div style={PANEL}>
            <div style={{ padding: '14px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
              <Clock size={14} color={C.amber} />
              <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>ACTIVITY TIMELINE</span>
            </div>
            <div style={{ padding: '12px 22px', display: 'flex', flexDirection: 'column', gap: 0 }}>
              {events.map((ev, i) => (
                <div key={i} style={{ display: 'flex', gap: 14, paddingBottom: i < events.length - 1 ? 14 : 0 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: ev.color, marginTop: 3, flexShrink: 0 }} />
                    {i < events.length - 1 && <span style={{ width: 1, flex: 1, background: C.border, marginTop: 4 }} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0, paddingBottom: 2 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ ...UI, fontSize: 12, fontWeight: 600, color: C.text1 }}>{ev.label}</span>
                      <span style={{ ...MONO, fontSize: 10, color: C.text4, marginLeft: 'auto', flexShrink: 0 }}>{new Date(ev.ts).toLocaleTimeString()}</span>
                    </div>
                    {ev.sub && <p style={{ ...UI, fontSize: 11, color: C.text3, margin: '2px 0 0' }}>{ev.sub}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Command Center */}
      <CommandCenter
        agentId={agentId}
        agentStatus={agent.status}
        metrics={m}
        onCommandSent={() => setCmdTick(t => t + 1)}
      />

      {/* Command History */}
      <CommandHistory agentId={agentId} refreshTick={cmdTick} />

      {/* System info + extra metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* System info */}
        <div style={{ ...PANEL, padding: '20px 22px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
            <Server size={14} color={C.amber} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>SYSTEM INFO</span>
          </div>
          {[
            { label: 'Hostname',   value: info.hostname },
            { label: 'OS',         value: info.os },
            { label: 'Platform',   value: info.platform },
            { label: 'CPU Model',  value: info.cpu_model },
            { label: 'CPU Cores',  value: info.cpu_cores },
            { label: 'Python',     value: info.python },
            { label: 'Uptime',     value: fmtUptime(m.uptime_secs) },
            { label: 'Processes',  value: m.processes },
            { label: 'Load Avg',   value: m.load_avg },
            { label: 'Temp (CPU)', value: m.temperature != null ? `${m.temperature}°C` : null },
          ].filter(r => r.value != null).map(({ label, value }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid rgba(42,40,32,0.6)` }}>
              <span style={{ ...UI, fontSize: 12, color: C.text3 }}>{label}</span>
              <span style={{ ...MONO, fontSize: 11, color: C.text2 }}>{value}</span>
            </div>
          ))}
        </div>

        {/* Network + memory detail */}
        <div style={{ ...PANEL, padding: '20px 22px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
            <Wifi size={14} color={C.amber} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>NETWORK & MEMORY</span>
          </div>
          {[
            { label: 'Net Received',  value: fmtBytes(m.network_in)   },
            { label: 'Net Sent',      value: fmtBytes(m.network_out)  },
            { label: 'Memory Total',  value: fmtBytes(m.memory_total) },
            { label: 'Memory Used',   value: fmtBytes(m.memory_used)  },
            { label: 'Memory Free',   value: (m.memory_total && m.memory_used) ? fmtBytes(m.memory_total - m.memory_used) : null },
          ].filter(r => r.value && r.value !== '—').map(({ label, value }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid rgba(42,40,32,0.6)` }}>
              <span style={{ ...UI, fontSize: 12, color: C.text3 }}>{label}</span>
              <span style={{ ...MONO, fontSize: 11, color: C.text2 }}>{value}</span>
            </div>
          ))}

          <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[
              { label: 'CPU',  icon: <Cpu size={11} />,        pct: m.cpu    },
              { label: 'MEM',  icon: <MemoryStick size={11} />, pct: m.memory },
              { label: 'DISK', icon: <HardDrive size={11} />,   pct: m.disk   },
            ].map(({ label, icon, pct }) => (
              <div key={label}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                  <span style={{ color: C.text4 }}>{icon}</span>
                  <span style={{ ...MONO, fontSize: 9, letterSpacing: '0.09em', color: C.text4 }}>{label}</span>
                  <span style={{ marginLeft: 'auto', ...MONO, fontSize: 11, color: pct >= 90 ? C.red : pct >= 75 ? C.amber : C.teal }}>
                    {pct != null ? `${pct.toFixed(1)}%` : '—'}
                  </span>
                </div>
                <Bar pct={pct} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function RemoteAgents() {
  const [agents, setAgents]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [spinning, setSpinning]   = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [selected, setSelected]   = useState(null); // agent_id for detail view

  const fetchAgents = useCallback(async () => {
    try {
      const data = await agentsApi.list();
      setAgents(data);
    } catch {} finally {
      setLoading(false);
    }
  }, []);

  // Poll every 5s to keep status fresh
  useEffect(() => {
    fetchAgents();
    const t = setInterval(fetchAgents, 5000);
    return () => clearInterval(t);
  }, [fetchAgents]);

  const handleRemove = async (id) => {
    if (!window.confirm('Revoke this agent token and remove the device? The agent script will stop working.')) return;
    await agentsApi.remove(null, id);
    if (selected === id) setSelected(null);
    setAgents(prev => prev.filter(a => a.id !== id));
  };

  const handleRefresh = async () => {
    setSpinning(true);
    await fetchAgents();
    setTimeout(() => setSpinning(false), 500);
  };

  const liveCount    = agents.filter(a => a.status === 'live').length;
  const offlineCount = agents.filter(a => a.status === 'offline').length;
  const pendingCount = agents.filter(a => a.status === 'pending').length;

  if (selected) {
    return (
      <div style={{ padding: 24 }}>
        <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
        <AgentDetail agentId={selected} onBack={() => setSelected(null)} />
      </div>
    );
  }

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 24 }}>
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <div>
          <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', color: C.text1, margin: 0, lineHeight: 1 }}>
            Remote Agents
          </h1>
          <p style={{ ...MONO, fontSize: 11, letterSpacing: '0.1em', color: C.text4, marginTop: 6, margin: '6px 0 0' }}>
            PUSH-BASED SYSTEM MONITORING · REAL METRICS · ZERO VPN
            <InfoTip size={13} info="Each remote agent is a lightweight Python script running on a user's machine. It pushes real psutil metrics every 3 seconds over HTTP — no VPN, no port forwarding, no firewall config needed." />
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={handleRefresh}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, background: 'transparent', border: `1px solid ${C.border}`, color: C.text3, cursor: 'pointer', ...MONO, fontSize: 11 }}
            onMouseEnter={e => { e.currentTarget.style.color = C.text1; e.currentTarget.style.borderColor = C.amber + '60'; }}
            onMouseLeave={e => { e.currentTarget.style.color = C.text3; e.currentTarget.style.borderColor = C.border; }}
          >
            <RefreshCw size={13} style={spinning ? { animation: 'spin 0.6s linear infinite' } : {}} />
            Refresh
          </button>
          <button
            onClick={() => setShowModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 18px', borderRadius: 8, background: C.amberAlpha, border: '1px solid rgba(245,158,11,0.35)', color: C.amber, cursor: 'pointer', ...MONO, fontSize: 11, letterSpacing: '0.08em' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.18)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = C.amberAlpha; }}
          >
            <Plus size={13} /> NEW AGENT
          </button>
        </div>
      </div>

      {/* Summary pills */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {[
          { label: 'LIVE',    count: liveCount,    color: C.teal  },
          { label: 'OFFLINE', count: offlineCount, color: C.red   },
          { label: 'PENDING', count: pendingCount, color: C.amber },
          { label: 'TOTAL',   count: agents.length, color: C.text3 },
        ].map(({ label, count, color }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px', borderRadius: 20, background: C.surface2, border: `1px solid ${C.border}` }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, display: 'inline-block' }} />
            <span style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: C.text3 }}>{label}</span>
            <span style={{ ...MONO, fontSize: 13, fontWeight: 700, color }}>{count}</span>
          </div>
        ))}
      </div>

      {/* Agent grid / empty state */}
      {loading ? (
        <div style={{ padding: '64px 0', textAlign: 'center' }}>
          <span style={{ ...MONO, fontSize: 11, color: C.text4 }}>LOADING…</span>
        </div>
      ) : agents.length === 0 ? (
        <div style={{ ...PANEL, padding: '64px 24px', textAlign: 'center' }}>
          <Monitor size={40} color={C.text4} style={{ margin: '0 auto 16px', opacity: 0.4, display: 'block' }} />
          <p style={{ ...UI, fontSize: 15, fontWeight: 600, color: C.text2, margin: '0 0 8px' }}>No remote agents yet</p>
          <p style={{ ...UI, fontSize: 13, color: C.text4, margin: '0 0 24px', lineHeight: 1.6, maxWidth: 400, marginLeft: 'auto', marginRight: 'auto' }}>
            Click <strong style={{ color: C.amber }}>New Agent</strong> to generate a token.
            Share the one-line install command and the device will appear here within seconds.
          </p>
          <button
            onClick={() => setShowModal(true)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 22px', borderRadius: 8, background: C.amberAlpha, border: '1px solid rgba(245,158,11,0.35)', color: C.amber, cursor: 'pointer', ...MONO, fontSize: 12 }}
          >
            <Plus size={14} /> NEW AGENT
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {agents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onSelect={a => setSelected(a.id)}
              onRemove={handleRemove}
            />
          ))}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <NewAgentModal
          onClose={() => setShowModal(false)}
          onCreated={() => fetchAgents()}
        />
      )}
    </div>
  );
}
