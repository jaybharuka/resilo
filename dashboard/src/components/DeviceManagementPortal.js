import React, { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { apiService, agentApi } from '../services/api';
import { motion, AnimatePresence } from 'framer-motion';
import InfoTip from './InfoTip';
import { AgentDetail, NewAgentModal } from './RemoteAgents';
import {
  Monitor, Server, Laptop, Cpu, HardDrive, MemoryStick,
  ShieldCheck, ShieldAlert, RefreshCw, ChevronRight,
  CheckCircle, XCircle, BarChart2, X, Plus, Radio,
} from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

// ─── theme tokens ────────────────────────────────────────────────────────────
const C = {
  bg:        'rgb(22, 20, 16)',
  surface:   'rgb(28, 26, 21)',
  surface2:  'rgb(31, 29, 24)',
  border:    'rgba(245,158,11,0.12)',
  borderDim: 'rgba(245,240,232,0.06)',
  amber:     '#F59E0B',
  amberDim:  'rgba(245,158,11,0.15)',
  text:      '#F5F0E8',
  muted:     '#6B6357',
  dim:       '#4A443D',
  green:     '#34D399',
  greenDim:  'rgba(52,211,153,0.12)',
  teal:      '#2DD4BF',
  tealDim:   'rgba(45,212,191,0.12)',
  red:       '#F87171',
  redDim:    'rgba(248,113,113,0.12)',
  yellow:    '#FCD34D',
  yellowDim: 'rgba(252,211,77,0.12)',
  grey:      '#52524E',
  greyDim:   'rgba(82,82,78,0.2)',
};

// ─── helpers ─────────────────────────────────────────────────────────────────
const normaliseType = (t = '') => t.toLowerCase();

const statusMeta = (s) => {
  switch ((s || '').toLowerCase()) {
    case 'online':   return { color: C.green,  dim: C.greenDim,  label: 'ONLINE'   };
    case 'live':     return { color: C.teal,   dim: C.tealDim,   label: 'LIVE'     };
    case 'warning':  return { color: C.yellow, dim: C.yellowDim, label: 'WARNING'  };
    case 'critical': return { color: C.red,    dim: C.redDim,    label: 'CRITICAL' };
    case 'offline':  return { color: C.grey,   dim: C.greyDim,   label: 'OFFLINE'  };
    case 'pending':  return { color: C.amber,  dim: C.amberDim,  label: 'PENDING'  };
    default:         return { color: C.green,  dim: C.greenDim,  label: 'ONLINE'   };
  }
};

const fmtTime = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = Math.floor((now - d) / 1000);
    if (diff < 60)   return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return '—'; }
};

const DeviceIcon = ({ type, size = 16 }) => {
  const t = normaliseType(type);
  const props = { size, color: C.muted };
  if (t === 'laptop')  return <Laptop {...props} />;
  if (t === 'server')  return <Server {...props} />;
  return <Monitor {...props} />;
};

// ─── Normalise data from both sources ────────────────────────────────────────
const normalizeDevice = (d) => ({
  id:         `managed-${d.id}`,
  name:       d.name,
  type:       d.type || 'workstation',
  os:         d.os,
  department: d.department,
  // treat 'online' as the alive state for managed devices
  status:     (d.status || 'online').toLowerCase(),
  cpu:        d.cpu,
  memory:     d.memory,
  disk:       d.disk,
  battery:    d.battery,
  security:   d.security,
  lastSeen:   d.lastSeen,
  source:     'managed',
  _deviceRaw: d,
  _agentRaw:  null,
});

const normalizeAgent = (a) => {
  // live → online mapping so filters are consistent
  const rawStatus = (a.status || 'pending').toLowerCase();
  const status = rawStatus === 'live' ? 'live' : rawStatus; // keep 'live' distinct for pulse dot
  return {
    id:         `remote-${a.id}`,
    name:       a.label || a.hostname || 'Unknown',
    type:       'workstation',
    os:         a.os || a.info?.os || null,
    department: null,
    status,
    cpu:        a.cpu    ?? a.metrics?.cpu    ?? null,
    memory:     a.memory ?? a.metrics?.memory ?? null,
    disk:       a.disk   ?? a.metrics?.disk   ?? null,
    battery:    null,
    security:   null,
    lastSeen:   a.last_seen ? new Date(a.last_seen * 1000).toISOString() : null,
    source:     'remote',
    _deviceRaw: null,
    _agentRaw:  a,
  };
};

