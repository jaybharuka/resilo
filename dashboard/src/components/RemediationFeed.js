import React, { useState, useEffect, useRef, useCallback } from 'react';
import { apiService } from '../services/api';
import { Zap, CheckCircle, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';

const C = {
  bg: 'rgb(22,20,16)', surface: 'rgb(31,29,24)', border: 'rgba(42,40,32,0.9)',
  amber: '#F59E0B', teal: '#2DD4BF', red: '#F87171', green: '#4ADE80',
  text1: 'rgb(245,240,232)', text2: 'rgb(168,159,140)', text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace", ui: "'Outfit', sans-serif",
};

const OUTCOME_META = {
  success:  { color: C.green,  bg: 'rgba(74,222,128,0.1)',   label: 'SUCCESS'  },
  failed:   { color: C.red,    bg: 'rgba(248,113,113,0.1)',  label: 'FAILED'   },
  dry_run:  { color: '#94A3B8', bg: 'rgba(148,163,184,0.1)', label: 'DRY RUN'  },
  running:  { color: C.amber,  bg: 'rgba(245,158,11,0.1)',   label: 'RUNNING'  },
  pending:  { color: C.text3,  bg: 'rgba(107,99,87,0.1)',    label: 'PENDING'  },
};

const ACTION_META = {
  scale_up:   { color: C.teal,  label: 'SCALE UP'   },
  scale_down: { color: C.amber, label: 'SCALE DOWN' },
  restart:    { color: C.amber, label: 'RESTART'    },
  optimize:   { color: C.teal,  label: 'OPTIMIZE'   },
  rollback:   { color: C.red,   label: 'ROLLBACK'   },
};

function fmt(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function normalise(item) {
  return {
    id:        item.id || item.job_id || String(Math.random()),
    ts:        item.executed_at || item.started_at || item.created_at || item.timestamp,
    component: item.component || item.agent_id || item.service || 'unknown',
    action:    item.action || item.action_type || 'unknown',
    trigger:   item.trigger_metric || item.trigger || '',
    triggerVal:item.trigger_value  ?? item.metric_value ?? null,
    outcome:   item.outcome || item.status || 'pending',
    details:   item,
  };
}

function Skeleton() {
  return (
    <div style={{ padding: '12px 18px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      {[1,2,3].map(i => (
        <div key={i} style={{ height: 52, borderRadius: 8, background: 'rgba(42,40,32,0.4)',
          animation: 'pulse 1.5s ease-in-out infinite', opacity: 0.6 }} />
      ))}
    </div>
  );
}

function _effectivenessCalc(before, after) {
  if (!before && !after) return null;
  const deltas = ['cpu', 'memory', 'disk'].flatMap(m => {
    const b = before?.[m], a = after?.[m];
    if (b == null || a == null || b === 0) return [];
    return [{ m, delta: ((b - a) / b * 100) }];
  });
  if (deltas.length === 0) return null;
  const avg = deltas.reduce((s, d) => s + d.delta, 0) / deltas.length;
  return { avg, deltas };
}

function EffectivenessBadge({ before, after }) {
  const r = _effectivenessCalc(before, after);
  if (!r) return null;
  const { avg, deltas } = r;
  const color = avg >= 20 ? C.green : avg >= 5 ? C.amber : avg >= -5 ? C.text3 : C.red;
  const label = avg >= 20 ? `↓ ${avg.toFixed(0)}% avg` : avg >= 5 ? `↓ ${avg.toFixed(0)}%` : avg >= -5 ? 'FLAT' : `↑ ${Math.abs(avg).toFixed(0)}%`;
  return (
    <span style={{ fontFamily: C.mono, fontSize: 9, color, background: `${color}15`,
      border: `1px solid ${color}30`, padding: '2px 6px', borderRadius: 3,
      flexShrink: 0 }} title={`Before→After: ${deltas.map(d => `${d.m}: ${d.delta.toFixed(1)}%`).join(', ')}`}>
      {label}
    </span>
  );
}

function EffectivenessHero({ before, after }) {
  const r = _effectivenessCalc(before, after);
  if (!r || Math.abs(r.avg) < 5) return null;
  const { avg } = r;
  const improved = avg > 0;
  const color = improved ? C.green : C.red;
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, flexShrink: 0 }}>
      <span style={{ fontFamily: C.mono, fontSize: 20, fontWeight: 700,
        color, lineHeight: 1, letterSpacing: '-0.02em' }}>
        {improved ? '↓' : '↑'} {Math.abs(avg).toFixed(0)}%
      </span>
      <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>avg</span>
    </div>
  );
}

