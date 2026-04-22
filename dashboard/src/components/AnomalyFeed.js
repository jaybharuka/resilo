import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { Zap, TrendingUp, TrendingDown, Activity, RefreshCw } from 'lucide-react';

const C = {
  bg:     'rgb(22,20,16)',
  border: 'rgba(42,40,32,0.9)',
  text1:  '#F5F0E8',
  text2:  '#A89F8C',
  text3:  '#4A443D',
  amber:  '#F59E0B',
  red:    '#EF4444',
  green:  '#10B981',
  teal:   '#14B8A6',
  mono:   "'IBM Plex Mono', monospace",
  ui:     "'Outfit', sans-serif",
};

const TYPE_META = {
  spike:          { label: 'SPIKE',     color: C.red,   Icon: TrendingUp   },
  sudden_drop:    { label: 'DROP',      color: C.teal,  Icon: TrendingDown },
  sustained_high: { label: 'SUSTAINED', color: C.amber, Icon: TrendingUp   },
  sustained_low:  { label: 'SUSTAINED', color: C.teal,  Icon: TrendingDown },
  oscillating:    { label: 'OSCILLATE', color: '#A78BFA', Icon: Activity   },
  anomaly:        { label: 'ANOMALY',   color: C.amber, Icon: Zap          },
};

const METRIC_LABEL = { cpu: 'CPU', memory: 'MEM', disk: 'DISK' };

function timeAgo(isoStr) {
  if (!isoStr) return '—';
  const secs = Math.floor((Date.now() - new Date(isoStr)) / 1000);
  if (secs < 60)   return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}

function SummaryBar({ summary }) {
  if (!summary) return null;
  const { critical = 0, warning = 0, by_type = {} } = summary;
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
      {critical > 0 && (
        <span style={{ fontFamily: C.mono, fontSize: 10, color: C.red,
          background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
          padding: '3px 10px', borderRadius: 20 }}>
          {critical} critical
        </span>
      )}
      {warning > 0 && (
        <span style={{ fontFamily: C.mono, fontSize: 10, color: C.amber,
          background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)',
          padding: '3px 10px', borderRadius: 20 }}>
          {warning} warning
        </span>
      )}
      {Object.entries(by_type).map(([t, n]) => (
        <span key={t} style={{ fontFamily: C.mono, fontSize: 10, color: C.text3,
          padding: '3px 8px' }}>
          {n} {t.replace('_', ' ')}
        </span>
      ))}
    </div>
  );
}

function AnomalyRow({ a }) {
  const meta = TYPE_META[a.type] || TYPE_META.anomaly;
  const { Icon } = meta;
  const sevColor = a.severity === 'critical' ? C.red : C.amber;
  const absZ = Math.abs(a.zscore);

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '28px 48px 52px 1fr auto auto',
      gap: 10, alignItems: 'center',
      padding: '9px 12px',
      borderBottom: `1px solid ${C.border}`,
      background: a.severity === 'critical' ? 'rgba(239,68,68,0.04)' : 'transparent',
    }}>
      <Icon size={14} color={meta.color} />

      {/* Metric */}
      <span style={{ fontFamily: C.mono, fontSize: 10, color: C.teal }}>
        {METRIC_LABEL[a.metric] || a.metric}
      </span>

      {/* Type badge */}
      <span style={{ fontFamily: C.mono, fontSize: 9, color: meta.color,
        background: `${meta.color}12`, border: `1px solid ${meta.color}30`,
        padding: '2px 5px', borderRadius: 3, textAlign: 'center',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {meta.label}
      </span>

      {/* Metric value + baseline */}
      <span style={{ fontFamily: C.mono, fontSize: 11, color: sevColor }}>
        {a.value.toFixed(1)}%
        <span style={{ color: C.text3, fontSize: 9, marginLeft: 4 }}>
          (baseline {a.baseline_mean.toFixed(1)} ± {a.baseline_std.toFixed(1)})
        </span>
      </span>

      {/* Z-score */}
      <span style={{ fontFamily: C.mono, fontSize: 10,
        color: absZ >= 4 ? C.red : C.amber, textAlign: 'right', whiteSpace: 'nowrap' }}>
        z={a.zscore > 0 ? '+' : ''}{a.zscore.toFixed(1)}σ
      </span>

      {/* Time */}
      <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3,
        minWidth: 50, textAlign: 'right' }}>
        {timeAgo(a.timestamp)}
      </span>
    </div>
  );
}