// ─── sub-components ──────────────────────────────────────────────────────────
const StatCard = ({ label, value, color, dim, info }) => (
  <div style={{
    background: dim, border: `1px solid ${color}30`,
    borderRadius: 10, padding: '16px 20px', flex: 1, minWidth: 0, position: 'relative',
  }}>
    {info && (
      <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10 }}>
        <InfoTip info={info} />
      </div>
    )}
    <div style={{ ...MONO, fontSize: 28, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
    <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.muted, marginTop: 6 }}>{label}</div>
  </div>
);

const Bar = ({ value = 0, color }) => {
  const pct = Math.min(100, Math.max(0, value));
  const c = color || (pct > 85 ? C.red : pct > 70 ? C.yellow : C.green);
  return (
    <div style={{ position: 'relative', height: 4, borderRadius: 2, background: C.borderDim, overflow: 'hidden' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${pct}%`, background: c, borderRadius: 2 }} />
    </div>
  );
};

const SecurityBadge = ({ ok, label }) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '2px 8px', borderRadius: 4,
    background: ok ? C.greenDim : C.redDim,
    border: `1px solid ${ok ? C.green : C.red}30`,
    ...MONO, fontSize: 10, letterSpacing: '0.08em',
    color: ok ? C.green : C.red,
  }}>
    {ok ? <CheckCircle size={10} /> : <XCircle size={10} />}
    {label}
  </span>
);

// ─── SourceBadge ─────────────────────────────────────────────────────────────
const SourceBadge = ({ source }) => {
  const isRemote = source === 'remote';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 7px', borderRadius: 4,
      background: isRemote ? C.tealDim : C.amberDim,
      border: `1px solid ${isRemote ? C.teal : C.amber}25`,
      ...MONO, fontSize: 9, letterSpacing: '0.08em',
      color: isRemote ? C.teal : C.amber,
    }}>
      {isRemote ? <Radio size={9} /> : <Monitor size={9} />}
      {isRemote ? 'REMOTE' : 'MANAGED'}
    </span>
  );
};

// ─── device detail modal (for managed devices) ────────────────────────────────
const DeviceDetail = ({ device, onClose }) => {
  if (!device) return null;
  const sm  = statusMeta(device.status);
  const sec = device.security || {};
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50,
      background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 12 }}
        transition={{ duration: 0.18 }}
        onClick={e => e.stopPropagation()}
        style={{
          background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 14, width: '100%', maxWidth: 560, overflow: 'hidden',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 22px', borderBottom: `1px solid ${C.borderDim}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <DeviceIcon type={device.type} size={18} />
            <span style={{ ...UI, fontSize: 15, fontWeight: 600, color: C.text }}>{device.name}</span>
            <span style={{
              ...MONO, fontSize: 10, letterSpacing: '0.1em',
              color: sm.color, background: sm.dim, padding: '2px 8px', borderRadius: 4,
            }}>{sm.label}</span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.muted, padding: 4 }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ padding: '22px' }}>
          <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.muted, marginBottom: 12 }}>PERFORMANCE</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 22 }}>
            {[
              { label: 'CPU',    value: device.cpu,    icon: <Cpu size={12} color={C.muted} /> },
              { label: 'MEMORY', value: device.memory, icon: <MemoryStick size={12} color={C.muted} /> },
              { label: 'DISK',   value: device.disk,   icon: <HardDrive size={12} color={C.muted} /> },
            ].map(({ label, value, icon }) => value != null && (
              <div key={label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, ...MONO, fontSize: 10, color: C.muted, letterSpacing: '0.1em' }}>
                    {icon}{label}
                  </div>
                  <span style={{ ...MONO, fontSize: 13, color: C.text }}>{value}%</span>
                </div>
                <Bar value={value} />
              </div>
            ))}
          </div>
          <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.muted, marginBottom: 12 }}>DEVICE INFO</div>
          <div style={{ background: C.bg, border: `1px solid ${C.borderDim}`, borderRadius: 8, padding: '12px 16px', marginBottom: 22 }}>
            {[
              ['OS',         device.os],
              ['TYPE',       device.type],
              ['DEPARTMENT', device.department],
              ['LAST SEEN',  fmtTime(device.lastSeen)],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: `1px solid ${C.borderDim}` }}>
                <span style={{ ...MONO, fontSize: 10, color: C.muted, letterSpacing: '0.1em' }}>{k}</span>
                <span style={{ ...MONO, fontSize: 11, color: C.text }}>{v || '—'}</span>
              </div>
            ))}
          </div>
          <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.muted, marginBottom: 12 }}>SECURITY</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <SecurityBadge ok={!!sec.antivirus}  label="Antivirus"  />
            <SecurityBadge ok={!!sec.firewall}   label="Firewall"   />
            <SecurityBadge ok={!!sec.encryption} label="Encryption" />
          </div>
        </div>
      </motion.div>
    </div>
  );
};

