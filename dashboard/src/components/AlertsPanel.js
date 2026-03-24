import React, { useState, useEffect, useCallback, memo } from 'react';
import { apiService, realTimeService } from '../services/api';
import {
  BellRing, LayoutList, LayoutGrid, RefreshCw,
  ChevronDown, ChevronUp, AlertTriangle, Info,
  CheckCircle, XCircle, Lightbulb, Clock, Server,
  ShieldCheck,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------
const C = {
  bg:           'rgb(14,13,11)',
  surface:      'rgb(22,20,16)',
  surface2:     'rgb(31,29,24)',
  border:       'rgba(42,40,32,1)',
  borderAmber:  'rgba(245,158,11,0.12)',
  amber:        '#F59E0B',
  amberDim:     '#D97706',
  amberAlpha:   'rgba(245,158,11,0.1)',
  red:          '#F87171',
  redAlpha:     'rgba(248,113,113,0.12)',
  teal:         '#2DD4BF',
  tealAlpha:    'rgba(45,212,191,0.1)',
  text1:        'rgb(245,240,232)',
  text2:        'rgb(168,159,140)',
  text3:        'rgb(107,99,87)',
};

// ---------------------------------------------------------------------------
// Severity config
// ---------------------------------------------------------------------------
const SEV = {
  critical: { color: '#F87171', alpha: 'rgba(248,113,113,0.12)', label: 'CRITICAL' },
  error:    { color: '#F87171', alpha: 'rgba(248,113,113,0.08)', label: 'ERROR' },
  warning:  { color: '#F59E0B', alpha: 'rgba(245,158,11,0.12)',  label: 'WARNING' },
  info:     { color: '#2DD4BF', alpha: 'rgba(45,212,191,0.1)',   label: 'INFO' },
  success:  { color: '#2DD4BF', alpha: 'rgba(45,212,191,0.1)',   label: 'OK' },
};
const STATUS = {
  active:        { color: '#F87171', label: 'ACTIVE' },
  investigating: { color: '#F59E0B', label: 'INVESTIGATING' },
  resolved:      { color: '#2DD4BF', label: 'RESOLVED' },
};

function getSev(s)    { return SEV[s]    || SEV.info; }
function getStatus(s) { return STATUS[s] || STATUS.active; }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function SeverityIcon({ s, size = 14 }) {
  const col = getSev(s).color;
  if (s === 'critical' || s === 'error')
    return <XCircle size={size} style={{ color: col }} />;
  if (s === 'warning')
    return <AlertTriangle size={size} style={{ color: col }} />;
  if (s === 'success')
    return <CheckCircle size={size} style={{ color: col }} />;
  return <Info size={size} style={{ color: col }} />;
}

function timeAgo(ts) {
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 0) return 'just now';
  const m = Math.floor(diff / 60000);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (d > 0) return `${d}d ${h % 24}h ago`;
  if (h > 0) return `${h}h ${m % 60}m ago`;
  if (m > 0) return `${m}m ago`;
  return 'just now';
}

function mapAlert(a, idx) {
  // Backend sends timestamp as Unix float (seconds)
  const ts = a.timestamp
    ? (typeof a.timestamp === 'number' ? a.timestamp * 1000 : new Date(a.timestamp).getTime())
    : Date.now();
  return {
    id:               a.id ?? `alert-${idx}`,
    severity:         a.severity || 'info',
    message:          a.message || a.description || 'Alert',
    source:           a.source || 'System Monitor',
    timestamp:        new Date(ts),
    status:           a.status || 'active',
    details:          a.details || '',
    category:         a.category || 'General',
    affected_systems: Array.isArray(a.affected_systems) ? a.affected_systems : [],
    recommendation:   a.recommendation || '',
  };
}