export default function AnomalyFeed({ maxRows = 15 }) {
  const [anomalies, setAnomalies] = useState([]);
  const [summary, setSummary]     = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [lastAt, setLastAt]       = useState(null);
  const [secAgo, setSecAgo]       = useState(null);
  const mountedRef                = useRef(true);
  const timerRef                  = useRef(null);

  const load = useCallback(async () => {
    try {
      const data = await apiService.detectAnomalies(60);
      if (!mountedRef.current) return;
      setAnomalies(data.anomalies || []);
      setSummary(data.summary);
      setError(null);
      setLastAt(Date.now());
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e?.response?.data?.detail || e?.message || 'Failed to load anomalies');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    timerRef.current = setInterval(load, 15000);
    const staleTmr = setInterval(() => {
      setLastAt(t => { if (t) setSecAgo(Math.round((Date.now() - t) / 1000)); return t; });
    }, 1000);
    return () => {
      mountedRef.current = false;
      clearInterval(timerRef.current);
      clearInterval(staleTmr);
    };
  }, [load]);

  const visible = anomalies.slice(0, maxRows);

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10,
        padding: '16px 20px', borderBottom: `1px solid ${C.border}` }}>
        <Zap size={15} color={C.amber} />
        <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
          ANOMALY DETECTION
        </span>
        {!loading && (
          <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3, marginLeft: 4 }}>
            rolling z-score · σ ≥ 2.5
          </span>
        )}
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          {secAgo != null && (
            <span style={{ fontFamily: C.mono, fontSize: 9,
              color: secAgo > 45 ? C.amber : C.text3 }}>
              {secAgo}s ago
            </span>
          )}
          <span style={{ display: 'flex', alignItems: 'center', gap: 4,
            fontFamily: C.mono, fontSize: 9, letterSpacing: '0.08em',
            color: error ? C.red : C.teal }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%',
              background: error ? C.red : C.teal,
              boxShadow: error ? 'none' : `0 0 5px ${C.teal}90`,
              animation: !error ? 'pulse 2s infinite' : 'none' }} />
            {!error && 'LIVE'}
          </span>
          {!loading && (
            <button onClick={load} style={{ background: 'none', border: 'none',
              cursor: 'pointer', padding: 4, color: C.text3 }} title="Refresh">
              <RefreshCw size={12} />
            </button>
          )}
        </span>
      </div>

      <div style={{ padding: '14px 20px 0' }}>
        <SummaryBar summary={summary} />
      </div>

      {/* Column headers */}
      {!loading && !error && anomalies.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '28px 48px 52px 1fr auto auto',
          gap: 10, padding: '4px 12px 6px',
          borderBottom: `1px solid ${C.border}` }}>
          {['', 'METRIC', 'TYPE', 'VALUE (BASELINE)', 'Z-SCORE', 'AGO'].map((h, i) => (
            <span key={i} style={{ fontFamily: C.mono, fontSize: 9,
              letterSpacing: '0.08em', color: C.text3 }}>{h}</span>
          ))}
        </div>
      )}

      {/* Rows */}
      {loading && (
        <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3,
          padding: '24px 0', textAlign: 'center' }}>
          DETECTING…
        </div>
      )}
      {!loading && error && (
        <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red,
          padding: '24px 0', textAlign: 'center' }}>
          {error}
        </div>
      )}
      {!loading && !error && anomalies.length === 0 && (
        <div style={{ padding: '24px 0', textAlign: 'center' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.green }}>
            ✓ NO ANOMALIES DETECTED
          </div>
          <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 6 }}>
            All signals within normal range
          </div>
        </div>
      )}
      {visible.map((a, i) => (
        <div key={`${a.metric}-${a.timestamp}-${i}`}
          style={{ animation: 'fadeIn 0.35s ease both', animationDelay: `${i * 30}ms` }}>
          <AnomalyRow a={a} />
        </div>
      ))}
      {anomalies.length > maxRows && (
        <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3,
          padding: '10px 16px', textAlign: 'center' }}>
          +{anomalies.length - maxRows} more anomalies
        </div>
      )}
      <div style={{ height: 10 }} />
    </div>
  );
}