// ─── analytics tab ───────────────────────────────────────────────────────────
const AnalyticsTab = ({ entries }) => {
  const total = entries.length;
  if (total === 0) return (
    <div style={{ textAlign: 'center', padding: 60, ...MONO, fontSize: 12, color: C.muted }}>
      NO DEVICES TO ANALYSE
    </div>
  );

  const deptMap   = {};
  const typeMap   = {};
  const statusMap = {};
  const sourceMap = { managed: 0, remote: 0 };

  entries.forEach(d => {
    if (d.department) deptMap[d.department] = (deptMap[d.department] || 0) + 1;
    const t = normaliseType(d.type); typeMap[t] = (typeMap[t] || 0) + 1;
    const s = (d.status || 'online').toLowerCase(); statusMap[s] = (statusMap[s] || 0) + 1;
    sourceMap[d.source] = (sourceMap[d.source] || 0) + 1;
  });

  const sec = {
    antivirus:  entries.filter(d => d.security?.antivirus).length,
    firewall:   entries.filter(d => d.security?.firewall).length,
    encryption: entries.filter(d => d.security?.encryption).length,
  };

  const Section = ({ title }) => (
    <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.14em', color: C.muted, marginBottom: 14 }}>{title}</div>
  );

  const BreakdownRow = ({ label, count, color }) => {
    const pct = Math.round((count / total) * 100);
    return (
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
          <span style={{ ...UI, fontSize: 13, color: C.text }}>{label}</span>
          <span style={{ ...MONO, fontSize: 11, color: C.muted }}>{count} · {pct}%</span>
        </div>
        <Bar value={pct} color={color || C.amber} />
      </div>
    );
  };

  const SecCounter = ({ label, value, ok }) => (
    <div style={{
      flex: 1, minWidth: 0, textAlign: 'center',
      background: ok ? C.greenDim : C.redDim,
      border: `1px solid ${ok ? C.green : C.red}20`,
      borderRadius: 10, padding: '14px 8px',
    }}>
      <div style={{ ...MONO, fontSize: 26, fontWeight: 700, color: ok ? C.green : C.red, lineHeight: 1 }}>{value}</div>
      <div style={{ ...MONO, fontSize: 9, letterSpacing: '0.12em', color: C.muted, marginTop: 6 }}>{label}</div>
    </div>
  );

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      {Object.keys(deptMap).length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '20px 22px' }}>
          <Section title="BY DEPARTMENT" />
          {Object.entries(deptMap).sort((a, b) => b[1] - a[1]).map(([dept, count]) => (
            <BreakdownRow key={dept} label={dept} count={count} />
          ))}
        </div>
      )}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '20px 22px' }}>
        <Section title="BY TYPE" />
        {Object.entries(typeMap).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
          <BreakdownRow key={type} label={type.charAt(0).toUpperCase() + type.slice(1)} count={count} />
        ))}
      </div>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '20px 22px' }}>
        <Section title="BY STATUS" />
        {Object.entries(statusMap).sort((a, b) => b[1] - a[1]).map(([s, count]) => {
          const sm = statusMeta(s);
          return <BreakdownRow key={s} label={sm.label} count={count} color={sm.color} />;
        })}
      </div>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '20px 22px' }}>
        <Section title="BY SOURCE" />
        <BreakdownRow label="Managed Devices" count={sourceMap.managed} color={C.amber} />
        <BreakdownRow label="Remote Agents"   count={sourceMap.remote}  color={C.teal}  />
      </div>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '20px 22px', gridColumn: 'span 2' }}>
        <Section title="SECURITY COVERAGE (MANAGED DEVICES)" />
        <div style={{ display: 'flex', gap: 10 }}>
          <SecCounter label="ANTIVIRUS"  value={sec.antivirus}  ok={sec.antivirus  === sourceMap.managed} />
          <SecCounter label="FIREWALL"   value={sec.firewall}   ok={sec.firewall   === sourceMap.managed} />
          <SecCounter label="ENCRYPTION" value={sec.encryption} ok={sec.encryption === sourceMap.managed} />
        </div>
      </div>
    </div>
  );
};

