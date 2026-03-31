/**
 * AgentDashboard.js — Isolated System Probe
 * Full-screen diagnostic view for a single monitored agent.
 * Opens as an overlay when an AgentCard is clicked in InfraHub.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import { metricsApi, alertsApi, agentsApi, wmiApi } from '../services/resiloApi';
import {
  ArrowLeft, RefreshCw, Activity, Server, Clock,
  AlertTriangle, CheckCircle2, Terminal, Zap, Wifi,
  Cpu, HardDrive, MemoryStick,
  TrendingUp, TrendingDown,
  Shield, Info,
} from 'lucide-react';

// ─── Design tokens (matches InfraHub palette + adds probe-specific) ────────────
const T = {
  bg:      'rgb(8, 7, 5)',
  panel:   'rgb(15, 14, 11)',
  panel2:  'rgb(20, 19, 15)',
  border:  'rgba(48,44,36,0.9)',
  borderB: 'rgba(72,66,52,0.5)',
  text:    '#F5F0E8',
  sub:     '#A89F8C',
  muted:   '#5A5249',
  dim:     '#2E2A24',
  amber:   '#F59E0B',
  amberD:  '#D97706',
  teal:    '#2DD4BF',
  red:     '#F87171',
  blue:    '#60A5FA',
  green:   '#34D399',
  disp:    "'Bebas Neue', sans-serif",
  mono:    "'IBM Plex Mono', monospace",
  ui:      "'Outfit', sans-serif",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function metricColor(v) {
  if (v == null) return T.muted;
  if (v > 85) return T.red;
  if (v > 70) return T.amber;
  return T.teal;
}

function fmtBytes(b) {
  if (b == null) return '—';
  if (b < 1024) return `${b} B`;
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`;
  return `${(b / 1024 ** 3).toFixed(2)} GB`;
}

function fmtUptime(s) {
  if (!s) return '—';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
}

function relTime(ts) {
  if (!ts) return 'never';
  const d = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (d < 5)   return 'just now';
  if (d < 60)  return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  return `${Math.floor(d / 3600)}h ago`;
}

function deriveStatus(lastSeen) {
  if (!lastSeen) return 'offline';
  const s = (Date.now() - new Date(lastSeen).getTime()) / 1000;
  if (s <= 30)  return 'online';
  if (s <= 120) return 'warning';
  return 'offline';
}

function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ─── Animated counter (counts from 0 on first render) ─────────────────────────
function AnimCount({ value, decimals = 0, duration = 900 }) {
  const [display, setDisplay] = useState(0);
  const mounted = useRef(false);

  useEffect(() => {
    if (value == null) return;
    if (!mounted.current) {
      mounted.current = true;
      const start = performance.now();
      const from = 0;
      const to = value;
      const tick = (now) => {
        const p = Math.min((now - start) / duration, 1);
        const e = 1 - Math.pow(1 - p, 3);
        setDisplay(from + (to - from) * e);
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    } else {
      setDisplay(value);
    }
  }, [value, duration]);

  if (value == null) return <>—</>;
  return <>{Number(display).toFixed(decimals)}</>;
}

// ─── Mini SVG sparkline ────────────────────────────────────────────────────────
function Spark({ values = [], color = T.teal, w = 96, h = 32 }) {
  if (values.length < 2) return <div style={{ width: w, height: h }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pad = 3;
  const pts = values.map((v, i) => [
    pad + (i / (values.length - 1)) * (w - pad * 2),
    (h - pad) - ((v - min) / range) * (h - pad * 2),
  ]);
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const fill = `${line} L${(w - pad).toFixed(1)},${(h).toFixed(1)} L${pad},${h} Z`;
  const uid = color.replace(/[^a-z0-9]/gi, '');
  return (
    <svg width={w} height={h} style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <linearGradient id={`sp-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={fill} fill={`url(#sp-${uid})`} />
      <path d={line} stroke={color} strokeWidth="1.8" fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
      {/* last point dot */}
      <circle
        cx={pts[pts.length - 1][0].toFixed(1)}
        cy={pts[pts.length - 1][1].toFixed(1)}
        r="2.5" fill={color}
      />
    </svg>
  );
}

