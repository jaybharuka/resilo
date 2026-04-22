import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { AlertTriangle, RefreshCw, Users } from 'lucide-react';

const C = {
  bg: 'rgb(22,20,16)', surface: 'rgb(31,29,24)', border: 'rgba(42,40,32,0.9)',
  amber: '#F59E0B', teal: '#2DD4BF', red: '#F87171', green: '#4ADE80',
  text1: 'rgb(245,240,232)', text2: 'rgb(168,159,140)', text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace", ui: "'Outfit', sans-serif",
};

function healthColor(score) {
  if (score == null) return '#3A342D';
  if (score >= 80) return '#4ADE80';
  if (score >= 60) return '#F59E0B';
  if (score >= 40) return '#FB923C';
  return '#F87171';
}

function healthBg(score) {
  const c = healthColor(score);
  return `${c}22`;
}

function fmtTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  const diff = Math.floor((Date.now() - d) / 60000);
  if (diff < 1) return 'just now';
  if (diff < 60) return `${diff}m ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function Tooltip({ tenant, x, y }) {
  if (!tenant) return null;
  return (
    <div style={{
      position: 'fixed', left: x + 12, top: y - 10, zIndex: 9999,
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 8, padding: '10px 14px', minWidth: 180,
      boxShadow: '0 8px 24px rgba(0,0,0,0.5)', pointerEvents: 'none',
    }}>
      <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text1, marginBottom: 6 }}>
        {tenant.org_name || tenant.name}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <Row label="Health" value={`${tenant.health_score ?? '—'}%`} color={healthColor(tenant.health_score)} />
        <Row label="Top issue" value={tenant.top_issue || 'None'} />
        <Row label="Last incident" value={fmtTime(tenant.last_incident_at)} />
        <Row label="Error rate"   value={tenant.error_rate != null ? `${tenant.error_rate.toFixed(1)}%` : '—'} />
        <Row label="P95 latency"  value={tenant.p95_latency_ms != null ? `${tenant.p95_latency_ms}ms` : '—'} />
      </div>
    </div>
  );
}

function Row({ label, value, color }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>{label}</span>
      <span style={{ fontFamily: C.mono, fontSize: 10, color: color || C.text2 }}>{value}</span>
    </div>
  );
}

function Skeleton() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))', gap: 8, padding: 18 }}>
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} style={{ height: 64, borderRadius: 8, background: 'rgba(42,40,32,0.4)',
          animation: 'pulse 1.5s ease-in-out infinite', opacity: 0.6 }} />
      ))}
    </div>
  );
}

export default function TenantHealthHeatmap() {
  const [tenants, setTenants]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [selected, setSelected] = useState(null);
  const [tooltip, setTooltip]   = useState({ tenant: null, x: 0, y: 0 });
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiService.getTenantHealthSummary();
      if (!mountedRef.current) return;
      setTenants(Array.isArray(data) ? data : data?.tenants || []);
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      const status = e?.response?.status;
      if (status === 404 || status === 501) {
        setError('pending');
      } else {
        setError(e?.response?.data?.detail || e?.message || 'Failed to load tenant data');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    return () => { mountedRef.current = false; };
  }, [load]);

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
      boxShadow: '0 4px 24px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 18px', borderBottom: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', gap: 10 }}>
        <Users size={15} color={C.amber} />
        <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>
          TENANT HEALTH HEATMAP
        </span>
        <button onClick={load} style={{ marginLeft: 'auto', background: 'none', border: 'none',
          cursor: 'pointer', color: C.text3, display: 'flex', alignItems: 'center' }}>
          <RefreshCw size={13} />
        </button>
      </div>

      {loading ? (
        <Skeleton />
      ) : error === 'pending' ? (
        <div style={{ padding: '36px 18px', textAlign: 'center' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.amber }}>ENDPOINT PENDING</div>
          <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text3, marginTop: 6 }}>
            <code style={{ color: C.text2 }}>GET /api/v1/tenants/health-summary</code>
            <br />not yet implemented — see MISSING_ENDPOINTS.md
          </div>
        </div>
      ) : error ? (
        <div style={{ padding: '32px 18px', textAlign: 'center' }}>
          <AlertTriangle size={18} color={C.red} style={{ marginBottom: 8 }} />
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red }}>{error}</div>
        </div>
      ) : tenants.length === 0 ? (
        <div style={{ padding: '32px 18px', textAlign: 'center' }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>NO TENANTS FOUND</div>
        </div>
      ) : (
        <div style={{ padding: 18 }}>
          {/* Legend */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 14, flexWrap: 'wrap' }}>
            {[['≥80', '#4ADE80', 'Healthy'], ['60–79', '#F59E0B', 'Warning'], ['40–59', '#FB923C', 'Degraded'], ['<40', '#F87171', 'Critical']].map(([range, color, label]) => (
              <div key={range} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
                <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>{range} {label}</span>
              </div>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))', gap: 8 }}>
            {tenants.map(t => (
              <div
                key={t.org_id || t.id}
                onClick={() => setSelected(selected?.org_id === t.org_id ? null : t)}
                onMouseMove={e => setTooltip({ tenant: t, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setTooltip({ tenant: null, x: 0, y: 0 })}
                style={{
                  padding: '10px 8px', borderRadius: 8, cursor: 'pointer', textAlign: 'center',
                  background: healthBg(t.health_score),
                  border: `1px solid ${selected?.org_id === t.org_id ? healthColor(t.health_score) : 'transparent'}`,
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ fontFamily: C.mono, fontSize: 16, fontWeight: 700,
                  color: healthColor(t.health_score), lineHeight: 1 }}>
                  {t.health_score ?? '?'}
                </div>
                <div style={{ fontFamily: C.mono, fontSize: 9, color: C.text3, marginTop: 4,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {(t.org_name || t.name || '').substring(0, 10)}
                </div>
              </div>
            ))}
          </div>
          {selected && (
            <div style={{ marginTop: 14, padding: 14, borderRadius: 8, background: C.surface,
              border: `1px solid ${C.border}` }}>
              <div style={{ fontFamily: C.mono, fontSize: 12, color: C.text1, marginBottom: 8 }}>
                {selected.org_name || selected.name}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 20px' }}>
                <Row label="Health score"  value={`${selected.health_score ?? '—'}%`} color={healthColor(selected.health_score)} />
                <Row label="Error rate"    value={selected.error_rate != null ? `${selected.error_rate.toFixed(2)}%` : '—'} />
                <Row label="P95 latency"   value={selected.p95_latency_ms != null ? `${selected.p95_latency_ms}ms` : '—'} />
                <Row label="Active sessions" value={selected.active_sessions ?? '—'} />
                <Row label="Failed auth (1h)" value={selected.failed_auth_1h ?? '—'} />
                <Row label="Last incident" value={fmtTime(selected.last_incident_at)} />
              </div>
              {selected.top_issue && (
                <div style={{ marginTop: 8, fontFamily: C.mono, fontSize: 10,
                  color: C.amber, padding: '6px 10px', borderRadius: 5,
                  background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.15)' }}>
                  Top issue: {selected.top_issue}
                </div>
              )}
              {/* Score breakdown */}
              {(selected.cpu != null || selected.memory != null || selected.disk != null) && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontFamily: C.mono, fontSize: 9, color: C.text3, marginBottom: 6, letterSpacing: '0.1em' }}>
                    SCORE BREAKDOWN
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                    {[
                      { label: 'CPU', val: selected.cpu, warn: 75, crit: 90 },
                      { label: 'MEM', val: selected.memory, warn: 80, crit: 90 },
                      { label: 'DISK', val: selected.disk, warn: 80, crit: 90 },
                    ].map(({ label, val, warn, crit }) => {
                      const color = val == null ? C.text3 : val >= crit ? '#EF4444' : val >= warn ? '#F59E0B' : '#10B981';
                      return (
                        <div key={label} style={{ textAlign: 'center', background: 'rgba(0,0,0,0.2)', borderRadius: 5, padding: '6px 4px' }}>
                          <div style={{ fontFamily: C.mono, fontSize: 16, fontWeight: 700, color, lineHeight: 1 }}>
                            {val != null ? `${val.toFixed(0)}%` : '—'}
                          </div>
                          <div style={{ fontFamily: C.mono, fontSize: 9, color: C.text3, marginTop: 3 }}>{label}</div>
                        </div>
                      );
                    })}
                  </div>
                  {selected.open_alerts > 0 && (
                    <div style={{ fontFamily: C.mono, fontSize: 10, color: '#EF4444', marginTop: 6 }}>
                      {selected.open_alerts} open alert{selected.open_alerts > 1 ? 's' : ''} deducting from score
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <Tooltip {...tooltip} />
    </div>
  );
}
