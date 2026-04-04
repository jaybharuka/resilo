import React, { useEffect, useState, useCallback } from 'react';
import { apiService, systemApi } from '../services/api';
import {
  LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { TrendingUp, Activity, Server, Wifi, AlertTriangle, RefreshCw } from 'lucide-react';
import InfoTip from './InfoTip';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const UI      = { fontFamily: "'Outfit', sans-serif" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const PANEL = {
  background: 'rgb(22, 20, 16)',
  border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: '12px',
  boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
};

const CHART_GRID  = 'rgba(42,40,32,0.8)';
const CHART_AXIS  = '#3A342D';
const CHART_TIP   = { backgroundColor: 'rgb(31,29,24)', borderColor: 'rgba(42,40,32,0.9)', borderRadius: '8px', fontFamily: "'IBM Plex Mono', monospace", fontSize: '11px' };

const RISK_META = {
  low:    { color: '#2DD4BF', bg: 'rgba(45,212,191,0.08)',  border: 'rgba(45,212,191,0.2)'  },
  medium: { color: '#F59E0B', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.2)'  },
  high:   { color: '#F87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.2)' },
};

const PRIORITY_META = {
  high:   { color: '#F87171' },
  medium: { color: '#F59E0B' },
  low:    { color: '#2DD4BF' },
};

function fmtTs(ts) {
  try {
    const d = new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

function avg(arr, key) {
  if (!arr.length) return null;
  const sum = arr.reduce((s, x) => s + (Number(x[key]) || 0), 0);
  return Math.round(sum / arr.length);
}
function peak(arr, key) {
  if (!arr.length) return null;
  return Math.round(Math.max(...arr.map(x => Number(x[key]) || 0)));
}

function StatCard({ label, value, unit, sub, color, info }) {
  return (
    <div style={{ ...PANEL, padding: '18px 20px', borderTop: `2px solid ${color}`, position: 'relative' }}>
      {info && (
        <div style={{ position: 'absolute', top: '10px', right: '10px', zIndex: 10 }}>
          <InfoTip info={info} />
        </div>
      )}
      <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: '#4A443D', marginBottom: '10px' }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
        <span style={{ ...DISPLAY, fontSize: '2.6rem', color: '#F5F0E8', lineHeight: 1 }}>
          {value ?? '—'}
        </span>
        {unit && <span style={{ ...MONO, fontSize: '12px', color: '#6B6357' }}>{unit}</span>}
      </div>
      {sub != null && (
        <div style={{ ...UI, fontSize: '12px', color: '#4A443D', marginTop: '6px' }}>{sub}</div>
      )}
    </div>
  );
}

function SectionHeader({ icon, label, right }) {
  return (
    <div style={{
      padding: '18px 22px',
      borderBottom: '1px solid rgba(42,40,32,0.9)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ color: '#F59E0B', display: 'flex' }}>{icon}</span>
        <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>{label}</span>
      </div>
      {right}
    </div>
  );
}

function EmptyState({ text, sub }) {
  return (
    <div style={{ padding: '48px 0', textAlign: 'center' }}>
      <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: '#3A342D' }}>{text}</div>
      {sub && <div style={{ ...UI, fontSize: '12px', color: '#3A342D', marginTop: '8px' }}>{sub}</div>}
    </div>
  );
}

export default function Analytics() {
  const [perf, setPerf]       = useState([]);
  const [pred, setPred]       = useState(null);   // object: { predictions, recommendations, confidence }
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState('');
  const [range, setRange]     = useState('1hour');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [series, predictive] = await Promise.all([
        apiService.getPerformanceData(range).catch(() => []),
        systemApi.getPredictive(range).catch(() => null),
      ]);
      setPerf(Array.isArray(series) ? series : []);
      // API returns either a flat array (Insights path) or the richer object — handle both
      if (predictive && !Array.isArray(predictive) && predictive.predictions) {
        setPred(predictive);
      } else {
        setPred(null);
      }
    } catch {
      setError('Failed to load analytics data.');
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const handler = () => load();
    try { window.addEventListener('aiops:refresh', handler); } catch {}
    return () => { try { window.removeEventListener('aiops:refresh', handler); } catch {} };
  }, [load]);

  // Prepare chart data — label x-axis with formatted timestamps
  const chartData = perf.map(pt => ({
    ...pt,
    time: fmtTs(pt.timestamp),
    net_in:  pt.network_in  != null ? Math.round(pt.network_in)  : null,
    net_out: pt.network_out != null ? Math.round(pt.network_out) : null,
  }));

  const predictions    = pred?.predictions      || {};
  const recommendations = pred?.recommendations || [];
  const confidence     = pred?.confidence       ?? null;
  const historyPoints  = pred?.history_points   ?? null;

  const cpuAvg  = avg(perf, 'cpu');
  const memAvg  = avg(perf, 'memory');
  const diskAvg = avg(perf, 'disk');
  const netAvg  = avg(perf, 'network_in');

  const cpuPeak  = peak(perf, 'cpu');
  const memPeak  = peak(perf, 'memory');

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', color: '#F5F0E8', margin: 0, lineHeight: 1 }}>
            Analytics
          </h1>
          <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: '#4A443D', marginTop: '6px' }}>
            PERFORMANCE TRENDS · PREDICTIVE ANALYSIS · RECOMMENDATIONS
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <select
            value={range}
            onChange={e => setRange(e.target.value)}
            style={{
              background: 'rgb(22,20,16)',
              border: '1px solid rgba(42,40,32,0.9)',
              borderRadius: '6px',
              padding: '6px 12px',
              ...MONO, fontSize: '11px', letterSpacing: '0.08em', color: '#A89F8C',
              cursor: 'pointer', outline: 'none',
            }}
          >
            <option value="1hour">LAST 1 HOUR</option>
            <option value="6hours">LAST 6 HOURS</option>
            <option value="24hours">LAST 24 HOURS</option>
          </select>
          <button
            onClick={() => setRefreshAt(Date.now())}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '32px', height: '32px', borderRadius: '6px',
              background: 'transparent', border: '1px solid rgba(42,40,32,0.9)',
              color: '#4A443D', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.4 : 1,
            }}
            onMouseEnter={e => { e.currentTarget.style.color = '#F59E0B'; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.35)'; }}
            onMouseLeave={e => { e.currentTarget.style.color = '#4A443D'; e.currentTarget.style.borderColor = 'rgba(42,40,32,0.9)'; }}
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ ...MONO, fontSize: '11px', letterSpacing: '0.08em', color: '#F87171', padding: '12px 16px', borderRadius: '8px', background: 'rgba(248,113,113,0.07)', border: '1px solid rgba(248,113,113,0.2)' }}>
          {error}
        </div>
      )}

      {/* Stat cards */}
      {!loading && perf.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="AVG CPU"    value={cpuAvg}  unit="%" sub={`Peak ${cpuPeak}%`}  color="#F59E0B"
            info="Mean CPU utilisation across all samples in the selected time window. Peak shows the highest recorded value. Sustained averages above 70% may indicate resource contention." />
          <StatCard label="AVG MEMORY" value={memAvg}  unit="%" sub={`Peak ${memPeak}%`}  color="#2DD4BF"
            info="Mean RAM utilisation for the period. Peak is the highest observed value. Memory rarely drops quickly — a rising average over time suggests a memory leak or workload growth." />
          <StatCard label="AVG DISK"   value={diskAvg} unit="%" sub={`${perf.length} samples`} color="#A78BFA"
            info="Average disk space utilisation across the period. Disk usage grows monotonically unless files are deleted. Configure disk cleanup rules in Remediation to auto-free space." />
          <StatCard label="AVG NET IN" value={netAvg}  unit="KB/s" sub="inbound throughput" color="#FB923C"
            info="Mean inbound network throughput in KB/s for the selected window. Spikes often correlate with deployments, log ingestion, or backup syncs." />
        </div>
      )}

      {loading && (
        <div style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: '#4A443D', padding: '48px 0', textAlign: 'center' }}>
          LOADING…
        </div>
      )}

      {/* Warmup notice — shown when history buffer is thin */}
      {!loading && perf.length > 0 && perf.length < 6 && (
        <div style={{ ...MONO, fontSize: '11px', letterSpacing: '0.08em', color: '#4A443D', padding: '10px 14px', borderRadius: '8px', background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.12)' }}>
          COLLECTING DATA — {perf.length} sample{perf.length !== 1 ? 's' : ''} so far. Charts will fill in as the system collects readings (every 10s).
        </div>
      )}

      {/* CPU + Memory time-series */}
      {!loading && chartData.length > 0 && (
        <div style={PANEL}>
          <SectionHeader
            icon={<Activity size={14} />}
            label="CPU & MEMORY OVER TIME"
            right={
              <div style={{ display: 'flex', gap: '16px' }}>
                {[['#F59E0B', 'CPU'], ['#2DD4BF', 'Memory']].map(([c, l]) => (
                  <span key={l} style={{ display: 'flex', alignItems: 'center', gap: '5px', ...UI, fontSize: '12px', color: '#6B6357' }}>
                    <span style={{ width: '20px', height: '2px', background: c, display: 'inline-block', borderRadius: '1px' }} />
                    {l}
                  </span>
                ))}
              </div>
            }
          />
          <div style={{ padding: '20px 22px', height: '260px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                <XAxis dataKey="time" stroke={CHART_AXIS} tick={{ ...MONO, fontSize: 10, fill: '#4A443D' }} interval="preserveStartEnd" />
                <YAxis stroke={CHART_AXIS} tick={{ ...MONO, fontSize: 10, fill: '#4A443D' }} domain={[0, 100]} unit="%" />
                <Tooltip contentStyle={CHART_TIP} labelStyle={{ color: '#A89F8C' }} itemStyle={{ color: '#F5F0E8' }} formatter={(v) => [`${v}%`]} />
                <Line type="monotone" dataKey="cpu"    stroke="#F59E0B" strokeWidth={2} dot={false} isAnimationActive={false} name="CPU" />
                <Line type="monotone" dataKey="memory" stroke="#2DD4BF" strokeWidth={2} dot={false} isAnimationActive={false} name="Memory" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Disk + Network */}
      {!loading && chartData.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

          {/* Disk */}
          <div style={PANEL}>
            <SectionHeader icon={<Server size={14} />} label="DISK USAGE OVER TIME" />
            <div style={{ padding: '20px 22px', height: '200px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="diskGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#A78BFA" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#A78BFA" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                  <XAxis dataKey="time" stroke={CHART_AXIS} tick={{ ...MONO, fontSize: 10, fill: '#4A443D' }} interval="preserveStartEnd" />
                  <YAxis stroke={CHART_AXIS} tick={{ ...MONO, fontSize: 10, fill: '#4A443D' }} domain={[0, 100]} unit="%" />
                  <Tooltip contentStyle={CHART_TIP} labelStyle={{ color: '#A89F8C' }} itemStyle={{ color: '#F5F0E8' }} formatter={(v) => [`${v}%`]} />
                  <Area type="monotone" dataKey="disk" stroke="#A78BFA" strokeWidth={2} fill="url(#diskGrad)" dot={false} isAnimationActive={false} name="Disk" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Network */}
          {chartData.some(d => d.net_in != null) ? (
            <div style={PANEL}>
              <SectionHeader
                icon={<Wifi size={14} />}
                label="NETWORK THROUGHPUT"
                right={
                  <div style={{ display: 'flex', gap: '14px' }}>
                    {[['#FB923C', '↑ Out'], ['#38BDF8', '↓ In']].map(([c, l]) => (
                      <span key={l} style={{ display: 'flex', alignItems: 'center', gap: '5px', ...UI, fontSize: '12px', color: '#6B6357' }}>
                        <span style={{ width: '16px', height: '2px', background: c, display: 'inline-block', borderRadius: '1px' }} />
                        {l}
                      </span>
                    ))}
                  </div>
                }
              />
              <div style={{ padding: '20px 22px', height: '200px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="netInGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#38BDF8" stopOpacity={0.12} />
                        <stop offset="95%" stopColor="#38BDF8" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="netOutGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#FB923C" stopOpacity={0.12} />
                        <stop offset="95%" stopColor="#FB923C" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                    <XAxis dataKey="time" stroke={CHART_AXIS} tick={{ ...MONO, fontSize: 10, fill: '#4A443D' }} interval="preserveStartEnd" />
                    <YAxis stroke={CHART_AXIS} tick={{ ...MONO, fontSize: 10, fill: '#4A443D' }} unit=" KB/s" />
                    <Tooltip contentStyle={CHART_TIP} labelStyle={{ color: '#A89F8C' }} itemStyle={{ color: '#F5F0E8' }} formatter={(v) => [`${v} KB/s`]} />
                    <Area type="monotone" dataKey="net_in"  stroke="#38BDF8" strokeWidth={2} fill="url(#netInGrad)"  dot={false} isAnimationActive={false} name="Net In" />
                    <Area type="monotone" dataKey="net_out" stroke="#FB923C" strokeWidth={2} fill="url(#netOutGrad)" dot={false} isAnimationActive={false} name="Net Out" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <div style={PANEL}>
              <SectionHeader icon={<Wifi size={14} />} label="NETWORK THROUGHPUT" />
              <EmptyState text="NO NETWORK DATA IN THIS DATASET" />
            </div>
          )}
        </div>
      )}

      {/* Predictive Analysis */}
      {!loading && (
        <div style={PANEL}>
          <SectionHeader
            icon={<TrendingUp size={14} />}
            label="PREDICTIVE ANALYSIS"
            right={confidence != null && (
              <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.08em', color: '#4A443D' }}>
                MODEL CONFIDENCE <span style={{ color: '#F59E0B' }}>{confidence}%</span>
                {historyPoints != null && (
                  <span style={{ marginLeft: '10px', color: '#3A342D' }}>
                    ({historyPoints} pts)
                  </span>
                )}
              </span>
            )}
          />
          {pred === null ? (
            <EmptyState
              text="PREDICTIVE ENGINE UNAVAILABLE"
              sub="Start the Python backend (python api_server.py) and refresh."
            />
          ) : Object.keys(predictions).length > 0 ? (
            <div style={{ padding: '20px 22px' }} className="grid sm:grid-cols-3 gap-4">
              {Object.entries(predictions).map(([metric, data]) => {
                const risk = (data.risk || 'low').toLowerCase();
                const rm = RISK_META[risk] || RISK_META.low;
                const projected = Array.isArray(data.predicted) ? data.predicted : [];
                const projMax = projected.length ? Math.round(Math.max(...projected)) : null;
                const projMin = projected.length ? Math.round(Math.min(...projected)) : null;

                return (
                  <div
                    key={metric}
                    style={{
                      padding: '16px',
                      borderRadius: '10px',
                      background: rm.bg,
                      border: `1px solid ${rm.border}`,
                      borderLeft: `3px solid ${rm.color}`,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: rm.color }}>
                        {metric.toUpperCase()}
                      </span>
                      <span style={{
                        ...MONO, fontSize: '9px', letterSpacing: '0.1em',
                        color: rm.color, background: `${rm.color}18`,
                        border: `1px solid ${rm.border}`,
                        borderRadius: '4px', padding: '2px 6px',
                      }}>
                        {risk.toUpperCase()} RISK
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px', marginBottom: '10px' }}>
                      <span style={{ ...DISPLAY, fontSize: '2.4rem', color: '#F5F0E8', lineHeight: 1 }}>
                        {data.current ?? '—'}
                      </span>
                      <span style={{ ...MONO, fontSize: '12px', color: '#6B6357' }}>% now</span>
                    </div>

                    {projected.length > 0 && (
                      <>
                        <div style={{ height: '40px', marginBottom: '8px' }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={projected.map((v, i) => ({ i, v }))}>
                              <Line type="monotone" dataKey="v" stroke={rm.color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ ...MONO, fontSize: '10px', color: '#4A443D' }}>
                            Min <span style={{ color: '#6B6357' }}>{projMin}%</span>
                          </span>
                          <span style={{ ...MONO, fontSize: '10px', color: '#4A443D' }}>
                            Max <span style={{ color: rm.color }}>{projMax}%</span>
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          ) : <EmptyState text="NO PREDICTIVE DATA AVAILABLE" sub="Collecting baseline metrics…" />}
        </div>
      )}

      {/* Recommendations */}
      {!loading && recommendations.length > 0 && (
        <div style={PANEL}>
          <SectionHeader icon={<AlertTriangle size={14} />} label="RECOMMENDATIONS" />
          <div style={{ padding: '16px 22px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {recommendations.map((r, i) => {
              const priority = (r.priority || 'low').toLowerCase();
              const pm = PRIORITY_META[priority] || PRIORITY_META.low;
              return (
                <div
                  key={i}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: '12px',
                    padding: '12px 14px', borderRadius: '8px',
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid rgba(42,40,32,0.9)',
                  }}
                >
                  <span style={{
                    ...MONO, fontSize: '9px', letterSpacing: '0.1em',
                    color: pm.color, border: `1px solid ${pm.color}40`,
                    borderRadius: '4px', padding: '2px 6px',
                    flexShrink: 0, marginTop: '1px',
                    background: `${pm.color}12`,
                  }}>
                    {priority.toUpperCase()}
                  </span>
                  <span style={{ ...UI, fontSize: '13px', color: '#A89F8C', lineHeight: 1.5 }}>
                    {r.action}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!loading && !error && perf.length === 0 && (
        <EmptyState
          text="NO PERFORMANCE DATA AVAILABLE"
          sub={pred === null
            ? "Backend is offline — run: python api_server.py"
            : "Backend is connected but collecting first samples. Auto-refreshes every 30s."}
        />
      )}
    </div>
  );
}
