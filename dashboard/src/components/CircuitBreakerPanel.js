import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { AlertTriangle, RefreshCw, Shield, RotateCcw } from 'lucide-react';

const C = {
  bg: 'rgb(22,20,16)', surface: 'rgb(31,29,24)', border: 'rgba(42,40,32,0.9)',
  amber: '#F59E0B', teal: '#2DD4BF', red: '#F87171', green: '#4ADE80',
  text1: 'rgb(245,240,232)', text2: 'rgb(168,159,140)', text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace", ui: "'Outfit', sans-serif",
};

const STATE_META = {
  CLOSED:    { color: C.green,  bg: 'rgba(74,222,128,0.1)',  label: 'CLOSED',    desc: 'Normal — requests flowing'  },
  OPEN:      { color: C.red,    bg: 'rgba(248,113,113,0.1)', label: 'OPEN',      desc: 'Tripped — requests blocked' },
  HALF_OPEN: { color: C.amber,  bg: 'rgba(245,158,11,0.1)',  label: 'HALF-OPEN', desc: 'Testing — probe requests'   },
};

function fmtAgo(iso) {
  if (!iso) return '—';
  const d = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (d < 60)   return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  return `${Math.floor(d / 3600)}h ago`;
}

function Skeleton() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10, padding: 18 }}>
      {[1,2,3,4,5].map(i => (
        <div key={i} style={{ height: 100, borderRadius: 8, background: 'rgba(42,40,32,0.4)',
          animation: 'pulse 1.5s ease-in-out infinite' }} />
      ))}
    </div>
  );
}

function BreakerCard({ cb, onReset, resetting }) {
  const meta = STATE_META[cb.state] || STATE_META.CLOSED;
  return (
    <div style={{ padding: 14, borderRadius: 8, background: meta.bg,
      border: `1px solid ${meta.color}30`, position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
        <div>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text1, marginBottom: 3 }}>
            {cb.component || cb.name}
          </div>
          <div style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>
            {cb.service || ''}
          </div>
        </div>
        <span style={{ fontFamily: C.mono, fontSize: 9, padding: '2px 7px', borderRadius: 10,
          background: meta.bg, color: meta.color, border: `1px solid ${meta.color}40`,
          letterSpacing: '0.08em' }}>
          {meta.label}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px 12px', marginBottom: 10 }}>
        <Stat label="Failures" value={cb.failure_count ?? '—'} warn={cb.failure_count > 3} />
        <Stat label="Threshold" value={cb.threshold ?? '—'} />
        <Stat label="Tripped" value={fmtAgo(cb.opened_at)} color={cb.state === 'OPEN' ? C.red : C.text2} />
        <Stat label="Timeout" value={cb.timeout_ms ? `${cb.timeout_ms}ms` : '—'} />
      </div>

      <div style={{ fontFamily: C.ui, fontSize: 11, color: C.text3, marginBottom: cb.state !== 'CLOSED' ? 10 : 0 }}>
        {meta.desc}
      </div>

      {cb.state !== 'CLOSED' && (
        <button
          onClick={() => onReset(cb.component || cb.name)}
          disabled={resetting}
          style={{ width: '100%', padding: '6px 0', borderRadius: 6,
            background: resetting ? 'rgba(42,40,32,0.4)' : 'rgba(245,158,11,0.12)',
            border: `1px solid ${C.amber}40`, color: resetting ? C.text3 : C.amber,
            fontFamily: C.mono, fontSize: 10, cursor: resetting ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
            letterSpacing: '0.06em' }}>
          <RotateCcw size={11} />
          {resetting ? 'RESETTING…' : 'RESET'}
        </button>
      )}
    </div>
  );
}

function Stat({ label, value, color, warn }) {
  return (
    <div>
      <div style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>{label}</div>
      <div style={{ fontFamily: C.mono, fontSize: 12, color: warn ? C.red : color || C.text2 }}>
        {value}
      </div>
    </div>
  );
}

export default function CircuitBreakerPanel() {
  const [breakers, setBreakers]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [resetting, setResetting] = useState({});
  const [toast, setToast]         = useState(null);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const data = await apiService.getCircuitBreakerStatus();
      if (!mountedRef.current) return;
      setBreakers(Array.isArray(data) ? data : data?.breakers || data?.circuit_breakers || []);
      setError(null);
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
    const t = setInterval(load, 10000);
    return () => { mountedRef.current = false; clearInterval(t); };
  }, [load]);

  const handleReset = useCallback(async (component) => {
    setResetting(r => ({ ...r, [component]: true }));
    try {
      await apiService.resetCircuitBreaker(component);
      setToast({ msg: `${component} reset`, ok: true });
      await load();
    } catch (e) {
      setToast({ msg: e?.response?.data?.detail || 'Reset failed', ok: false });
    } finally {
      setResetting(r => ({ ...r, [component]: false }));
      setTimeout(() => setToast(null), 3000);
    }
  }, [load]);

  const openCount = breakers.filter(b => b.state === 'OPEN').length;

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
      boxShadow: '0 4px 24px rgba(0,0,0,0.3)', overflow: 'hidden', position: 'relative' }}>
      {/* Toast */}
      {toast && (
        <div style={{ position: 'absolute', top: 14, right: 14, zIndex: 100,
          padding: '8px 14px', borderRadius: 8,
          background: toast.ok ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
          border: `1px solid ${toast.ok ? C.green : C.red}40`,
          fontFamily: C.mono, fontSize: 11, color: toast.ok ? C.green : C.red }}>
          {toast.msg}
        </div>
      )}

      <div style={{ padding: '16px 18px', borderBottom: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', gap: 10 }}>
        <Shield size={15} color={openCount > 0 ? C.red : C.amber} />
        <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
          CIRCUIT BREAKERS
        </span>
        {openCount > 0 && (
          <span style={{ fontFamily: C.mono, fontSize: 10, padding: '2px 8px', borderRadius: 8,
            background: 'rgba(248,113,113,0.15)', color: C.red, border: `1px solid ${C.red}30` }}>
            {openCount} TRIPPED
          </span>
        )}
        <button onClick={load} style={{ marginLeft: 'auto', background: 'none', border: 'none',
          cursor: 'pointer', color: C.text3, display: 'flex', alignItems: 'center' }}>
          <RefreshCw size={13} />
        </button>
      </div>

      {loading ? (
        <Skeleton />
      ) : error === 'pending' ? (
        <div style={{ padding: '32px 18px', textAlign: 'center' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.amber }}>ENDPOINT PENDING</div>
          <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 6 }}>
            <code style={{ color: C.text2 }}>GET /api/v1/remediation/circuit-breaker/status</code>
            <br />not yet implemented — see MISSING_ENDPOINTS.md
          </div>
        </div>
      ) : error ? (
        <div style={{ padding: '28px 18px', textAlign: 'center' }}>
          <AlertTriangle size={18} color={C.red} style={{ marginBottom: 8 }} />
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red }}>{error}</div>
        </div>
      ) : breakers.length === 0 ? (
        <div style={{ padding: '28px 18px', textAlign: 'center' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>NO CIRCUIT BREAKERS CONFIGURED</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px,1fr))', gap: 10, padding: 18 }}>
          {breakers.map((cb, i) => (
            <BreakerCard
              key={cb.component || cb.name || i}
              cb={cb}
              onReset={handleReset}
              resetting={!!resetting[cb.component || cb.name]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