// ---------------------------------------------------------------------------
// Card view
// ---------------------------------------------------------------------------
function AlertCard({ alert, expanded, onToggle }) {
  const sev    = getSev(alert.severity);
  const stat   = getStatus(alert.status);

  return (
    <div
      onClick={onToggle}
      style={{
        background:   C.surface,
        border:       `1px solid ${C.border}`,
        borderLeft:   `3px solid ${sev.color}`,
        borderRadius: 10,
        overflow:     'hidden',
        cursor:       'pointer',
        transition:   'background 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.background = C.surface2}
      onMouseLeave={e => e.currentTarget.style.background = C.surface}
    >
      <div style={{ padding: '14px 16px' }}>
        {/* Top row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <SeverityIcon s={alert.severity} size={13} />
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
              color: sev.color, background: sev.alpha,
              padding: '2px 6px', borderRadius: 4,
            }}>
              {sev.label}
            </span>
            <span style={{
              fontSize: 9, fontWeight: 600, letterSpacing: '0.06em',
              color: stat.color, opacity: 0.85,
              padding: '2px 6px', borderRadius: 4,
              background: `${stat.color}15`,
            }}>
              {stat.label}
            </span>
          </div>
          {expanded
            ? <ChevronUp size={13} style={{ color: C.text3 }} />
            : <ChevronDown size={13} style={{ color: C.text3 }} />}
        </div>

        {/* Message */}
        <p style={{ fontSize: 13, fontWeight: 500, color: C.text1, margin: 0, lineHeight: 1.45 }}>
          {alert.message}
        </p>

        {/* Meta */}
        <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
          <span style={{ fontSize: 11, color: C.text3, display: 'flex', alignItems: 'center', gap: 4 }}>
            <Server size={10} />{alert.source}
          </span>
          <span style={{ fontSize: 11, color: C.text3, display: 'flex', alignItems: 'center', gap: 4 }}>
            <Clock size={10} />{timeAgo(alert.timestamp)}
          </span>
        </div>

        {/* Expanded */}
        {expanded && (
          <div style={{
            marginTop: 12, paddingTop: 12,
            borderTop: `1px solid ${C.border}`,
            display: 'flex', flexDirection: 'column', gap: 8,
          }}>
            {alert.details && (
              <p style={{ fontSize: 12, color: C.text2, margin: 0, lineHeight: 1.55 }}>{alert.details}</p>
            )}
            {alert.affected_systems.length > 0 && (
              <p style={{ fontSize: 11, color: C.text3, margin: 0 }}>
                <span style={{ color: C.text2, fontWeight: 600 }}>Affected: </span>
                {alert.affected_systems.join(', ')}
              </p>
            )}
            {alert.recommendation && (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                background: 'rgba(245,158,11,0.07)',
                border: `1px solid rgba(245,158,11,0.15)`,
                borderRadius: 6, padding: '8px 10px',
              }}>
                <Lightbulb size={11} style={{ color: C.amber, marginTop: 1, flexShrink: 0 }} />
                <span style={{ fontSize: 11, color: C.text2, lineHeight: 1.5 }}>{alert.recommendation}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table row
// ---------------------------------------------------------------------------
function AlertRow({ alert, expanded, onToggle, isLast }) {
  const sev  = getSev(alert.severity);
  const stat = getStatus(alert.status);

  return (
    <>
      <tr
        onClick={onToggle}
        style={{ cursor: 'pointer', transition: 'background 0.12s' }}
        onMouseEnter={e => e.currentTarget.style.background = C.surface2}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        {/* Severity */}
        <td style={{ padding: '11px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !expanded ? 'none' : `1px solid ${C.border}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: sev.color, flexShrink: 0, boxShadow: `0 0 6px ${sev.color}80` }} />
            <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: sev.color, background: sev.alpha, padding: '2px 6px', borderRadius: 4 }}>
              {sev.label}
            </span>
          </div>
        </td>

        {/* Message */}
        <td style={{ padding: '11px 16px', maxWidth: 340, borderBottom: isLast && !expanded ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 13, color: C.text1, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {alert.message}
          </span>
        </td>

        {/* Category */}
        <td style={{ padding: '11px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !expanded ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 11, color: C.text3, fontFamily: "'IBM Plex Mono', monospace" }}>{alert.category}</span>
        </td>

        {/* Source */}
        <td style={{ padding: '11px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !expanded ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 11, color: C.text3 }}>{alert.source}</span>
        </td>

        {/* Status */}
        <td style={{ padding: '11px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !expanded ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.06em', color: stat.color, background: `${stat.color}18`, padding: '2px 7px', borderRadius: 4 }}>
            {stat.label}
          </span>
        </td>

        {/* Time */}
        <td style={{ padding: '11px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !expanded ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 11, color: C.text3, fontFamily: "'IBM Plex Mono', monospace" }}>{timeAgo(alert.timestamp)}</span>
        </td>

        {/* Expand */}
        <td style={{ padding: '11px 12px', borderBottom: isLast && !expanded ? 'none' : `1px solid ${C.border}` }}>
          {expanded
            ? <ChevronUp size={13} style={{ color: C.text3 }} />
            : <ChevronDown size={13} style={{ color: C.text3 }} />}
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={7} style={{ padding: '0 16px 14px 16px', background: C.surface2, borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 10 }}>
              {alert.details && (
                <p style={{ fontSize: 12, color: C.text2, margin: 0, lineHeight: 1.55 }}>{alert.details}</p>
              )}
              {alert.affected_systems.length > 0 && (
                <p style={{ fontSize: 11, color: C.text3, margin: 0 }}>
                  <span style={{ color: C.text2, fontWeight: 600 }}>Affected: </span>
                  {alert.affected_systems.join(', ')}
                </p>
              )}
              {alert.recommendation && (
                <div style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  background: 'rgba(245,158,11,0.07)',
                  border: `1px solid rgba(245,158,11,0.15)`,
                  borderRadius: 6, padding: '8px 10px',
                }}>
                  <Lightbulb size={11} style={{ color: C.amber, marginTop: 1, flexShrink: 0 }} />
                  <span style={{ fontSize: 11, color: C.text2, lineHeight: 1.5 }}>{alert.recommendation}</span>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------
function Skeleton() {
  return (
    <div style={{ padding: '4px 0' }}>
      {[1, 2, 3].map(i => (
        <div key={i} style={{
          display: 'flex', gap: 12, padding: '14px 16px',
          borderBottom: `1px solid ${C.border}`,
        }}>
          <div style={{ width: 70, height: 14, background: C.surface2, borderRadius: 4 }} />
          <div style={{ flex: 1, height: 14, background: C.surface2, borderRadius: 4 }} />
          <div style={{ width: 80, height: 14, background: C.surface2, borderRadius: 4 }} />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
function EmptyState() {
  return (
    <div style={{ padding: '48px 24px', textAlign: 'center' }}>
      <ShieldCheck size={32} style={{ color: C.teal, margin: '0 auto 12px', opacity: 0.7 }} />
      <p style={{ fontSize: 14, fontWeight: 600, color: C.text1, margin: '0 0 4px' }}>All systems healthy</p>
      <p style={{ fontSize: 12, color: C.text3, margin: 0 }}>No active alerts — metrics are within normal thresholds</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
const AlertsPanel = memo(() => {
  const [alerts,   setAlerts]   = useState([]);
  const [expanded, setExpanded] = useState({});
  const [viewMode, setViewMode] = useState('table');
  const [loading,  setLoading]  = useState(true);
  const [spinning, setSpinning] = useState(false);

  const fetchAlerts = useCallback(async () => {
    try {
      const list = await apiService.getAlerts();
      if (Array.isArray(list)) {
        setAlerts(list.map(mapAlert));
      }
    } catch {
      setAlerts([]);
    }
  }, []);

  const handleRefresh = async () => {
    setSpinning(true);
    await fetchAlerts();
    setTimeout(() => setSpinning(false), 600);
  };

  useEffect(() => {
    fetchAlerts().finally(() => setLoading(false));

    const unsub = realTimeService.subscribe('alerts', (data) => {
      if (Array.isArray(data)) setAlerts(data.map(mapAlert));
    });

    const onRefresh = () => fetchAlerts();
    window.addEventListener('aiops:refresh', onRefresh);
    return () => { unsub(); window.removeEventListener('aiops:refresh', onRefresh); };
  }, [fetchAlerts]);

  const toggle = (id) => setExpanded(p => ({ ...p, [id]: !p[id] }));

  const criticalCount = alerts.filter(a => a.severity === 'critical').length;
  const warningCount  = alerts.filter(a => a.severity === 'warning').length;
  const activeCount   = alerts.filter(a => a.status === 'active').length;

  return (
    <div style={{
      background:   C.surface,
      border:       `1px solid ${C.borderAmber}`,
      borderRadius: 12,
      overflow:     'hidden',
    }}>
      {/* Header */}
      <div style={{
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'space-between',
        padding:        '14px 18px',
        borderBottom:   `1px solid ${C.border}`,
        flexWrap:       'wrap',
        gap:            10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BellRing size={15} style={{ color: C.amber }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>Recent Alerts</span>
            {activeCount > 0 && (
              <span style={{
                fontSize: 10, fontWeight: 700, color: '#F87171',
                background: 'rgba(248,113,113,0.12)', padding: '2px 8px',
                borderRadius: 999, letterSpacing: '0.04em',
              }}>
                {activeCount} active
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {criticalCount > 0 && (
              <span style={{ fontSize: 9, fontWeight: 700, color: '#F87171', background: 'rgba(248,113,113,0.1)', padding: '2px 7px', borderRadius: 4, letterSpacing: '0.07em' }}>
                {criticalCount} CRITICAL
              </span>
            )}
            {warningCount > 0 && (
              <span style={{ fontSize: 9, fontWeight: 700, color: C.amber, background: C.amberAlpha, padding: '2px 7px', borderRadius: 4, letterSpacing: '0.07em' }}>
                {warningCount} WARNING
              </span>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 4 }}>
          <button
            onClick={() => setViewMode(v => v === 'table' ? 'cards' : 'table')}
            title="Toggle view"
            style={{
              padding: '6px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: 'transparent', color: C.text3, transition: 'color 0.15s, background 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = C.surface2; e.currentTarget.style.color = C.text1; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = C.text3; }}
          >
            {viewMode === 'table' ? <LayoutGrid size={14} /> : <LayoutList size={14} />}
          </button>
          <button
            onClick={handleRefresh}
            title="Refresh"
            style={{
              padding: '6px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: 'transparent', color: C.text3, transition: 'color 0.15s, background 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = C.surface2; e.currentTarget.style.color = C.text1; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = C.text3; }}
          >
            <RefreshCw size={14} style={spinning ? { animation: 'spin 0.7s linear infinite' } : {}} />
          </button>
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <Skeleton />
      ) : alerts.length === 0 ? (
        <EmptyState />
      ) : viewMode === 'cards' ? (
        <div style={{ padding: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {alerts.map(a => (
            <AlertCard key={a.id} alert={a} expanded={!!expanded[a.id]} onToggle={() => toggle(a.id)} />
          ))}
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                {['Severity', 'Message', 'Category', 'Source', 'Status', 'Time', ''].map(h => (
                  <th key={h} style={{
                    padding: '8px 16px',
                    fontSize: 9, fontWeight: 700, letterSpacing: '0.09em',
                    textAlign: 'left', color: C.text3, whiteSpace: 'nowrap',
                    fontFamily: "'IBM Plex Mono', monospace",
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {alerts.map((a, i) => (
                <AlertRow
                  key={a.id}
                  alert={a}
                  expanded={!!expanded[a.id]}
                  onToggle={() => toggle(a.id)}
                  isLast={i === alerts.length - 1}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
});

export default AlertsPanel;
