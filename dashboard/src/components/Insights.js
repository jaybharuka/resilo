import React, { useState, useEffect, useCallback } from 'react';
import { apiService, systemApi, actionsApi } from '../services/api';
import { toast } from 'react-hot-toast';
import {
  Bot, AlertTriangle, Sparkles, BarChart3, Target, TrendingUp,
  Cpu, Activity, HardDrive, ChevronDown, ChevronUp, Zap, RefreshCw,
} from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const UI      = { fontFamily: "'Outfit', sans-serif" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const PANEL = {
  background: 'rgb(22, 20, 16)',
  border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: '12px',
  boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
};

const TABS = ['AI HEALTH', 'ANOMALIES', 'ANALYTICS'];

// ── Status helpers ──────────────────────────────────────────────────────────
const statusMeta = (s) => ({
  healthy:  { color: '#2DD4BF', glow: 'rgba(45,212,191,0.45)',  label: 'HEALTHY'  },
  degraded: { color: '#F59E0B', glow: 'rgba(245,158,11,0.45)',  label: 'DEGRADED' },
  critical: { color: '#F87171', glow: 'rgba(248,113,113,0.45)', label: 'CRITICAL' },
  loading:  { color: '#4A443D', glow: 'none',                   label: 'LOADING'  },
}[s] || { color: '#4A443D', glow: 'none', label: String(s || '—').toUpperCase() });

const riskMeta = (r) => ({
  low:    { color: '#2DD4BF', bg: 'rgba(45,212,191,0.08)',  border: 'rgba(45,212,191,0.2)',  label: 'LOW'    },
  medium: { color: '#F59E0B', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.2)',  label: 'MEDIUM' },
  high:   { color: '#F87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.2)', label: 'HIGH'   },
}[r] || { color: '#6B6357', bg: 'rgba(255,255,255,0.02)', border: 'rgba(42,40,32,0.9)', label: '—' });

const severityMeta = (s) => ({
  critical: { color: '#F87171', bg: 'rgba(248,113,113,0.06)', border: 'rgba(248,113,113,0.18)' },
  warning:  { color: '#F59E0B', bg: 'rgba(245,158,11,0.06)',  border: 'rgba(245,158,11,0.18)'  },
  info:     { color: '#2DD4BF', bg: 'rgba(45,212,191,0.06)',  border: 'rgba(45,212,191,0.18)'  },
}[s] || { color: '#6B6357', bg: 'rgba(255,255,255,0.02)', border: 'rgba(42,40,32,0.9)' });

const priorityMeta = (p) => ({
  high:   { color: '#F87171' },
  medium: { color: '#F59E0B' },
  low:    { color: '#2DD4BF' },
}[p] || { color: '#6B6357' });

// ── Utility ─────────────────────────────────────────────────────────────────
const avg = (arr, key) =>
  arr.length === 0 ? null : Math.round(arr.reduce((s, x) => s + (x[key] || 0), 0) / arr.length);

const fmt = (n) => (n == null ? '—' : n.toLocaleString());

const barColor = (v) => v > 85 ? '#F87171' : v > 65 ? '#F59E0B' : '#2DD4BF';

function fmtUptime(seconds) {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function fmtTs(unixTs) {
  if (!unixTs) return '—';
  const d = new Date(unixTs * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ── Shared sub-components ────────────────────────────────────────────────────
function SectionLabel({ icon, children, suffix }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ color: '#F59E0B', display: 'flex' }}>{icon}</span>
        <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>
          {children}
        </span>
      </div>
      {suffix}
    </div>
  );
}

function PanelHeader({ icon, label, suffix }) {
  return (
    <div style={{ padding: '18px 22px', borderBottom: '1px solid rgba(42,40,32,0.9)' }}>
      <SectionLabel icon={icon} suffix={suffix}>{label}</SectionLabel>
    </div>
  );
}

function Badge({ color, bg, border, label }) {
  return (
    <span style={{
      ...MONO, fontSize: '9px', letterSpacing: '0.1em',
      color, background: bg, border: `1px solid ${border}`,
      borderRadius: '10px', padding: '2px 7px',
    }}>
      {label}
    </span>
  );
}

function EmptyState({ text, sub }) {
  return (
    <div style={{ padding: '40px 0', textAlign: 'center' }}>
      <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: '#3A342D' }}>{text}</div>
      {sub && <div style={{ ...UI, fontSize: '12px', color: '#3A342D', marginTop: '6px' }}>{sub}</div>}
    </div>
  );
}

