import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { Brain, AlertTriangle, Info, ChevronDown, ChevronUp, RefreshCw, Lightbulb } from 'lucide-react';

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

const SEV = {
  critical: { color: C.red,   bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.2)',   label: 'CRITICAL' },
  warning:  { color: C.amber, bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.2)',  label: 'WARNING'  },
  info:     { color: C.teal,  bg: 'rgba(20,184,166,0.08)', border: 'rgba(20,184,166,0.2)', label: 'INFO'     },
};

const TYPE_ICONS = {
  resource_exhaustion:        <AlertTriangle size={14} />,
  cpu_saturation:             <AlertTriangle size={14} />,
  memory_leak:                <AlertTriangle size={14} />,
  disk_pressure:              <AlertTriangle size={14} />,
  recurring_alert_pattern:    <RefreshCw size={14} />,
  noisy_neighbor:             <Info size={14} />,
  critical_storm:             <AlertTriangle size={14} />,
  repeated_remediation_failure: <AlertTriangle size={14} />,
  ineffective_remediation:    <Info size={14} />,
};

function InsightCard({ insight, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const meta = SEV[insight.severity] || SEV.info;

  return (
    <div style={{
      border: `1px solid ${meta.border}`,
      background: meta.bg,
      borderRadius: 8,
      marginBottom: 10,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'flex-start', gap: 10,
          padding: '12px 14px', background: 'transparent', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{ color: meta.color, marginTop: 1, flexShrink: 0 }}>
          {TYPE_ICONS[insight.type] || <Lightbulb size={14} />}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: C.mono, fontSize: 9, letterSpacing: '0.1em',
              color: meta.color, background: `${meta.color}18`, padding: '1px 6px',
              borderRadius: 3, flexShrink: 0 }}>
              {meta.label}
            </span>
            {insight.confidence != null && (
              <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3,
                background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)',
                padding: '1px 6px', borderRadius: 3, flexShrink: 0 }}>
                {Math.round(insight.confidence * 100)}% conf
              </span>
            )}
            <div>
              <span style={{ fontFamily: C.ui, fontSize: 13, fontWeight: 600, color: C.text1, lineHeight: 1.3 }}>
                {insight.title}
              </span>
              {!open && insight.explanation && (
                <div style={{ fontFamily: C.ui, fontSize: 11, color: C.text3,
                  marginTop: 3, lineHeight: 1.5,
                  overflow: 'hidden', display: '-webkit-box',
                  WebkitLineClamp: 1, WebkitBoxOrient: 'vertical' }}>
                  {insight.explanation.split(/\. /)[0]}.
                </div>
              )}
            </div>
          </div>
        </div>
        <span style={{ color: C.text3, flexShrink: 0, marginTop: 2 }}>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {/* Body */}
      {open && (
        <div style={{ padding: '0 14px 14px', borderTop: `1px solid ${meta.border}` }}>
          {insight.signals?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, margin: '12px 0 8px' }}>
              {insight.signals.map(s => (
                <span key={s} style={{ fontFamily: C.mono, fontSize: 9, color: C.text2,
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
                  padding: '2px 7px', borderRadius: 3 }}>
                  {s}
                </span>
              ))}
            </div>
          )}
          <p style={{ fontFamily: C.ui, fontSize: 13, color: C.text2,
            lineHeight: 1.7, margin: '8px 0 10px' }}>
            {insight.explanation}
          </p>
          {insight.recommendation && (
            <div style={{ background: 'rgba(0,0,0,0.25)', borderRadius: 6,
              padding: '10px 12px', borderLeft: `3px solid ${C.teal}` }}>
              <div style={{ fontFamily: C.mono, fontSize: 9, color: C.teal,
                letterSpacing: '0.1em', marginBottom: 6 }}>
                RECOMMENDED ACTIONS
              </div>
              <pre style={{ fontFamily: C.ui, fontSize: 12, color: C.text2,
                margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                {insight.recommendation}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function InsightExplainer() {
  const [insights, setInsights]     = useState([]);
  const [meta, setMeta]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [lastAt, setLastAt]         = useState(null);
  const mountedRef                  = useRef(true);
  const timerRef                    = useRef(null);

  const load = useCallback(async () => {
    try {
      const data = await apiService.getInsightExplanations();
      if (!mountedRef.current) return;
      setInsights(data.insights || []);
      setMeta({
        analysedAlerts:  data.analysed_alerts,
        analysedActions: data.analysed_actions,
        windowHours:     data.window_hours,
        generatedAt:     data.generated_at,
      });
      setError(null);
      setLastAt(Date.now());
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e?.response?.data?.detail || e?.message || 'Failed to load insights');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    timerRef.current = setInterval(load, 30000);
    return () => { mountedRef.current = false; clearInterval(timerRef.current); };
  }, [load]);

  const critCount = insights.filter(i => i.severity === 'critical').length;
  const warnCount = insights.filter(i => i.severity === 'warning').length;

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12, padding: 22 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
        <Brain size={16} color={C.teal} />
        <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
          AI ROOT CAUSE ANALYSIS
        </span>
        {!loading && meta && (
          <span style={{ marginLeft: 'auto', fontFamily: C.mono, fontSize: 9, color: C.text3 }}>
            {meta.analysedAlerts} alerts · {meta.analysedActions} actions · last {meta.windowHours}h
          </span>
        )}
        {!loading && (
          <button onClick={load} style={{ background: 'none', border: 'none',
            cursor: 'pointer', padding: 4, color: C.text3 }} title="Refresh">
            <RefreshCw size={12} />
          </button>
        )}
      </div>

      {/* Summary badges */}
      {!loading && !error && insights.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {critCount > 0 && (
            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.red,
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
              padding: '3px 10px', borderRadius: 20 }}>
              {critCount} critical
            </span>
          )}
          {warnCount > 0 && (
            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.amber,
              background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)',
              padding: '3px 10px', borderRadius: 20 }}>
              {warnCount} warning
            </span>
          )}
        </div>
      )}

      {/* States */}
      {loading && (
        <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3, padding: '20px 0', textAlign: 'center' }}>
          ANALYSING…
        </div>
      )}

      {!loading && error && (
        <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red, textAlign: 'center', padding: '20px 0' }}>
          {error}
        </div>
      )}

      {!loading && !error && insights.length === 0 && (
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.green }}>
            ✓ NO ANOMALOUS PATTERNS DETECTED
          </div>
          <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 6 }}>
            System is operating within normal parameters over the last {meta?.windowHours}h
          </div>
        </div>
      )}

      {/* Insight cards — sorted: critical first, then by confidence desc */}
      {!loading && !error && [...insights].sort((a, b) => {
        const SEV = { critical: 0, warning: 1, info: 2 };
        const sd = (SEV[a.severity] ?? 2) - (SEV[b.severity] ?? 2);
        return sd !== 0 ? sd : (b.confidence ?? 0) - (a.confidence ?? 0);
      }).map((ins, i) => (
        <InsightCard
          key={ins.type + i}
          insight={ins}
          defaultOpen={i === 0 && ins.severity === 'critical'}
        />
      ))}

      {lastAt && (
        <div style={{ fontFamily: C.mono, fontSize: 9, color: C.text3, textAlign: 'right', marginTop: 4 }}>
          updated {new Date(lastAt).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
