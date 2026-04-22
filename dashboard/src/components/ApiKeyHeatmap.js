import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { AlertTriangle, Key, RefreshCw } from 'lucide-react';

const C = {
  bg: 'rgb(22,20,16)', surface: 'rgb(31,29,24)', border: 'rgba(42,40,32,0.9)',
  amber: '#F59E0B', teal: '#2DD4BF', red: '#F87171',
  text1: 'rgb(245,240,232)', text2: 'rgb(168,159,140)', text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace", ui: "'Outfit', sans-serif",
};

const HOURS = Array.from({ length: 24 }, (_, i) => i);

function cellColor(req, maxReq, errRate) {
  if (!req) return 'rgba(42,40,32,0.3)';
  const intensity = Math.min(1, req / (maxReq || 1));
  if (errRate > 5) {
    const r = Math.round(248 * intensity);
    return `rgba(${r},${Math.round(113 * (1 - intensity * 0.4))},${Math.round(113 * (1 - intensity * 0.4))},${0.2 + intensity * 0.6})`;
  }
  const t = C.teal;
  return `rgba(45,212,191,${0.1 + intensity * 0.75})`;
}

function Tooltip({ data, x, y }) {
  if (!data) return null;
  return (
    <div style={{
      position: 'fixed', left: x + 12, top: y - 10, zIndex: 9999,
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 8, padding: '10px 14px', minWidth: 160,
      boxShadow: '0 8px 24px rgba(0,0,0,0.5)', pointerEvents: 'none',
    }}>
      <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text1, marginBottom: 5 }}>
        {data.key_label} — {data.hour.toString().padStart(2,'0')}:00
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Row label="Requests"   value={data.requests} />
        <Row label="Errors"     value={data.errors}   color={data.error_rate > 5 ? C.red : C.text2} />
        <Row label="Error rate" value={`${data.error_rate?.toFixed(1)}%`} color={data.error_rate > 5 ? C.red : C.text2} />
        <Row label="P95 lat."   value={data.p95_ms ? `${data.p95_ms}ms` : '—'} />
      </div>
    </div>
  );
}

function Row({ label, value, color }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
      <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>{label}</span>
      <span style={{ fontFamily: C.mono, fontSize: 9, color: color || C.text2 }}>{value ?? '—'}</span>
    </div>
  );
}

function Skeleton() {
  return (
    <div style={{ padding: 18 }}>
      <div style={{ height: 120, borderRadius: 8, background: 'rgba(42,40,32,0.4)',
        animation: 'pulse 1.5s ease-in-out infinite' }} />
    </div>
  );
}

export default function ApiKeyHeatmap({ hours = 24 }) {
  const [data, setData]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [tooltip, setTooltip]   = useState({ data: null, x: 0, y: 0 });
  const [selected, setSelected] = useState(null);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const res = await apiService.getApiKeyUsageHeatmap(hours);
      if (!mountedRef.current) return;
      setData(Array.isArray(res) ? res : res?.keys || res?.data || []);
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      const status = e?.response?.status;
      setError(status === 404 || status === 501 ? 'pending' : e?.response?.data?.detail || e?.message || 'Load failed');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    mountedRef.current = true;
    load();
    return () => { mountedRef.current = false; };
  }, [load]);

  // Compute max requests across all cells for colour scaling
  const maxReq = data.reduce((m, row) =>
    Math.max(m, ...(row.hours || HOURS).map(h => (row.data?.[h]?.requests || row[h]?.requests || 0))), 1);

  const getCellData = (row, h) => {
    const cell = row.data?.[h] || row[h] || {};
    return {
      key_label:  row.key_label || row.name || row.key_id || 'key',
      hour:       h,
      requests:   cell.requests ?? 0,
      errors:     cell.errors   ?? 0,
      error_rate: cell.error_rate ?? (cell.errors && cell.requests ? (cell.errors / cell.requests) * 100 : 0),
      p95_ms:     cell.p95_ms,
    };
  };

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
      boxShadow: '0 4px 24px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 18px', borderBottom: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', gap: 10 }}>
        <Key size={15} color={C.amber} />
        <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
          API KEY USAGE (LAST {hours}H)
        </span>
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
            <code style={{ color: C.text2 }}>GET /api/v1/api-keys/usage-heatmap?hours={hours}</code>
            <br />not yet implemented — see MISSING_ENDPOINTS.md
          </div>
        </div>
      ) : error ? (
        <div style={{ padding: '28px 18px', textAlign: 'center' }}>
          <AlertTriangle size={18} color={C.red} style={{ marginBottom: 8 }} />
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red }}>{error}</div>
        </div>
      ) : data.length === 0 ? (
        <div style={{ padding: '28px 18px', textAlign: 'center' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>NO API KEY DATA</div>
        </div>
      ) : (
        <div style={{ padding: 18, overflowX: 'auto' }}>
          {/* Hour axis labels */}
          <div style={{ display: 'flex', paddingLeft: 110, marginBottom: 4 }}>
            {HOURS.filter(h => h % 3 === 0).map(h => (
              <div key={h} style={{ flex: h === 0 ? 1 : 3, fontFamily: C.mono, fontSize: 9, color: C.text3,
                textAlign: h === 0 ? 'left' : 'center' }}>
                {h.toString().padStart(2,'0')}h
              </div>
            ))}
          </div>

          {/* Grid */}
          {data.map((row, ri) => {
            const isSel = selected === ri;
            return (
              <div key={ri} style={{ display: 'flex', alignItems: 'center', marginBottom: 3 }}>
                {/* Key label */}
                <div
                  onClick={() => setSelected(isSel ? null : ri)}
                  style={{ width: 100, paddingRight: 10, fontFamily: C.mono, fontSize: 10,
                    color: isSel ? C.amber : C.text2, overflow: 'hidden', textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap', cursor: 'pointer', flexShrink: 0 }}>
                  {row.key_label || row.name || `key-${ri + 1}`}
                </div>
                {/* Cells */}
                <div style={{ display: 'flex', gap: 2, flex: 1 }}>
                  {HOURS.map(h => {
                    const cell = getCellData(row, h);
                    const isHighErr = cell.error_rate > 5;
                    return (
                      <div
                        key={h}
                        onMouseMove={e => setTooltip({ data: cell, x: e.clientX, y: e.clientY })}
                        onMouseLeave={() => setTooltip({ data: null, x: 0, y: 0 })}
                        style={{
                          flex: 1, height: 18, borderRadius: 2,
                          background: cellColor(cell.requests, maxReq, cell.error_rate),
                          border: isHighErr ? `1px solid ${C.red}60` : '1px solid transparent',
                          cursor: 'default',
                        }}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* Legend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 12 }}>
            <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>Volume:</span>
            {[0.1, 0.3, 0.6, 1.0].map(i => (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 14, height: 14, borderRadius: 2, display: 'inline-block',
                  background: `rgba(45,212,191,${i})` }} />
                <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>
                  {i === 0.1 ? 'low' : i === 1.0 ? 'high' : ''}
                </span>
              </span>
            ))}
            <span style={{ marginLeft: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 14, height: 14, borderRadius: 2, display: 'inline-block',
                background: C.red, opacity: 0.6 }} />
              <span style={{ fontFamily: C.mono, fontSize: 9, color: C.red }}>&gt;5% err</span>
            </span>
          </div>
        </div>
      )}

      <Tooltip {...tooltip} />
    </div>
  );
}