function FeedRow({ item }) {
  const [open, setOpen] = useState(false);
  const om = OUTCOME_META[item.outcome] || OUTCOME_META.pending;
  const am = ACTION_META[item.action.toLowerCase()] || { color: C.amber, label: item.action.toUpperCase() };
  const before = item.details?.before_metrics;
  const after  = item.details?.after_metrics;

  return (
    <div
      style={{ borderBottom: `1px solid ${C.border}`, cursor: 'pointer', transition: 'background 0.15s' }}
      onClick={() => setOpen(o => !o)}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(42,40,32,0.4)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 18px' }}>
        <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, minWidth: 70 }}>{fmt(item.ts)}</span>
        <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text2, flex: 1, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.component}
        </span>
        <span style={{ fontFamily: C.mono, fontSize: 10, color: am.color, padding: '2px 7px',
          borderRadius: 4, background: `${am.color}18`, letterSpacing: '0.06em', flexShrink: 0 }}>
          {am.label}
        </span>
        {item.triggerVal != null && (
          <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, flexShrink: 0 }}>
            {item.trigger && `${item.trigger}:`}{item.triggerVal}
            {typeof item.triggerVal === 'number' && item.trigger?.includes('usage') ? '%' : ''}
          </span>
        )}
        <EffectivenessBadge before={before} after={after} />
        <span style={{ fontFamily: C.mono, fontSize: 10, color: om.color, padding: '2px 7px',
          borderRadius: 4, background: om.bg, letterSpacing: '0.06em', flexShrink: 0 }}>
          {om.label}
        </span>
        {open ? <ChevronUp size={12} color={C.text3} /> : <ChevronDown size={12} color={C.text3} />}
      </div>
      {open && (
        <div style={{ margin: '0 18px 12px' }}>
          {(before || after) && (() => {
            const metrics = ['cpu', 'memory', 'disk'];
            return (
              <div style={{ marginBottom: 8 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 6 }}>
                  {[['BEFORE', before], ['AFTER', after]].map(([label, snap]) => (
                    <div key={label} style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 6,
                      padding: '8px 10px', border: `1px solid ${C.border}` }}>
                      <div style={{ fontFamily: C.mono, fontSize: 9, color: C.text3,
                        letterSpacing: '0.1em', marginBottom: 6 }}>{label}</div>
                      {snap ? (metrics.map(m => snap[m] != null && (
                        <div key={m} style={{ marginBottom: 5 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between',
                            fontFamily: C.mono, fontSize: 10, color: C.text2, marginBottom: 2 }}>
                            <span style={{ color: C.text3 }}>{m.toUpperCase()}</span>
                            <span style={{ color: snap[m] > 85 ? C.red : snap[m] > 70 ? C.amber : C.green }}>
                              {parseFloat(snap[m]).toFixed(1)}%
                            </span>
                          </div>
                          <div style={{ height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.06)' }}>
                            <div style={{ height: '100%', borderRadius: 2, width: `${Math.min(100, snap[m])}%`,
                              background: snap[m] > 85 ? C.red : snap[m] > 70 ? C.amber : C.green,
                              transition: 'width 0.4s ease' }} />
                          </div>
                        </div>
                      ))) : <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>—</span>}
                    </div>
                  ))}
                </div>
                <EffectivenessHero before={before} after={after} />
              </div>
            );
          })()}
          <pre style={{ padding: 10, borderRadius: 6, background: C.surface,
            fontFamily: C.mono, fontSize: 10, color: C.text2, overflowX: 'auto',
            border: `1px solid ${C.border}`, lineHeight: 1.6, margin: 0 }}>
            {JSON.stringify(item.details, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export default function RemediationFeed({ maxHeight = 340 }) {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [lastAt, setLastAt]   = useState(null);
  const [stale, setStale]     = useState(false);
  const timerRef              = useRef(null);
  const mountedRef            = useRef(true);

  const applyRaw = useCallback((raw) => {
    if (!mountedRef.current) return;
    const list = Array.isArray(raw) ? raw : raw?.items || raw?.actions || [];
    if (!Array.isArray(list)) throw new Error('Invalid remediation data: expected array');
    const normalised = list.map(normalise).sort((a, b) => new Date(b.ts) - new Date(a.ts));
    setItems(normalised);
    setError(null);
    setLastAt(Date.now());
    setStale(false);
    setLoading(false);
  }, []);

  const poll = useCallback(async () => {
    try {
      const raw = await apiService.getRemediationActions(20);
      applyRaw(raw);
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e?.response?.data?.detail || e?.message || 'Failed to load feed');
      setLoading(false);
    }
  }, [applyRaw]);

  useEffect(() => {
    mountedRef.current = true;
    let es = null;
    let sseOk = false;

    // Initial HTTP fetch immediately
    poll();

    // Obtain a short-lived (60s) stream token then open SSE.
    // This avoids passing the long-lived access token as a URL query param
    // where it would appear in server logs and browser history.
    const openSSE = async () => {
      try {
        const res = await fetch('/stream/token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('aiops:token') || ''}`,
          },
        });
        if (!res.ok) throw new Error(`stream/token ${res.status}`);
        const { token: streamToken } = await res.json();
        if (!mountedRef.current) return;

        const base = window.location.origin;
        es = new EventSource(`${base}/api/v1/remediation/actions/stream?token=${encodeURIComponent(streamToken)}`);

        es.addEventListener('remediation_action', (evt) => {
          try {
            const item = normalise(JSON.parse(evt.data));
            if (!mountedRef.current) return;
            setItems(prev => {
              const updated = [item, ...prev.filter(i => i.id !== item.id)];
              return updated.length > 50 ? updated.slice(0, 50) : updated;
            });
            setLastAt(Date.now());
            setStale(false);
            sseOk = true;
          } catch {}
        });

        es.onerror = () => {
          if (es) { es.close(); es = null; }
          sseOk = false;
        };
      } catch {
        // stream/token failed or EventSource not supported — polling handles it
      }
    };

    openSSE();

    // Polling fallback: runs every 5s; skipped if SSE is delivering events
    timerRef.current = setInterval(() => {
      if (!sseOk) poll();
    }, 5000);

    return () => {
      mountedRef.current = false;
      clearInterval(timerRef.current);
      timerRef.current = null;
      if (es) { es.close(); }
    };
  }, [poll]);

  // Staleness indicator
  useEffect(() => {
    const t = setInterval(() => {
      if (lastAt) setStale(Date.now() - lastAt > 30000);
    }, 5000);
    return () => clearInterval(t);
  }, [lastAt]);

  const secAgo = lastAt ? Math.round((Date.now() - lastAt) / 1000) : null;

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
      boxShadow: '0 4px 24px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '16px 18px', borderBottom: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', gap: 10 }}>
        <Zap size={15} color={C.amber} />
        <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
          LIVE REMEDIATION FEED
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          {secAgo != null && (
            <span style={{ fontFamily: C.mono, fontSize: 10,
              color: stale ? C.red : secAgo > 20 ? C.amber : C.text3 }}>
              {secAgo}s ago
            </span>
          )}
          <span style={{ width: 6, height: 6, borderRadius: '50%',
            background: error ? C.red : C.teal,
            boxShadow: error ? 'none' : `0 0 6px ${C.teal}80`,
            animation: !error ? 'pulse 2s infinite' : 'none' }} />
        </span>
      </div>

      {/* Body */}
      <div style={{ maxHeight, overflowY: 'auto' }}>
        {loading ? (
          <Skeleton />
        ) : error ? (
          <div style={{ padding: '32px 18px', textAlign: 'center' }}>
            <AlertTriangle size={20} color={C.red} style={{ marginBottom: 8 }} />
            <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red }}>{error}</div>
            <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 4 }}>
              Check that the remediation service is running
            </div>
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding: '32px 18px', textAlign: 'center' }}>
            <CheckCircle size={20} color={C.teal} style={{ marginBottom: 8 }} />
            <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>NO ACTIONS YET</div>
            <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 4 }}>
              Remediation events will appear here as they fire
            </div>
          </div>
        ) : (
          items.map((item, i) => (
            <div key={item.id} style={{ animation: 'fadeIn 0.3s ease both', animationDelay: `${i * 20}ms` }}>
              <FeedRow item={item} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