// ── Anomaly Item ─────────────────────────────────────────────────────────────
function AnomalyItem({ a }) {
  const [open, setOpen] = useState(false);
  const sv = severityMeta(a.severity);
  return (
    <div style={{
      padding: '12px 14px', borderRadius: '8px',
      background: sv.bg, border: `1px solid ${sv.border}`,
      borderLeft: `3px solid ${sv.color}`,
    }}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', cursor: 'pointer' }}
        onClick={() => setOpen(o => !o)}
      >
        <div style={{ flex: 1, minWidth: 0, paddingRight: '8px' }}>
          <div style={{ ...UI, fontSize: '13px', color: '#F5F0E8', fontWeight: 500, marginBottom: '3px' }}>
            {a.message}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: '#4A443D' }}>
              {a.source}
            </span>
            {a.timestamp && (
              <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.06em', color: '#3A342D' }}>
                · {fmtTs(a.timestamp)}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <Badge color={sv.color} bg={sv.bg} border={sv.border} label={(a.severity || 'info').toUpperCase()} />
          <span style={{ color: '#4A443D', display: 'flex' }}>
            {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </span>
        </div>
      </div>
      {open && (
        <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid rgba(42,40,32,0.5)' }}>
          {a.details && (
            <p style={{ ...UI, fontSize: '12px', color: '#6B6357', margin: '0 0 8px' }}>{a.details}</p>
          )}
          {a.recommendation && (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
              <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: '#F59E0B', flexShrink: 0, paddingTop: '2px' }}>
                ACTION
              </span>
              <p style={{ ...UI, fontSize: '12px', color: '#A89F8C', margin: 0 }}>{a.recommendation}</p>
            </div>
          )}
          {a.affected_systems?.length > 0 && (
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
              {a.affected_systems.map(s => (
                <span key={s} style={{
                  ...MONO, fontSize: '9px', letterSpacing: '0.06em',
                  color: '#4A443D', background: 'rgba(42,40,32,0.5)',
                  borderRadius: '4px', padding: '2px 6px',
                }}>{s}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Insights() {
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [health, setHealth]   = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [predictive, setPredictive] = useState(null);
  const [perf, setPerf] = useState([]);
  const [range, setRange] = useState('1hour');
  const [perfLoading, setPerfLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState({});
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchCore = useCallback(async () => {
    try {
      const [h, a] = await Promise.all([
        apiService.getAiInsights().catch(() => null),
        apiService.getAlerts().catch(() => []),
      ]);
      if (h) setHealth(h);
      setAnomalies(Array.isArray(a) ? a : []);
      setLastUpdated(new Date());
    } catch {}
    setLoading(false);
  }, []);

  const fetchPredictive = useCallback(async (r) => {
    try {
      const p = await systemApi.getPredictive(r).catch(() => null);
      // Backend returns nested object: { predictions: {cpu,memory,disk}, recommendations, confidence }
      if (p && p.predictions) setPredictive(p);
      else if (Array.isArray(p)) setPredictive(null); // ignore old flat shape
    } catch {}
  }, []);

  const fetchPerf = useCallback(async (r) => {
    setPerfLoading(true);
    try {
      const s = await apiService.getPerformanceData(r).catch(() => []);
      setPerf(Array.isArray(s) ? s : []);
    } catch {} finally { setPerfLoading(false); }
  }, []);

  // Initial load + polling
  useEffect(() => {
    fetchCore();
    const id = setInterval(fetchCore, 10000);
    return () => clearInterval(id);
  }, [fetchCore]);

  // Predictive + perf whenever range changes
  useEffect(() => {
    fetchPredictive(range);
    fetchPerf(range);
  }, [range, fetchPredictive, fetchPerf]);

  const runAction = async (key, label, fn) => {
    setActionLoading(l => ({ ...l, [key]: true }));
    const t = toast.loading(`${label}…`);
    try {
      const res = await fn();
      toast.success(res?.message || `${label} complete`, { id: t });
    } catch {
      toast.error(`${label} failed`, { id: t });
    } finally {
      setActionLoading(l => ({ ...l, [key]: false }));
    }
  };

  // ── Derived data ────────────────────────────────────────────────────────────
  const sm = statusMeta(loading ? 'loading' : (health?.status || 'degraded'));
  const gemini = health?.models?.gemini || null;
  const hf     = health?.models?.huggingface || null;

  const preds = predictive?.predictions || null;
  const recs  = predictive?.recommendations || [];
  const conf  = predictive?.confidence ?? null;

  const metricPreds = preds ? [
    { key: 'cpu',    label: 'CPU',    icon: <Cpu size={13} />,      data: preds.cpu    },
    { key: 'memory', label: 'MEMORY', icon: <Activity size={13} />, data: preds.memory },
    { key: 'disk',   label: 'DISK',   icon: <HardDrive size={13} />,data: preds.disk   },
  ] : [];

  const avgCPU  = avg(perf, 'cpu');
  const avgMem  = avg(perf, 'memory');
  const avgDisk = avg(perf, 'disk');

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', color: '#F5F0E8', margin: 0, lineHeight: 1 }}>
            Insights
          </h1>
          <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: '#4A443D', marginTop: '6px' }}>
            AI HEALTH · ANOMALY DETECTION · PERFORMANCE ANALYTICS
          </p>
        </div>
        {lastUpdated && (
          <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.06em', color: '#3A342D' }}>
            UPDATED {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid rgba(42,40,32,0.9)' }}>
        {TABS.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(i)}
            style={{
              padding: '10px 18px', background: 'transparent', border: 'none',
              borderBottom: tab === i ? '2px solid #F59E0B' : '2px solid transparent',
              cursor: 'pointer', marginBottom: '-1px', transition: 'color 0.15s, border-color 0.15s',
              ...MONO, fontSize: '11px', letterSpacing: '0.1em',
              color: tab === i ? '#F59E0B' : '#4A443D',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════
          TAB 0 — AI HEALTH
      ══════════════════════════════════════════ */}
      {tab === 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Status banner */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '14px',
            padding: '14px 20px', borderRadius: '10px',
            background: `${sm.glow === 'none' ? 'rgba(255,255,255,0.02)' : sm.color}10`,
            border: `1px solid ${sm.color}28`,
          }}>
            <div style={{
              width: '9px', height: '9px', borderRadius: '50%',
              background: sm.color, boxShadow: `0 0 10px ${sm.glow}`,
              flexShrink: 0, animation: 'pulse 2s infinite',
            }} />
            <span style={{ ...MONO, fontSize: '12px', letterSpacing: '0.1em', color: sm.color }}>
              SYSTEM {sm.label}
            </span>
            {health?.uptime_seconds != null && (
              <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.06em', color: '#4A443D', marginLeft: 'auto' }}>
                UPTIME {fmtUptime(health.uptime_seconds)}
              </span>
            )}
          </div>

          {/* Model cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            {[
              { key: 'gemini',      label: gemini?.name || 'Gemini Pro',  data: gemini, icon: <Sparkles size={15} /> },
              { key: 'huggingface', label: hf?.name || 'HuggingFace',     data: hf,     icon: <Bot size={15} /> },
            ].map(({ key, label, data, icon }) => {
              const avail = data?.available ?? false;
              const dot   = avail ? '#2DD4BF' : '#F87171';
              return (
                <div key={key} style={PANEL}>
                  <PanelHeader icon={icon} label="AI ENGINE" />
                  <div style={{ padding: '18px 22px' }}>
                    {/* Model name + status */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                      <span style={{ ...DISPLAY, fontSize: '1.5rem', letterSpacing: '0.05em', color: '#F5F0E8' }}>
                        {label}
                      </span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <div style={{
                          width: '7px', height: '7px', borderRadius: '50%',
                          background: dot, boxShadow: avail ? `0 0 8px ${dot}80` : 'none',
                        }} />
                        <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: dot }}>
                          {avail ? 'ONLINE' : 'OFFLINE'}
                        </span>
                      </div>
                    </div>

                    {/* Metrics */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                      {/* Accuracy */}
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                          <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#4A443D' }}>ACCURACY</span>
                          <span style={{ ...MONO, fontSize: '12px', color: data?.accuracy != null ? '#F5F0E8' : '#3A342D' }}>
                            {data?.accuracy != null ? `${data.accuracy}%` : '—'}
                          </span>
                        </div>
                        <div style={{ height: '3px', background: 'rgba(42,40,32,0.9)', borderRadius: '2px', overflow: 'hidden' }}>
                          {data?.accuracy != null && (
                            <div style={{ height: '100%', width: `${data.accuracy}%`, background: '#F59E0B', borderRadius: '2px', transition: 'width 0.6s ease' }} />
                          )}
                        </div>
                      </div>

                      {/* Latency */}
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#4A443D' }}>LATENCY</span>
                        <span style={{ ...MONO, fontSize: '12px', color: data?.latency_ms != null ? '#A89F8C' : '#3A342D' }}>
                          {data?.latency_ms != null ? `${data.latency_ms} ms` : '—'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Key Metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '16px' }}>
            {[
              {
                label: 'PREDICTION ACCURACY',
                value: health?.prediction_accuracy != null ? `${health.prediction_accuracy}%` : '—',
                icon: <Target size={13} />,
                accent: '#F59E0B',
              },
              {
                label: 'INFERENCES TODAY',
                value: fmt(health?.inference_count_today),
                icon: <Zap size={13} />,
                accent: '#2DD4BF',
              },
              {
                label: 'ANOMALIES DETECTED',
                value: health?.anomalies_detected_today != null ? String(health.anomalies_detected_today) : '—',
                icon: <AlertTriangle size={13} />,
                accent: health?.anomalies_detected_today > 0 ? '#F87171' : '#2DD4BF',
              },
            ].map(m => (
              <div key={m.label} style={{
                ...PANEL, padding: '18px 20px',
                display: 'flex', flexDirection: 'column', gap: '12px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                  <span style={{ color: m.accent, display: 'flex' }}>{m.icon}</span>
                  <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.12em', color: '#4A443D' }}>
                    {m.label}
                  </span>
                </div>
                <span style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.03em', color: m.accent, lineHeight: 1 }}>
                  {m.value}
                </span>
              </div>
            ))}
          </div>

          {/* AI Actions */}
          <div style={PANEL}>
            <PanelHeader icon={<Target size={14} />} label="AI ACTIONS" />
            <div style={{ padding: '18px 22px', display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              {[
                { key: 'diag',    label: 'Run Diagnostics', fn: actionsApi.runDiagnostics },
                { key: 'retrain', label: 'Retrain Models',  fn: actionsApi.retrainModels  },
                { key: 'export',  label: 'Export Insights', fn: actionsApi.exportInsights },
              ].map(a => (
                <button
                  key={a.key}
                  onClick={() => runAction(a.key, a.label, a.fn)}
                  disabled={!!actionLoading[a.key]}
                  style={{
                    padding: '9px 18px', borderRadius: '6px',
                    background: actionLoading[a.key] ? 'rgba(245,158,11,0.08)' : 'transparent',
                    border: actionLoading[a.key] ? '1px solid rgba(245,158,11,0.3)' : '1px solid rgba(42,40,32,0.9)',
                    cursor: actionLoading[a.key] ? 'not-allowed' : 'pointer',
                    ...MONO, fontSize: '10px', letterSpacing: '0.1em',
                    color: actionLoading[a.key] ? '#F59E0B' : '#6B6357',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { if (!actionLoading[a.key]) { e.currentTarget.style.borderColor = 'rgba(245,158,11,0.3)'; e.currentTarget.style.color = '#F59E0B'; } }}
                  onMouseLeave={e => { if (!actionLoading[a.key]) { e.currentTarget.style.borderColor = 'rgba(42,40,32,0.9)'; e.currentTarget.style.color = '#6B6357'; } }}
                >
                  {actionLoading[a.key] ? 'RUNNING…' : a.label.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════
          TAB 1 — ANOMALIES & PREDICTIONS
      ══════════════════════════════════════════ */}
      {tab === 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Timeframe for predictions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#4A443D' }}>TIMEFRAME</span>
            {['1hour', '6hours', '24hours'].map(r => (
              <button
                key={r}
                onClick={() => setRange(r)}
                style={{
                  padding: '5px 12px', borderRadius: '5px', cursor: 'pointer',
                  ...MONO, fontSize: '10px', letterSpacing: '0.08em',
                  background: range === r ? 'rgba(245,158,11,0.1)' : 'transparent',
                  border: range === r ? '1px solid rgba(245,158,11,0.3)' : '1px solid rgba(42,40,32,0.9)',
                  color: range === r ? '#F59E0B' : '#4A443D',
                  transition: 'all 0.15s',
                }}
              >
                {r === '1hour' ? '1H' : r === '6hours' ? '6H' : '24H'}
              </button>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>

            {/* Anomalies */}
            <div style={PANEL}>
              <PanelHeader
                icon={<AlertTriangle size={14} />}
                label="ACTIVE ANOMALIES"
                suffix={anomalies.length > 0 ? (
                  <span style={{
                    ...MONO, fontSize: '10px', letterSpacing: '0.08em',
                    color: '#F87171', background: 'rgba(248,113,113,0.1)',
                    border: '1px solid rgba(248,113,113,0.2)', borderRadius: '10px', padding: '2px 8px',
                  }}>
                    {anomalies.length}
                  </span>
                ) : null}
              />
              <div style={{ padding: '14px 22px', display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '480px', overflowY: 'auto' }}>
                {anomalies.length > 0
                  ? anomalies.map((a, i) => <AnomalyItem key={a.id || i} a={a} />)
                  : <EmptyState text="ALL CLEAR" sub="No anomalies detected at current thresholds" />
                }
              </div>
            </div>

            {/* Predictive Analysis */}
            <div style={PANEL}>
              <PanelHeader icon={<Sparkles size={14} />} label="PREDICTIVE ANALYSIS" />
              <div style={{ padding: '14px 22px', display: 'flex', flexDirection: 'column', gap: '12px' }}>

                {/* Confidence */}
                {conf != null && (
                  <div style={{
                    padding: '10px 14px', borderRadius: '8px',
                    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(42,40,32,0.9)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  }}>
                    <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#4A443D' }}>
                      MODEL CONFIDENCE
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ width: '80px', height: '3px', background: 'rgba(42,40,32,0.9)', borderRadius: '2px', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${conf}%`, background: '#F59E0B', borderRadius: '2px', transition: 'width 0.6s ease' }} />
                      </div>
                      <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.06em', color: '#F59E0B' }}>{conf}%</span>
                    </div>
                  </div>
                )}

                {/* Per-metric predictions */}
                {metricPreds.length > 0 ? metricPreds.map(({ key, label, icon, data }) => {
                  if (!data) return null;
                  const peak = data.predicted?.length > 0 ? Math.round(Math.max(...data.predicted)) : null;
                  const rm = riskMeta(data.risk);
                  const trend = peak != null && data.current != null ? peak - data.current : null;
                  return (
                    <div key={key} style={{
                      padding: '14px', borderRadius: '8px',
                      background: rm.bg, border: `1px solid ${rm.border}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                          <span style={{ color: '#A89F8C', display: 'flex' }}>{icon}</span>
                          <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#A89F8C' }}>{label}</span>
                        </div>
                        <Badge color={rm.color} bg={rm.bg} border={rm.border} label={`RISK: ${rm.label}`} />
                      </div>
                      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '16px' }}>
                        <div>
                          <div style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: '#4A443D', marginBottom: '4px' }}>NOW</div>
                          <span style={{ ...DISPLAY, fontSize: '1.6rem', letterSpacing: '0.03em', color: '#F5F0E8' }}>
                            {data.current != null ? `${Math.round(data.current)}%` : '—'}
                          </span>
                        </div>
                        {trend != null && (
                          <div style={{ ...MONO, fontSize: '12px', color: trend > 5 ? '#F87171' : trend > 0 ? '#F59E0B' : '#2DD4BF', marginBottom: '4px' }}>
                            {trend > 0 ? `+${trend}%` : `${trend}%`}
                          </div>
                        )}
                        {peak != null && (
                          <div style={{ marginLeft: 'auto' }}>
                            <div style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: '#4A443D', marginBottom: '4px' }}>PEAK</div>
                            <span style={{ ...DISPLAY, fontSize: '1.6rem', letterSpacing: '0.03em', color: rm.color }}>
                              {peak}%
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                }) : (
                  <EmptyState text="NO PREDICTIONS AVAILABLE" sub="Collecting system history…" />
                )}

                {/* Recommendations */}
                {recs.length > 0 && (
                  <div style={{ marginTop: '4px' }}>
                    <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.12em', color: '#4A443D', marginBottom: '8px' }}>
                      RECOMMENDATIONS
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {recs.map((r, i) => {
                        const pm = priorityMeta(r.priority);
                        return (
                          <div key={i} style={{
                            display: 'flex', gap: '10px', alignItems: 'flex-start',
                            padding: '10px 12px', borderRadius: '7px',
                            background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(42,40,32,0.9)',
                          }}>
                            <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: pm.color, flexShrink: 0, paddingTop: '1px' }}>
                              {(r.priority || 'low').toUpperCase()}
                            </span>
                            <span style={{ ...UI, fontSize: '12px', color: '#A89F8C' }}>{r.action}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════
          TAB 2 — ANALYTICS
      ══════════════════════════════════════════ */}
      {tab === 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Timeframe selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#4A443D' }}>TIMEFRAME</span>
            {['1hour', '6hours', '24hours'].map(r => (
              <button
                key={r}
                onClick={() => setRange(r)}
                style={{
                  padding: '5px 12px', borderRadius: '5px', cursor: 'pointer',
                  ...MONO, fontSize: '10px', letterSpacing: '0.08em',
                  background: range === r ? 'rgba(245,158,11,0.1)' : 'transparent',
                  border: range === r ? '1px solid rgba(245,158,11,0.3)' : '1px solid rgba(42,40,32,0.9)',
                  color: range === r ? '#F59E0B' : '#4A443D',
                  transition: 'all 0.15s',
                }}
              >
                {r === '1hour' ? 'LAST HOUR' : r === '6hours' ? 'LAST 6H' : 'LAST 24H'}
              </button>
            ))}
            {perfLoading && (
              <RefreshCw size={12} style={{ color: '#4A443D', animation: 'spin 1s linear infinite' }} />
            )}
            {perf.length > 0 && (
              <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.06em', color: '#3A342D', marginLeft: 'auto' }}>
                {perf.length} DATA POINTS
              </span>
            )}
          </div>

          {/* Average Performance */}
          <div style={PANEL}>
            <PanelHeader icon={<TrendingUp size={14} />} label="AVERAGE PERFORMANCE" />
            <div style={{ padding: '20px 22px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '16px' }}>
              {[
                { label: 'AVG CPU',    value: avgCPU,  icon: <Cpu size={13} /> },
                { label: 'AVG MEMORY', value: avgMem,  icon: <Activity size={13} /> },
                { label: 'AVG DISK',   value: avgDisk, icon: <HardDrive size={13} /> },
              ].map(m => {
                const bc = m.value != null ? barColor(m.value) : '#4A443D';
                return (
                  <div key={m.label} style={{
                    padding: '18px', borderRadius: '10px',
                    border: '1px solid rgba(42,40,32,0.9)',
                    background: 'rgba(255,255,255,0.015)',
                    display: 'flex', flexDirection: 'column', gap: '12px',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ color: bc, display: 'flex' }}>{m.icon}</span>
                      <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.14em', color: '#4A443D' }}>
                        {m.label}
                      </span>
                    </div>
                    <span style={{ ...DISPLAY, fontSize: '2.6rem', letterSpacing: '0.03em', color: '#F5F0E8', lineHeight: 1 }}>
                      {m.value != null ? (
                        <>
                          {m.value}
                          <span style={{ ...MONO, fontSize: '13px', color: '#6B6357', marginLeft: '3px' }}>%</span>
                        </>
                      ) : (
                        <span style={{ fontSize: '1.4rem', color: '#3A342D' }}>—</span>
                      )}
                    </span>
                    <div style={{ height: '3px', background: 'rgba(42,40,32,0.9)', borderRadius: '2px', overflow: 'hidden' }}>
                      {m.value != null && (
                        <div style={{ height: '100%', width: `${m.value}%`, background: bc, borderRadius: '2px', transition: 'width 0.6s ease' }} />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            {perf.length === 0 && !perfLoading && (
              <div style={{ padding: '0 22px 20px' }}>
                <EmptyState text="NO PERFORMANCE DATA" sub={`No history collected for the selected timeframe`} />
              </div>
            )}
          </div>

          {/* Trend Forecasts */}
          <div style={PANEL}>
            <PanelHeader
              icon={<BarChart3 size={14} />}
              label="TREND FORECASTS"
              suffix={conf != null ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: '#4A443D' }}>CONFIDENCE</span>
                  <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.06em', color: '#F59E0B' }}>{conf}%</span>
                </div>
              ) : null}
            />
            <div style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {metricPreds.length > 0 ? (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
                    {metricPreds.map(({ key, label, icon, data }) => {
                      if (!data) return null;
                      const predicted = data.predicted || [];
                      const peak = predicted.length > 0 ? Math.round(Math.max(...predicted)) : null;
                      const current = data.current != null ? Math.round(data.current) : null;
                      const rm = riskMeta(data.risk);
                      const trend = peak != null && current != null ? peak - current : null;
                      // Sparkline: normalize predicted array to 0-100 for bar heights
                      const maxVal = predicted.length > 0 ? Math.max(...predicted, current || 0, 1) : 100;
                      return (
                        <div key={key} style={{
                          padding: '16px', borderRadius: '10px',
                          background: rm.bg, border: `1px solid ${rm.border}`,
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                              <span style={{ color: rm.color, display: 'flex' }}>{icon}</span>
                              <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#A89F8C' }}>{label}</span>
                            </div>
                            <Badge color={rm.color} bg={rm.bg} border={rm.border} label={rm.label} />
                          </div>

                          {/* Mini sparkline */}
                          {predicted.length > 0 && (
                            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: '32px', marginBottom: '12px' }}>
                              {predicted.map((v, i) => (
                                <div
                                  key={i}
                                  style={{
                                    flex: 1, borderRadius: '1px',
                                    height: `${Math.round((v / maxVal) * 100)}%`,
                                    background: rm.color,
                                    opacity: 0.3 + (i / predicted.length) * 0.7,
                                    minHeight: '2px',
                                    transition: 'height 0.4s ease',
                                  }}
                                />
                              ))}
                            </div>
                          )}

                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                            <div>
                              <div style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: '#4A443D', marginBottom: '3px' }}>CURRENT</div>
                              <span style={{ ...DISPLAY, fontSize: '1.4rem', color: '#F5F0E8' }}>
                                {current != null ? `${current}%` : '—'}
                              </span>
                            </div>
                            {trend != null && (
                              <span style={{
                                ...MONO, fontSize: '11px',
                                color: trend > 10 ? '#F87171' : trend > 0 ? '#F59E0B' : '#2DD4BF',
                              }}>
                                {trend > 0 ? `↑ +${trend}%` : `↓ ${trend}%`}
                              </span>
                            )}
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: '#4A443D', marginBottom: '3px' }}>PEAK</div>
                              <span style={{ ...DISPLAY, fontSize: '1.4rem', color: rm.color }}>
                                {peak != null ? `${peak}%` : '—'}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Recommendations in analytics */}
                  {recs.length > 0 && (
                    <div>
                      <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.12em', color: '#4A443D', marginBottom: '10px' }}>
                        RECOMMENDATIONS
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        {recs.map((r, i) => {
                          const pm = priorityMeta(r.priority);
                          return (
                            <div key={i} style={{
                              display: 'flex', gap: '12px', alignItems: 'flex-start',
                              padding: '11px 14px', borderRadius: '8px',
                              background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(42,40,32,0.9)',
                            }}>
                              <div style={{
                                width: '4px', height: '4px', borderRadius: '50%',
                                background: pm.color, marginTop: '6px', flexShrink: 0,
                              }} />
                              <span style={{ ...UI, fontSize: '13px', color: '#A89F8C' }}>{r.action}</span>
                              <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: pm.color, marginLeft: 'auto', flexShrink: 0, paddingTop: '2px' }}>
                                {(r.priority || '').toUpperCase()}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <EmptyState text="NO FORECAST DATA" sub="Predictions require system history — collecting now" />
              )}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