// ─── Metric card ──────────────────────────────────────────────────────────────
function MetricCard({ icon: Icon, label, value, unit = '%', sparkValues = [], delay = 0, extra }) {
  const color = metricColor(value);
  const prev = sparkValues.length >= 2 ? sparkValues[sparkValues.length - 2] : null;
  const trend = prev != null ? value - prev : 0;

  return (
    <div style={{
      background: T.panel,
      border: `1px solid ${T.border}`,
      borderTop: `2px solid ${color}`,
      borderRadius: 10,
      padding: '16px 18px',
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      animation: `probe-slide ${0.4 + delay}s ease both`,
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* subtle glow */}
      <div style={{
        position: 'absolute', top: -20, right: -20,
        width: 80, height: 80, borderRadius: '50%',
        background: `radial-gradient(circle, ${color}18 0%, transparent 70%)`,
        pointerEvents: 'none',
      }} />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon size={13} color={color} />
          <span style={{ fontFamily: T.mono, fontSize: '9px', letterSpacing: '0.12em', color: T.muted }}>
            {label}
          </span>
        </div>
        {trend !== 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {trend > 0
              ? <TrendingUp size={10} color={value > 80 ? T.red : T.amber} />
              : <TrendingDown size={10} color={T.teal} />}
            <span style={{ fontFamily: T.mono, fontSize: '8px', color: trend > 0 ? (value > 80 ? T.red : T.amber) : T.teal }}>
              {trend > 0 ? '+' : ''}{trend.toFixed(1)}
            </span>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <span style={{ fontFamily: T.disp, fontSize: '2.8rem', lineHeight: 1, color: value != null ? T.text : T.muted }}>
            <AnimCount value={value} decimals={1} />
          </span>
          {value != null && (
            <span style={{ fontFamily: T.mono, fontSize: '13px', color: T.muted, marginLeft: 3 }}>{unit}</span>
          )}
        </div>
        <Spark values={sparkValues} color={color} />
      </div>

      {/* progress bar */}
      {value != null && (
        <div style={{ height: 2, borderRadius: 2, background: T.dim, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${Math.min(100, value)}%`,
            background: color, borderRadius: 2,
            boxShadow: `0 0 6px ${color}80`,
            transition: 'width 0.8s ease',
          }} />
        </div>
      )}

      {extra && (
        <div style={{ fontFamily: T.mono, fontSize: '9px', color: T.muted, letterSpacing: '0.05em' }}>{extra}</div>
      )}
    </div>
  );
}

// ─── Custom chart tooltip ──────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: T.panel2, border: `1px solid ${T.border}`,
      borderRadius: 8, padding: '10px 14px',
      fontFamily: T.mono, fontSize: '10px',
    }}>
      <div style={{ color: T.muted, marginBottom: 6, letterSpacing: '0.06em' }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
          <span style={{ width: 8, height: 2, background: p.color, display: 'inline-block', borderRadius: 1 }} />
          <span style={{ color: T.sub }}>{p.name}:</span>
          <span style={{ color: T.text, fontWeight: 600 }}>{Number(p.value).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}

// ─── Alert row ────────────────────────────────────────────────────────────────
function AlertRow({ alert }) {
  const sevColor = alert.severity === 'critical' ? T.red : alert.severity === 'warning' ? T.amber : T.blue;
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 10,
      padding: '10px 14px',
      borderBottom: `1px solid ${T.border}`,
    }}>
      <div style={{
        width: 6, height: 6, borderRadius: '50%',
        background: sevColor, flexShrink: 0, marginTop: 5,
        boxShadow: `0 0 6px ${sevColor}`,
      }} />
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: T.ui, fontSize: '12px', color: T.text, fontWeight: 500 }}>
          {alert.title || alert.metric || 'Alert'}
        </div>
        <div style={{ fontFamily: T.mono, fontSize: '9px', color: T.muted, marginTop: 2 }}>
          {alert.message || `Threshold: ${alert.threshold}`} · {relTime(alert.triggered_at || alert.created_at)}
        </div>
      </div>
      <span style={{
        fontFamily: T.mono, fontSize: '8px', letterSpacing: '0.08em',
        color: sevColor, background: `${sevColor}14`,
        border: `1px solid ${sevColor}28`, padding: '2px 6px', borderRadius: 4,
        flexShrink: 0,
      }}>
        {(alert.severity || 'INFO').toUpperCase()}
      </span>
    </div>
  );
}

// ─── Action button ────────────────────────────────────────────────────────────
function ActionBtn({ label, desc, icon: Icon, action, agentId, orgId, wmiTargetId, onResult }) {
  const [state, setState] = useState('idle'); // idle | busy | ok | err

  const run = async () => {
    if (state === 'busy') return;
    setState('busy');
    try {
      if (wmiTargetId) {
        await wmiApi.remediate(orgId, wmiTargetId, action);
      } else {
        await agentsApi.sendCommand(orgId, agentId, action);
      }
      setState('ok');
      onResult?.(`${label} completed`);
    } catch (e) {
      setState('err');
      onResult?.(`${label} failed: ${e?.response?.data?.detail || e.message}`, true);
    } finally {
      setTimeout(() => setState('idle'), 3000);
    }
  };

  const colors = { idle: T.border, busy: T.amber, ok: T.teal, err: T.red };
  const textColors = { idle: T.sub, busy: T.amber, ok: T.teal, err: T.red };

  return (
    <button
      onClick={run}
      disabled={state === 'busy'}
      style={{
        background: T.panel2,
        border: `1px solid ${colors[state]}`,
        borderRadius: 9,
        padding: '12px 14px',
        cursor: state === 'busy' ? 'not-allowed' : 'pointer',
        display: 'flex', alignItems: 'flex-start', gap: 10,
        transition: 'border-color 0.2s, background 0.2s',
        textAlign: 'left', width: '100%',
      }}
      onMouseEnter={e => { if (state === 'idle') e.currentTarget.style.borderColor = T.amber + '50'; }}
      onMouseLeave={e => { if (state === 'idle') e.currentTarget.style.borderColor = T.border; }}
    >
      <div style={{
        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
        background: `${textColors[state]}14`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'background 0.2s',
      }}>
        {state === 'busy'
          ? <RefreshCw size={13} color={T.amber} style={{ animation: 'probe-spin 1s linear infinite' }} />
          : state === 'ok'
          ? <CheckCircle2 size={13} color={T.teal} />
          : state === 'err'
          ? <AlertTriangle size={13} color={T.red} />
          : <Icon size={13} color={T.sub} />}
      </div>
      <div>
        <div style={{ fontFamily: T.mono, fontSize: '10px', letterSpacing: '0.07em', color: textColors[state] }}>
          {state === 'ok' ? 'DONE' : state === 'err' ? 'FAILED' : state === 'busy' ? 'RUNNING…' : label}
        </div>
        <div style={{ fontFamily: T.ui, fontSize: '11px', color: T.muted, marginTop: 2 }}>{desc}</div>
      </div>
    </button>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function AgentDashboard({ agent, orgId, wmiTargetId, onClose }) {
  const [history,    setHistory]    = useState([]);
  const [alerts,     setAlerts]     = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [lastAt,     setLastAt]     = useState(null);
  const [toast,      setToast]      = useState(null);
  const pollRef = useRef(null);

  const m   = agent.metrics || {};
  const pi  = agent.platform_info || {};
  const status = deriveStatus(agent.last_seen);
  const statusColor = status === 'online' ? T.teal : status === 'warning' ? T.amber : T.muted;

  const showToast = (msg, isErr = false) => {
    setToast({ msg, isErr });
    setTimeout(() => setToast(null), 4000);
  };

  // ── Data fetch ──
  const fetchData = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const [rawHistory, rawAlerts] = await Promise.allSettled([
        metricsApi.getHistory(orgId, { agentId: agent.id, limit: 60 }),
        alertsApi.list(orgId),
      ]);

      const hist = rawHistory.value || [];
      // sort oldest → newest
      hist.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
      setHistory(hist);

      const allAlerts = rawAlerts.value || [];
      setAlerts(Array.isArray(allAlerts)
        ? allAlerts.filter(a => !a.agent_id || a.agent_id === agent.id)
        : []);

      setLastAt(new Date());
    } catch (e) {
      console.error('[AgentDashboard] fetch error', e);
    } finally {
      setRefreshing(false);
    }
  }, [orgId, agent.id]);

  useEffect(() => {
    fetchData();
    pollRef.current = setInterval(() => fetchData(), 10000);
    return () => clearInterval(pollRef.current);
  }, [fetchData]);

  // ── ESC to close ──
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // ── Chart data ──
  const chartData = history.slice(-40).map(h => ({
    t:    fmtTime(h.timestamp),
    CPU:  h.cpu  ?? null,
    MEM:  h.memory ?? null,
    DISK: h.disk ?? null,
  })).filter(d => d.CPU != null || d.MEM != null || d.DISK != null);

  // ── Sparkline history ──
  const sparkCpu  = history.map(h => h.cpu).filter(v => v != null);
  const sparkMem  = history.map(h => h.memory).filter(v => v != null);
  const sparkDisk = history.map(h => h.disk).filter(v => v != null);
  const sparkNet  = history.map(h => (h.network_in || 0) / 1024 / 1024).filter(v => v != null);

  // ── Current values (live from latest agent metric) ──
  const cpu  = m.cpu  ?? m.cpu_percent  ?? null;
  const mem  = m.memory ?? m.memory_percent ?? null;
  const disk = m.disk ?? m.disk_percent ?? null;
  const netIn  = m.network_in  ?? null;
  const netOut = m.network_out ?? null;
  const temp = m.temperature ?? null;
  const uptime = m.uptime_secs ?? null;
  const procs = m.processes ?? null;
  const load  = m.load_avg ?? null;

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Keyframe animations */}
      <style>{`
        @keyframes probe-slide {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes probe-spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes probe-pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.35; }
        }
        @keyframes probe-toast {
          0%   { opacity: 0; transform: translateY(12px); }
          15%  { opacity: 1; transform: translateY(0); }
          85%  { opacity: 1; transform: translateY(0); }
          100% { opacity: 0; transform: translateY(12px); }
        }
        .probe-scroll::-webkit-scrollbar { width: 4px; }
        .probe-scroll::-webkit-scrollbar-track { background: transparent; }
        .probe-scroll::-webkit-scrollbar-thumb { background: ${T.dim}; border-radius: 2px; }
      `}</style>

      {/* Full-screen overlay */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 900,
        background: T.bg,
        overflowY: 'auto',
        animation: 'probe-slide 0.3s ease both',
      }} className="probe-scroll">

        {/* Noise + scanline texture */}
        <div style={{
          position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
          backgroundImage: `
            repeating-linear-gradient(
              0deg,
              rgba(0,0,0,0) 0px,
              rgba(0,0,0,0) 3px,
              rgba(0,0,0,0.04) 3px,
              rgba(0,0,0,0.04) 4px
            )
          `,
        }} />

        {/* Amber top-edge accent */}
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, height: 2, zIndex: 10,
          background: `linear-gradient(90deg, transparent, ${T.amber}, ${T.teal}, transparent)`,
        }} />

        <div style={{ position: 'relative', zIndex: 1, padding: '24px 28px', maxWidth: 1400, margin: '0 auto' }}>

          {/* ── HEADER ─────────────────────────────────────────────────────── */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 16,
            marginBottom: 24, flexWrap: 'wrap',
            animation: 'probe-slide 0.25s ease both',
          }}>
            {/* Back */}
            <button
              onClick={onClose}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: 'none', border: `1px solid ${T.border}`,
                borderRadius: 7, padding: '7px 12px', cursor: 'pointer',
                fontFamily: T.mono, fontSize: '10px', letterSpacing: '0.08em',
                color: T.sub, transition: 'all 0.15s', flexShrink: 0,
              }}
              onMouseEnter={e => { e.currentTarget.style.color = T.amber; e.currentTarget.style.borderColor = T.amber + '50'; }}
              onMouseLeave={e => { e.currentTarget.style.color = T.sub; e.currentTarget.style.borderColor = T.border; }}
            >
              <ArrowLeft size={12} /> BACK
            </button>

            {/* Status pulse */}
            <div style={{ position: 'relative', width: 10, height: 10, flexShrink: 0 }}>
              {status === 'online' && (
                <span style={{
                  position: 'absolute', inset: -4, borderRadius: '50%',
                  background: T.teal, opacity: 0.2,
                  animation: 'probe-pulse 2s ease infinite',
                }} />
              )}
              <span style={{
                position: 'absolute', inset: 0, borderRadius: '50%',
                background: statusColor,
              }} />
            </div>

            {/* Agent name */}
            <h1 style={{
              fontFamily: T.disp, fontSize: '2.2rem', letterSpacing: '0.06em',
              lineHeight: 1, color: T.text, margin: 0,
            }}>
              {agent.label || agent.id}
            </h1>

            {/* Info chips */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginLeft: 4 }}>
              {pi.hostname && (
                <Chip icon={Server} label={pi.hostname} />
              )}
              {pi.os && (
                <Chip icon={Shield} label={pi.os} />
              )}
              {pi.cpu_cores && (
                <Chip icon={Cpu} label={`${pi.cpu_cores} cores`} />
              )}
              {uptime != null && (
                <Chip icon={Clock} label={fmtUptime(uptime)} color={T.teal} />
              )}
              {(pi.source === 'wmi' || wmiTargetId) && (
                <Chip icon={Wifi} label="WMI / AGENTLESS" color={T.blue} />
              )}
            </div>

            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
              {lastAt && (
                <span style={{ fontFamily: T.mono, fontSize: '9px', color: T.muted }}>
                  {lastAt.toLocaleTimeString()}
                </span>
              )}
              <button
                onClick={() => fetchData(true)}
                disabled={refreshing}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  background: 'none', border: `1px solid ${T.border}`,
                  borderRadius: 7, padding: '7px 12px', cursor: refreshing ? 'not-allowed' : 'pointer',
                  fontFamily: T.mono, fontSize: '10px', color: T.sub, opacity: refreshing ? 0.5 : 1,
                }}
              >
                <RefreshCw size={11} style={{ animation: refreshing ? 'probe-spin 1s linear infinite' : 'none' }} />
                REFRESH
              </button>
            </div>
          </div>

          {/* ── METRIC CARDS ───────────────────────────────────────────────── */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 12,
            marginBottom: 20,
          }}>
            <MetricCard
              icon={Cpu} label="CPU USAGE"
              value={cpu} unit="%"
              sparkValues={sparkCpu}
              delay={0}
              extra={load ? `LOAD AVG ${load}` : undefined}
            />
            <MetricCard
              icon={MemoryStick} label="MEMORY"
              value={mem} unit="%"
              sparkValues={sparkMem}
              delay={0.05}
              extra={procs ? `${procs} PROCESSES` : undefined}
            />
            <MetricCard
              icon={HardDrive} label="DISK USAGE"
              value={disk} unit="%"
              sparkValues={sparkDisk}
              delay={0.1}
            />
            <MetricCard
              icon={Wifi} label="NET IN (MB/s)"
              value={netIn != null ? netIn / 1024 / 1024 : null}
              unit=" MB/s"
              sparkValues={sparkNet}
              delay={0.15}
              extra={netOut != null ? `OUT ${fmtBytes(netOut)}` : undefined}
            />
          </div>

          {/* ── MAIN GRID ──────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, marginBottom: 14 }}>

            {/* ── VITAL SIGNS CHART ── */}
            <div style={{
              background: T.panel,
              border: `1px solid ${T.border}`,
              borderRadius: 12, overflow: 'hidden',
              animation: 'probe-slide 0.5s ease both',
            }}>
              <div style={{
                padding: '14px 20px', borderBottom: `1px solid ${T.border}`,
                display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <Activity size={13} color={T.amber} />
                <span style={{ fontFamily: T.mono, fontSize: '10px', letterSpacing: '0.12em', color: T.sub }}>
                  VITAL SIGNS — LAST {Math.min(chartData.length, 40)} READINGS
                </span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 12 }}>
                  {[['CPU', T.amber], ['MEM', T.teal], ['DISK', T.blue]].map(([n, c]) => (
                    <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 20, height: 2, background: c, display: 'inline-block', borderRadius: 1 }} />
                      <span style={{ fontFamily: T.mono, fontSize: '8px', color: T.muted, letterSpacing: '0.08em' }}>{n}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ padding: '16px 8px 12px 0', height: 260 }}>
                {chartData.length < 2 ? (
                  <div style={{
                    height: '100%', display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center', gap: 10,
                  }}>
                    <Activity size={28} color={T.dim} />
                    <span style={{ fontFamily: T.mono, fontSize: '10px', color: T.muted, letterSpacing: '0.1em' }}>
                      COLLECTING DATA…
                    </span>
                    <span style={{ fontFamily: T.ui, fontSize: '11px', color: T.muted, opacity: 0.6 }}>
                      History appears after a few heartbeat cycles
                    </span>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 4, right: 16, left: -20, bottom: 0 }}>
                      <defs>
                        {[['cpu-g', T.amber], ['mem-g', T.teal], ['disk-g', T.blue]].map(([id, c]) => (
                          <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={c} stopOpacity={0.18} />
                            <stop offset="95%" stopColor={c} stopOpacity={0} />
                          </linearGradient>
                        ))}
                      </defs>
                      <CartesianGrid stroke={T.dim} strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="t" tick={{ fontFamily: T.mono, fontSize: 8, fill: T.muted }}
                        tickLine={false} axisLine={{ stroke: T.border }}
                        interval={Math.floor(chartData.length / 6)} />
                      <YAxis domain={[0, 100]} tick={{ fontFamily: T.mono, fontSize: 8, fill: T.muted }}
                        tickLine={false} axisLine={false}
                        tickFormatter={v => `${v}%`} />
                      <Tooltip content={<ChartTooltip />} />
                      <Area type="monotone" dataKey="CPU" stroke={T.amber} strokeWidth={1.5}
                        fill="url(#cpu-g)" dot={false} activeDot={{ r: 3, fill: T.amber }} />
                      <Area type="monotone" dataKey="MEM" stroke={T.teal} strokeWidth={1.5}
                        fill="url(#mem-g)" dot={false} activeDot={{ r: 3, fill: T.teal }} />
                      <Area type="monotone" dataKey="DISK" stroke={T.blue} strokeWidth={1.5}
                        fill="url(#disk-g)" dot={false} activeDot={{ r: 3, fill: T.blue }} />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {/* ── SYSTEM INFO ── */}
            <div style={{
              background: T.panel,
              border: `1px solid ${T.border}`,
              borderRadius: 12, overflow: 'hidden',
              display: 'flex', flexDirection: 'column',
              animation: 'probe-slide 0.55s ease both',
            }}>
              <div style={{
                padding: '14px 18px', borderBottom: `1px solid ${T.border}`,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <Info size={13} color={T.amber} />
                <span style={{ fontFamily: T.mono, fontSize: '10px', letterSpacing: '0.12em', color: T.sub }}>
                  SYSTEM INFO
                </span>
              </div>
              <div style={{ padding: '14px 18px', flex: 1, display: 'flex', flexDirection: 'column', gap: 0 }}>
                {[
                  ['HOSTNAME',    pi.hostname  || agent.label],
                  ['OS',          pi.os        || pi.platform],
                  ['PLATFORM',    pi.platform],
                  ['CPU MODEL',   pi.cpu_model],
                  ['CPU CORES',   pi.cpu_cores],
                  ['PYTHON',      pi.python],
                  ['PROCESSES',   procs],
                  ['TEMPERATURE', temp != null ? `${temp}°C` : null],
                  ['LOAD AVG',    load],
                  ['UPTIME',      uptime != null ? fmtUptime(uptime) : null],
                  ['NET IN',      fmtBytes(netIn)],
                  ['NET OUT',     fmtBytes(netOut)],
                  ['LAST SEEN',   relTime(agent.last_seen)],
                  ['AGENT ID',    agent.id?.slice(0, 18) + '…'],
                  ['CREATED',     agent.created_at ? new Date(agent.created_at).toLocaleDateString() : null],
                ].filter(([, v]) => v != null && v !== undefined).map(([k, v]) => (
                  <div key={k} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                    padding: '7px 0', borderBottom: `1px solid ${T.dim}`,
                    gap: 8,
                  }}>
                    <span style={{ fontFamily: T.mono, fontSize: '9px', letterSpacing: '0.08em', color: T.muted, flexShrink: 0 }}>
                      {k}
                    </span>
                    <span style={{
                      fontFamily: T.mono, fontSize: '10px', color: T.sub,
                      textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      maxWidth: 160,
                    }}>
                      {String(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── BOTTOM ROW ─────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14 }}>

            {/* ── ALERTS ── */}
            <div style={{
              background: T.panel,
              border: `1px solid ${T.border}`,
              borderRadius: 12, overflow: 'hidden',
              animation: 'probe-slide 0.6s ease both',
            }}>
              <div style={{
                padding: '14px 18px', borderBottom: `1px solid ${T.border}`,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <AlertTriangle size={13} color={alerts.length > 0 ? T.red : T.muted} />
                <span style={{ fontFamily: T.mono, fontSize: '10px', letterSpacing: '0.12em', color: T.sub }}>
                  ALERTS
                </span>
                {alerts.length > 0 && (
                  <span style={{
                    marginLeft: 6, fontFamily: T.mono, fontSize: '8px',
                    color: T.red, background: `${T.red}18`,
                    border: `1px solid ${T.red}28`, padding: '1px 6px', borderRadius: 4,
                  }}>
                    {alerts.length} OPEN
                  </span>
                )}
              </div>
              <div style={{ maxHeight: 200, overflowY: 'auto' }} className="probe-scroll">
                {alerts.length === 0 ? (
                  <div style={{
                    padding: '28px', textAlign: 'center',
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
                  }}>
                    <CheckCircle2 size={22} color={T.teal} />
                    <span style={{ fontFamily: T.mono, fontSize: '10px', letterSpacing: '0.1em', color: T.muted }}>
                      ALL CLEAR
                    </span>
                  </div>
                ) : (
                  alerts.map((a, i) => <AlertRow key={a.id || i} alert={a} />)
                )}
              </div>
            </div>

            {/* ── REMEDIATION ACTIONS ── */}
            <div style={{
              background: T.panel,
              border: `1px solid ${T.border}`,
              borderRadius: 12, overflow: 'hidden',
              animation: 'probe-slide 0.65s ease both',
            }}>
              <div style={{
                padding: '14px 18px', borderBottom: `1px solid ${T.border}`,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <Terminal size={13} color={T.amber} />
                <span style={{ fontFamily: T.mono, fontSize: '10px', letterSpacing: '0.12em', color: T.sub }}>
                  REMEDIATION
                </span>
              </div>
              {wmiTargetId && (
                <div style={{
                  margin: '8px 12px 0', padding: '8px 12px',
                  background: `${T.blue}0a`, border: `1px solid ${T.blue}20`,
                  borderRadius: 7, fontFamily: T.mono, fontSize: '9px',
                  color: T.blue, letterSpacing: '0.06em', lineHeight: 1.5,
                }}>
                  WMI AGENT — commands execute via WinRM directly
                </div>
              )}
              <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  { label: 'FREE MEMORY',  desc: 'Trigger garbage collection / empty working sets', icon: Zap,      action: 'free_memory'  },
                  { label: 'CLEAR CACHE',  desc: 'Flush DNS + clear temp files',                   icon: RefreshCw, action: 'clear_cache' },
                  { label: 'DISK CLEANUP', desc: 'Remove temp / Windows temp files',               icon: HardDrive, action: 'disk_cleanup' },
                  { label: 'RUN GC',       desc: 'Force .NET/Python garbage collection',            icon: Activity,  action: 'run_gc'       },
                ].map(a => (
                  <ActionBtn
                    key={a.action}
                    {...a}
                    agentId={agent.id}
                    orgId={orgId}
                    wmiTargetId={wmiTargetId}
                    onResult={showToast}
                  />
                ))}
              </div>
            </div>

          </div>

          {/* Bottom padding */}
          <div style={{ height: 40 }} />
        </div>
      </div>

      {/* ── Toast ── */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
          zIndex: 1100,
          background: toast.isErr ? `${T.red}20` : `${T.teal}18`,
          border: `1px solid ${toast.isErr ? T.red + '40' : T.teal + '40'}`,
          borderRadius: 9, padding: '10px 18px',
          fontFamily: T.mono, fontSize: '11px', letterSpacing: '0.06em',
          color: toast.isErr ? T.red : T.teal,
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          animation: 'probe-toast 4s ease forwards',
          whiteSpace: 'nowrap',
        }}>
          {toast.isErr ? '✗' : '✓'} {toast.msg}
        </div>
      )}
    </>
  );
}

// ─── Chip helper ──────────────────────────────────────────────────────────────
function Chip({ icon: Icon, label, color = T.muted }) {
  if (!label) return null;
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontFamily: T.mono, fontSize: '9px', letterSpacing: '0.07em',
      color: color, background: `${color}12`,
      border: `1px solid ${color}25`, padding: '3px 9px', borderRadius: 5,
    }}>
      <Icon size={9} />
      {String(label)}
    </div>
  );
}
