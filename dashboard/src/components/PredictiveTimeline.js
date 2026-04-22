import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { AlertTriangle, Info, RefreshCw, TrendingUp } from 'lucide-react';

const C = {
  bg: 'rgb(22,20,16)', surface: 'rgb(31,29,24)', border: 'rgba(42,40,32,0.9)',
  amber: '#F59E0B', teal: '#2DD4BF', red: '#F87171', blue: '#60A5FA',
  text1: 'rgb(245,240,232)', text2: 'rgb(168,159,140)', text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace", ui: "'Outfit', sans-serif",
};

const SEV_META = {
  critical: { color: C.red,   label: 'CRIT' },
  warning:  { color: C.amber, label: 'WARN' },
  info:     { color: C.blue,  label: 'INFO' },
};

function fmtHHMM(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return ''; }
}

function Skeleton() {
  return (
    <div style={{ padding: '24px 18px' }}>
      <div style={{ height: 80, borderRadius: 8, background: 'rgba(42,40,32,0.4)',
        animation: 'pulse 1.5s ease-in-out infinite' }} />
    </div>
  );
}

export default function PredictiveTimeline() {
  const [alerts, setAlerts]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [why, setWhy]           = useState(null);
  const [lastAt, setLastAt]     = useState(null);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const data = await apiService.getPredictedAlerts();
      if (!mountedRef.current) return;
      setAlerts(Array.isArray(data) ? data : data?.predictions || data?.alerts || []);
      setError(null);
      setLastAt(Date.now());
    } catch (e) {
      if (!mountedRef.current) return;
      const status = e?.response?.status;
      setError(status === 404 || status === 501 ? 'pending' : e?.response?.data?.detail || e?.message || 'Load failed');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    const t = setInterval(load, 60000);
    return () => { mountedRef.current = false; clearInterval(t); };
  }, [load]);

  const now = Date.now();
  const twoHours = now + 2 * 3600 * 1000;

  // Place dots on a 0–100% scale within the next 2 hours
  function pct(isoTs) {
    const t = new Date(isoTs).getTime();
    return Math.max(0, Math.min(100, ((t - now) / (twoHours - now)) * 100));
  }

  const secAgo = lastAt ? Math.round((Date.now() - lastAt) / 1000) : null;

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
      boxShadow: '0 4px 24px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 18px', borderBottom: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', gap: 10 }}>
        <TrendingUp size={15} color={C.amber} />
        <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
          PREDICTIVE ALERT TIMELINE (NEXT 2H)
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {secAgo != null && (
            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>{secAgo}s ago</span>
          )}
          <button onClick={load} style={{ background: 'none', border: 'none', cursor: 'pointer',
            color: C.text3, display: 'flex', alignItems: 'center' }}>
            <RefreshCw size={13} />
          </button>
        </span>
      </div>

      {loading ? (
        <Skeleton />
      ) : error === 'pending' ? (
        <div style={{ padding: '32px 18px', textAlign: 'center' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.amber }}>ENDPOINT PENDING</div>
          <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 6 }}>
            <code style={{ color: C.text2 }}>GET /api/v1/predictions/upcoming</code>
            <br />not yet implemented — see MISSING_ENDPOINTS.md
          </div>
        </div>
      ) : error ? (
        <div style={{ padding: '28px 18px', textAlign: 'center' }}>
          <AlertTriangle size={18} color={C.red} style={{ marginBottom: 8 }} />
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red }}>{error}</div>
        </div>
      ) : (
        <div style={{ padding: '20px 18px' }}>
          {/* Timeline track */}
          <div style={{ position: 'relative', height: 56, marginBottom: 8 }}>
            {/* Track */}
            <div style={{ position: 'absolute', top: 20, left: 0, right: 0, height: 2,
              background: C.border, borderRadius: 1 }} />
            {/* Now marker */}
            <div style={{ position: 'absolute', top: 10, left: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', transform: 'translateX(-50%)' }}>
              <div style={{ width: 1, height: 22, background: C.teal }} />
              <span style={{ fontFamily: C.mono, fontSize: 9, color: C.teal, marginTop: 2 }}>NOW</span>
            </div>
            {/* +2h marker */}
            <div style={{ position: 'absolute', top: 10, right: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', transform: 'translateX(50%)' }}>
              <div style={{ width: 1, height: 22, background: C.text3 }} />
              <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3, marginTop: 2 }}>+2H</span>
            </div>
            {/* Alert dots */}
            {alerts.map((a, i) => {
              const p = pct(a.predicted_at || a.timestamp);
              const sev = SEV_META[a.severity || a.level || 'info'] || SEV_META.info;
              const conf = a.confidence ?? 1;
              const isWhy = why === i;
              return (
                <div key={i} style={{ position: 'absolute', left: `${p}%`, top: 10,
                  transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column',
                  alignItems: 'center', gap: 2 }}>
                  <button
                    onClick={() => setWhy(isWhy ? null : i)}
                    style={{ width: 14, height: 14, borderRadius: '50%',
                      background: sev.color, opacity: 0.3 + conf * 0.7,
                      border: isWhy ? `2px solid ${sev.color}` : 'none',
                      cursor: 'pointer', padding: 0,
                      boxShadow: isWhy ? `0 0 8px ${sev.color}80` : 'none' }}
                    title={`${sev.label} — ${Math.round(conf * 100)}% confidence`}
                  />
                  <span style={{ fontFamily: C.mono, fontSize: 8, color: sev.color,
                    opacity: 0.5 + conf * 0.5 }}>
                    {fmtHHMM(a.predicted_at || a.timestamp)}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Why panel */}
          {why !== null && alerts[why] && (
            <div style={{ marginTop: 10, padding: '10px 14px', borderRadius: 8, background: C.surface,
              border: `1px solid ${C.border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Info size={13} color={C.amber} />
                <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text1 }}>
                  {alerts[why].name || alerts[why].metric || 'Predicted alert'}
                </span>
                <span style={{ marginLeft: 'auto', fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
                  {Math.round((alerts[why].confidence ?? 1) * 100)}% confidence
                </span>
              </div>
              {alerts[why].spike_detected && (
                <div style={{ fontFamily: C.mono, fontSize: 10, color: '#EF4444',
                  background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
                  borderRadius: 3, padding: '3px 8px', marginBottom: 6, display: 'inline-block' }}>
                  ⚡ SPIKE DETECTED
                </div>
              )}
              <p style={{ fontFamily: C.ui, fontSize: 12, color: C.text2, margin: 0, lineHeight: 1.6 }}>
                {alerts[why].reason || alerts[why].explanation || 'No explanation available from the ML platform.'}
              </p>
              {alerts[why].variance != null && (
                <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 4 }}>
                  Signal variance: {alerts[why].variance.toFixed(1)} — {alerts[why].variance > 25 ? '⚠ noisy' : '✓ stable'}
                </div>
              )}
              {alerts[why].contributing_signals?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginBottom: 4 }}>
                    CONTRIBUTING SIGNALS
                  </div>
                  {alerts[why].contributing_signals.map((s, si) => (
                    <div key={si} style={{ fontFamily: C.mono, fontSize: 10, color: C.text2,
                      padding: '2px 0', borderBottom: `1px solid ${C.border}` }}>
                      {s}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {alerts.length === 0 && (
            <div style={{ textAlign: 'center', paddingTop: 8 }}>
              <div style={{ fontFamily: C.mono, fontSize: 11, color: C.teal }}>
                NO ALERTS PREDICTED IN NEXT 2H
              </div>
            </div>
          )}

          {/* Legend */}
          <div style={{ display: 'flex', gap: 14, marginTop: 14 }}>
            {Object.entries(SEV_META).map(([key, m]) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: m.color, display: 'inline-block' }} />
                <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>{m.label}</span>
              </div>
            ))}
            <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3, marginLeft: 'auto' }}>
              dot opacity = confidence
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