// ─── main component ───────────────────────────────────────────────────────────
export default function DeviceManagementPortal() {
  const location = useLocation();
  const [devices, setDevices]           = useState([]);
  const [agents, setAgents]             = useState([]);
  const [loading, setLoading]           = useState(true);
  const [lastRefresh, setLastRefresh]   = useState(null);
  const [tab, setTab]                   = useState(0);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterSource, setFilterSource] = useState('all');
  const [filterDept, setFilterDept]     = useState('all');
  const [selectedDevice, setSelectedDevice] = useState(null);   // managed → modal
  const [selectedAgentId, setSelectedAgentId] = useState(null); // remote → full page
  const [showNewAgent, setShowNewAgent] = useState(false);
  const [prefilledLabel, setPrefilledLabel] = useState('');

  // Auto-open New Agent modal when navigated from User Management (/devices?label=Jay)
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const label = params.get('label');
    if (label) {
      setPrefilledLabel(decodeURIComponent(label));
      setShowNewAgent(true);
      // Clean the URL so refreshing doesn't re-open the modal
      window.history.replaceState({}, '', '/devices');
    }
  }, [location.search]);

  const fetchAll = useCallback(async () => {
    try {
      const [devList, agentList] = await Promise.allSettled([
        apiService.getDevices(),
        agentApi.list(),
      ]);
      if (devList.status === 'fulfilled' && Array.isArray(devList.value)) {
        setDevices(devList.value);
      }
      if (agentList.status === 'fulfilled' && Array.isArray(agentList.value)) {
        setAgents(agentList.value);
      }
      setLastRefresh(new Date());
    } catch (e) {
      console.warn('fleet fetch failed', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 15_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  // ── if an agent is selected, render its detail page full-screen ───────────
  if (selectedAgentId !== null) {
    return (
      <div style={{ padding: '24px 32px', minHeight: '100vh', background: C.bg }}>
        <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}} @keyframes spin{to{transform:rotate(360deg)}}`}</style>
        <AgentDetail agentId={selectedAgentId} onBack={() => setSelectedAgentId(null)} />
      </div>
    );
  }

  // ── normalise & merge ─────────────────────────────────────────────────────
  const allEntries = [
    ...devices.map(normalizeDevice),
    ...agents.map(normalizeAgent),
  ];

  // ── stats ─────────────────────────────────────────────────────────────────
  const stats = {
    total:    allEntries.length,
    online:   allEntries.filter(d => d.status === 'online' || d.status === 'live').length,
    warning:  allEntries.filter(d => d.status === 'warning').length,
    critical: allEntries.filter(d => d.status === 'critical').length,
    offline:  allEntries.filter(d => d.status === 'offline').length,
    pending:  allEntries.filter(d => d.status === 'pending').length,
  };

  // ── derived filters ───────────────────────────────────────────────────────
  const departments = [...new Set(devices.map(d => d.department).filter(Boolean))].sort();

  const filtered = allEntries.filter(d => {
    const statusOk = filterStatus === 'all' ||
      (filterStatus === 'online' ? (d.status === 'online' || d.status === 'live') : d.status === filterStatus);
    const sourceOk = filterSource === 'all' || d.source === filterSource;
    const deptOk   = filterDept   === 'all' || d.department === filterDept;
    return statusOk && sourceOk && deptOk;
  });

  const TABS = [
    { label: 'FLEET',     icon: <Monitor size={13} /> },
    { label: 'ANALYTICS', icon: <BarChart2 size={13} /> },
  ];

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: C.bg }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}} @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>

      {/* ── page header ── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <Monitor size={18} color={C.amber} />
            <h1 style={{ ...UI, fontSize: 20, fontWeight: 700, color: C.text, margin: 0 }}>Device Fleet</h1>
          </div>
          <p style={{ ...MONO, fontSize: 10, letterSpacing: '0.14em', color: C.muted, margin: 0 }}>
            MANAGED DEVICES + REMOTE AGENTS · {lastRefresh ? `UPDATED ${fmtTime(lastRefresh.toISOString())}` : 'LOADING…'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={fetchAll}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', gap: 7,
              background: 'transparent', border: `1px solid ${C.borderDim}`,
              borderRadius: 8, padding: '8px 14px', cursor: 'pointer',
              ...MONO, fontSize: 11, letterSpacing: '0.1em', color: C.muted,
              opacity: loading ? 0.5 : 1,
            }}
          >
            <RefreshCw size={13} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            REFRESH
          </button>
          <button
            onClick={() => setShowNewAgent(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 7,
              background: C.amberDim, border: `1px solid ${C.amber}30`,
              borderRadius: 8, padding: '8px 14px', cursor: 'pointer',
              ...MONO, fontSize: 11, letterSpacing: '0.1em', color: C.amber,
            }}
          >
            <Plus size={13} /> NEW AGENT
          </button>
        </div>
      </div>

      {/* ── stat cards ── */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 28, flexWrap: 'wrap' }}>
        <StatCard label="TOTAL"    value={loading ? '—' : stats.total}    color={C.amber}  dim={C.amberDim}
          info="All managed devices and remote agents registered in the fleet." />
        <StatCard label="ONLINE"   value={loading ? '—' : stats.online}   color={C.green}  dim={C.greenDim}
          info="Managed devices reporting healthy status, plus remote agents with a live heartbeat." />
        <StatCard label="WARNING"  value={loading ? '—' : stats.warning}  color={C.yellow} dim={C.yellowDim}
          info="Devices with elevated but non-critical metrics — CPU, memory, or disk above warn threshold." />
        <StatCard label="CRITICAL" value={loading ? '—' : stats.critical} color={C.red}    dim={C.redDim}
          info="Devices exceeding critical thresholds or experiencing active errors. Requires immediate attention." />
        <StatCard label="OFFLINE"  value={loading ? '—' : stats.offline}  color={C.grey}   dim={C.greyDim}
          info="Devices that have not sent a heartbeat and are presumed unreachable." />
        {stats.pending > 0 && (
          <StatCard label="PENDING" value={stats.pending} color={C.amber} dim={C.amberDim}
            info="Remote agents that have been provisioned but have not connected yet." />
        )}
      </div>

      {/* ── tabs ── */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 22 }}>
        {TABS.map((t, i) => (
          <button
            key={t.label}
            onClick={() => setTab(i)}
            style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '7px 16px', borderRadius: 7, cursor: 'pointer',
              border: tab === i ? `1px solid ${C.amber}40` : `1px solid transparent`,
              background: tab === i ? C.amberDim : 'transparent',
              ...MONO, fontSize: 10, letterSpacing: '0.12em',
              color: tab === i ? C.amber : C.muted,
              transition: 'all 0.15s',
            }}
          >
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {/* ── tab content ── */}
      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
        >

          {/* ════ tab 0: fleet ════ */}
          {tab === 0 && (
            <>
              {/* filter bar */}
              <div style={{
                background: C.surface, border: `1px solid ${C.borderDim}`,
                borderRadius: 10, padding: '12px 18px', marginBottom: 16,
                display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
              }}>
                <span style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.muted }}>FILTER</span>

                {/* status */}
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {['all', 'online', 'warning', 'critical', 'offline', 'pending'].map(s => {
                    const active = filterStatus === s;
                    const sm = s === 'all' ? { color: C.amber, dim: C.amberDim } : statusMeta(s);
                    return (
                      <button key={s} onClick={() => setFilterStatus(s)} style={{
                        padding: '3px 10px', borderRadius: 5, cursor: 'pointer',
                        border: active ? `1px solid ${sm.color}50` : `1px solid ${C.borderDim}`,
                        background: active ? sm.dim : 'transparent',
                        ...MONO, fontSize: 10, letterSpacing: '0.08em',
                        color: active ? sm.color : C.muted, transition: 'all 0.12s',
                      }}>
                        {s.toUpperCase()}
                      </button>
                    );
                  })}
                </div>

                <div style={{ width: 1, height: 18, background: C.borderDim }} />

                {/* source */}
                <div style={{ display: 'flex', gap: 6 }}>
                  {[
                    { key: 'all',     label: 'ALL SOURCES' },
                    { key: 'managed', label: 'MANAGED'     },
                    { key: 'remote',  label: 'REMOTE'      },
                  ].map(({ key, label }) => {
                    const active = filterSource === key;
                    return (
                      <button key={key} onClick={() => setFilterSource(key)} style={{
                        padding: '3px 10px', borderRadius: 5, cursor: 'pointer',
                        border: active ? `1px solid ${C.amber}40` : `1px solid ${C.borderDim}`,
                        background: active ? C.amberDim : 'transparent',
                        ...MONO, fontSize: 10, letterSpacing: '0.08em',
                        color: active ? C.amber : C.muted, transition: 'all 0.12s',
                      }}>
                        {label}
                      </button>
                    );
                  })}
                </div>

                {departments.length > 1 && (
                  <>
                    <div style={{ width: 1, height: 18, background: C.borderDim }} />
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {['all', ...departments].map(dept => {
                        const active = filterDept === dept;
                        return (
                          <button key={dept} onClick={() => setFilterDept(dept)} style={{
                            padding: '3px 10px', borderRadius: 5, cursor: 'pointer',
                            border: active ? `1px solid ${C.amber}40` : `1px solid ${C.borderDim}`,
                            background: active ? C.amberDim : 'transparent',
                            ...MONO, fontSize: 10, letterSpacing: '0.08em',
                            color: active ? C.amber : C.muted, transition: 'all 0.12s',
                          }}>
                            {dept === 'all' ? 'ALL DEPTS' : dept.toUpperCase()}
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}

                <span style={{ ...MONO, fontSize: 10, color: C.dim, marginLeft: 'auto' }}>
                  {filtered.length} / {allEntries.length}
                </span>
              </div>

              {/* table */}
              {loading ? (
                <div style={{ textAlign: 'center', padding: 60, ...MONO, fontSize: 12, color: C.muted }}>
                  LOADING FLEET…
                </div>
              ) : filtered.length === 0 ? (
                <div style={{
                  textAlign: 'center', padding: 60,
                  background: C.surface, border: `1px solid ${C.borderDim}`,
                  borderRadius: 12, ...MONO, fontSize: 12, color: C.muted,
                }}>
                  NO DEVICES MATCH THE CURRENT FILTERS
                </div>
              ) : (
                <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
                  {/* table head */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '2fr 80px 1fr 1fr 2fr 1fr 40px',
                    padding: '10px 20px',
                    borderBottom: `1px solid ${C.borderDim}`,
                    ...MONO, fontSize: 9, letterSpacing: '0.14em', color: C.dim,
                  }}>
                    <span>DEVICE</span>
                    <span>SOURCE</span>
                    <span>STATUS</span>
                    <span>DEPARTMENT</span>
                    <span>PERFORMANCE</span>
                    <span>SECURITY</span>
                    <span></span>
                  </div>

                  {filtered.map((entry, idx) => {
                    const sm  = statusMeta(entry.status);
                    const sec = entry.security || {};
                    const allSecure = sec.antivirus && sec.firewall && sec.encryption;
                    const isRemote  = entry.source === 'remote';

                    // pulse dot for live/pending remote agents
                    const showPulse = entry.status === 'live' || entry.status === 'pending';

                    return (
                      <motion.div
                        key={entry.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: idx * 0.03 }}
                        onClick={() => {
                          if (isRemote) setSelectedAgentId(entry._agentRaw.id);
                          else setSelectedDevice(entry._deviceRaw);
                        }}
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '2fr 80px 1fr 1fr 2fr 1fr 40px',
                          padding: '14px 20px',
                          borderBottom: idx < filtered.length - 1 ? `1px solid ${C.borderDim}` : 'none',
                          alignItems: 'center',
                          cursor: 'pointer',
                          transition: 'background 0.12s',
                        }}
                        whileHover={{ backgroundColor: 'rgba(245,158,11,0.04)' }}
                      >
                        {/* name + host */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{
                            width: 32, height: 32, borderRadius: 8,
                            background: isRemote ? C.tealDim : C.amberDim,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            position: 'relative',
                          }}>
                            <DeviceIcon type={entry.type} size={15} />
                            {showPulse && (
                              <span style={{
                                position: 'absolute', top: -3, right: -3,
                                width: 7, height: 7, borderRadius: '50%',
                                background: entry.status === 'live' ? C.teal : C.amber,
                                boxShadow: `0 0 6px ${entry.status === 'live' ? C.teal : C.amber}`,
                                animation: 'pulse 1.5s ease-in-out infinite',
                              }} />
                            )}
                          </div>
                          <div>
                            <div style={{ ...UI, fontSize: 13, fontWeight: 500, color: C.text }}>{entry.name}</div>
                            <div style={{ ...MONO, fontSize: 10, color: C.muted, marginTop: 2 }}>
                              {entry.os || '—'}
                            </div>
                          </div>
                        </div>

                        {/* source */}
                        <div><SourceBadge source={entry.source} /></div>

                        {/* status */}
                        <div>
                          <span style={{
                            ...MONO, fontSize: 10, letterSpacing: '0.08em',
                            color: sm.color, background: sm.dim,
                            padding: '3px 9px', borderRadius: 5,
                          }}>
                            {sm.label}
                          </span>
                        </div>

                        {/* department */}
                        <div style={{ ...UI, fontSize: 12, color: C.muted }}>
                          {entry.department || (isRemote ? <span style={{ color: C.dim, ...MONO, fontSize: 10 }}>remote</span> : '—')}
                        </div>

                        {/* performance bars */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingRight: 16 }}>
                          {[
                            { label: 'CPU',  value: entry.cpu    },
                            { label: 'MEM',  value: entry.memory },
                            { label: 'DISK', value: entry.disk   },
                          ].filter(m => m.value != null).map(m => (
                            <div key={m.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ ...MONO, fontSize: 9, color: C.dim, width: 30, letterSpacing: '0.08em' }}>{m.label}</span>
                              <div style={{ flex: 1 }}><Bar value={m.value} /></div>
                              <span style={{ ...MONO, fontSize: 9, color: C.muted, width: 36, textAlign: 'right' }}>{m.value.toFixed ? m.value.toFixed(0) : m.value}%</span>
                            </div>
                          ))}
                          {entry.battery != null && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ ...MONO, fontSize: 9, color: C.dim, width: 30 }}>BAT</span>
                              <div style={{ flex: 1 }}><Bar value={entry.battery} color={entry.battery < 20 ? C.red : C.green} /></div>
                              <span style={{ ...MONO, fontSize: 9, color: C.muted, width: 36, textAlign: 'right' }}>{entry.battery}%</span>
                            </div>
                          )}
                          {entry.cpu == null && entry.memory == null && entry.disk == null && (
                            <span style={{ ...MONO, fontSize: 9, color: C.dim }}>
                              {entry.status === 'pending' ? 'awaiting agent…' : 'no metrics'}
                            </span>
                          )}
                        </div>

                        {/* security */}
                        <div>
                          {isRemote ? (
                            <span style={{ ...MONO, fontSize: 10, color: C.dim }}>—</span>
                          ) : allSecure ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, ...MONO, fontSize: 10, color: C.green }}><ShieldCheck size={13} />SECURE</span>
                          ) : (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, ...MONO, fontSize: 10, color: C.red }}><ShieldAlert size={13} />ISSUES</span>
                          )}
                        </div>

                        {/* chevron */}
                        <div style={{ display: 'flex', justifyContent: 'center' }}>
                          <ChevronRight size={14} color={C.dim} />
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {/* ════ tab 1: analytics ════ */}
          {tab === 1 && <AnalyticsTab entries={allEntries} />}

        </motion.div>
      </AnimatePresence>

      {/* ── managed device detail modal ── */}
      <AnimatePresence>
        {selectedDevice && (
          <DeviceDetail device={selectedDevice} onClose={() => setSelectedDevice(null)} />
        )}
      </AnimatePresence>

      {/* ── new remote agent modal ── */}
      {showNewAgent && (
        <NewAgentModal
          initialLabel={prefilledLabel}
          onClose={() => { setShowNewAgent(false); setPrefilledLabel(''); }}
          onCreated={() => { fetchAll(); }}
        />
      )}
    </div>
  );
}
