import React, { useEffect, useState, useCallback, useRef } from 'react';
import toast from 'react-hot-toast';
import {
  Wrench, CheckCircle, XCircle, Play, RefreshCw,
  Cpu, MemoryStick, HardDrive, Zap, Clock,
  ChevronDown, ChevronUp, ShieldCheck,
  Bot, Activity, Radio, Shield,
} from 'lucide-react';
import { apiService } from '../services/api';
import InfoTip from './InfoTip';

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------
const C = {
  bg:          'rgb(14,13,11)',
  surface:     'rgb(22,20,16)',
  surface2:    'rgb(31,29,24)',
  border:      'rgba(42,40,32,1)',
  borderAmber: 'rgba(245,158,11,0.12)',
  amber:       '#F59E0B',
  amberAlpha:  'rgba(245,158,11,0.1)',
  amberDim:    '#D97706',
  red:         '#F87171',
  redAlpha:    'rgba(248,113,113,0.12)',
  teal:        '#2DD4BF',
  tealAlpha:   'rgba(45,212,191,0.1)',
  green:       '#4ADE80',
  greenAlpha:  'rgba(74,222,128,0.1)',
  text1:       'rgb(245,240,232)',
  text2:       'rgb(168,159,140)',
  text3:       'rgb(107,99,87)',
  mono:        "'IBM Plex Mono', monospace",
};

const SEV_COLOR = {
  low:      { fg: C.teal,    bg: C.tealAlpha },
  medium:   { fg: C.amber,   bg: C.amberAlpha },
  high:     { fg: '#FB923C', bg: 'rgba(251,146,60,0.12)' },
  critical: { fg: C.red,     bg: C.redAlpha },
};
function sevStyle(s) { return SEV_COLOR[s] || SEV_COLOR.medium; }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}


// Parse a simple "metric_name > 80" trigger pattern → { key, op, threshold }
function parseTrigger(pattern) {
  const m = /^(\w+)\s*(>=|<=|>|<|==)\s*([\d.]+)$/.exec((pattern || '').trim());
  if (!m) return null;
  return { key: m[1], op: m[2], threshold: parseFloat(m[3]) };
}

function evalTrigger(pattern, metrics) {
  const p = parseTrigger(pattern);
  if (!p) return false;
  const MAP = { cpu_usage: 'cpu', memory_usage: 'memory', disk_usage: 'disk', error_rate: 'error_rate' };
  const val = metrics[MAP[p.key] ?? p.key];
  if (val == null) return false;
  switch (p.op) {
    case '>':  return val > p.threshold;
    case '<':  return val < p.threshold;
    case '>=': return val >= p.threshold;
    case '<=': return val <= p.threshold;
    case '==': return val === p.threshold;
    default:   return false;
  }
}

function metricBar(val, warn = 75, crit = 90) {
  const pct = Math.min(100, Math.max(0, val || 0));
  const color = pct >= crit ? C.red : pct >= warn ? C.amber : C.teal;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: C.surface2, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: C.mono, color, minWidth: 36, textAlign: 'right' }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------
function StatCard({ label, value, sub, highlight, info }) {
  return (
    <div style={{
      background: highlight ? 'rgba(245,158,11,0.07)' : C.surface2,
      border: `1px solid ${highlight ? 'rgba(245,158,11,0.25)' : C.border}`,
      borderRadius: 10, padding: '14px 18px', position: 'relative',
    }}>
      {info && (
        <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10 }}>
          <InfoTip info={info} />
        </div>
      )}
      <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.09em', color: highlight ? C.amber : C.text3, fontFamily: C.mono, margin: '0 0 6px' }}>
        {label}
      </p>
      <p style={{ fontSize: 22, fontWeight: 700, fontFamily: "'Bebas Neue', sans-serif", letterSpacing: '0.03em', color: highlight ? C.amber : C.text1, margin: 0, lineHeight: 1 }}>
        {value ?? '—'}
      </p>
      {sub && <p style={{ fontSize: 10, color: C.text3, margin: '4px 0 0', fontFamily: C.mono }}>{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------
function Skeleton() {
  return (
    <div style={{ padding: '20px 0', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {[160, 240, 100, 200].map((w, i) => (
        <div key={i} style={{ height: 14, width: w, background: C.surface2, borderRadius: 4 }} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// History row
// ---------------------------------------------------------------------------
function HistoryRow({ item, isLast }) {
  const [open, setOpen] = useState(false);
  const hasDelta = item.metrics_before && item.metrics_after;

  return (
    <>
      <tr
        onClick={() => hasDelta && setOpen(o => !o)}
        style={{ cursor: hasDelta ? 'pointer' : 'default', transition: 'background 0.12s' }}
        onMouseEnter={e => hasDelta && (e.currentTarget.style.background = C.surface2)}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        <td style={{ padding: '10px 16px', borderBottom: isLast && !open ? 'none' : `1px solid ${C.border}` }}>
          {item.success
            ? <CheckCircle size={13} style={{ color: C.teal }} />
            : <XCircle    size={13} style={{ color: C.red }} />}
        </td>
        <td style={{ padding: '10px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !open ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 11, fontFamily: C.mono, color: C.text3 }}>{fmt(item.timestamp)}</span>
        </td>
        <td style={{ padding: '10px 16px', borderBottom: isLast && !open ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 12, fontWeight: 500, color: C.text1 }}>{item.rule_name || item.rule_id}</span>
        </td>
        <td style={{ padding: '10px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !open ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 11, color: C.text3, fontFamily: C.mono }}>{item.action?.replace(/_/g, ' ')}</span>
        </td>
        <td style={{ padding: '10px 16px', whiteSpace: 'nowrap', borderBottom: isLast && !open ? 'none' : `1px solid ${C.border}` }}>
          <span style={{ fontSize: 11, color: C.text3, fontFamily: C.mono }}>
            {item.execution_time_seconds != null ? `${item.execution_time_seconds}s` : '—'}
          </span>
        </td>
        <td style={{ padding: '10px 12px', borderBottom: isLast && !open ? 'none' : `1px solid ${C.border}` }}>
          {hasDelta && (open
            ? <ChevronUp size={12} style={{ color: C.text3 }} />
            : <ChevronDown size={12} style={{ color: C.text3 }} />)}
        </td>
      </tr>

      {open && hasDelta && (
        <tr>
          <td colSpan={6} style={{ padding: '0 16px 12px 44px', background: C.surface2, borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
            <div style={{ paddingTop: 10, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              {['cpu_usage', 'memory_usage', 'disk_usage'].map(key => {
                const before = item.metrics_before?.[key];
                const after  = item.metrics_after?.[key];
                if (before == null && after == null) return null;
                const label = key.replace('_usage', '').toUpperCase();
                const delta = after != null && before != null ? (after - before) : null;
                const better = delta != null && delta < 0;
                return (
                  <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontSize: 9, fontWeight: 700, color: C.text3, letterSpacing: '0.08em', fontFamily: C.mono }}>{label}</span>
                    <span style={{ fontSize: 12, fontFamily: C.mono, color: C.text2 }}>
                      {before != null ? `${before.toFixed(1)}%` : '—'}{' → '}{after != null ? `${after.toFixed(1)}%` : '—'}
                      {delta != null && (
                        <span style={{ marginLeft: 6, color: better ? C.teal : C.red, fontSize: 11 }}>
                          ({better ? '' : '+'}{delta.toFixed(1)}%)
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
              {item.error_message && (
                <span style={{ fontSize: 11, color: C.red, fontFamily: C.mono, alignSelf: 'center' }}>
                  {item.error_message}
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// IssueCard — per-issue agentic card
// ---------------------------------------------------------------------------
function IssueCard({ issue, status = 'idle', autonomousMode, onFix }) {
  const sc = sevStyle(issue.severity);
  const parsed = parseTrigger(issue.trigger_pattern);
  const threshold = parsed?.threshold ?? 0;
  const unit = issue.trigger_pattern.includes('error_rate') ? ' err/min' : '%';

  const isHighOrCrit = issue.severity === 'high' || issue.severity === 'critical';

  function handleClick() {
    if (status === 'fixing' || status === 'cooldown') return;
    if (isHighOrCrit) {
      const ok = window.confirm(
        `This action has ${issue.severity.toUpperCase()} severity and may cause service disruption.\n\nProceed with: ${issue.rule_name}?`
      );
      if (!ok) return;
    }
    onFix(issue.rule_id, issue.issue_type);
  }

  // Status badge
  let statusEl;
  if (status === 'fixing') {
    statusEl = (
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: C.amber, fontFamily: C.mono }}>
        <Wrench size={11} style={{ animation: 'spin 1s linear infinite' }} />
        Fixing…
      </span>
    );
  } else if (status === 'fixed') {
    statusEl = (
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: C.green, fontFamily: C.mono }}>
        <CheckCircle size={11} /> Fixed
      </span>
    );
  } else if (status === 'failed') {
    statusEl = (
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: C.red, fontFamily: C.mono }}>
        <XCircle size={11} /> Failed
      </span>
    );
  } else if (status === 'cooldown') {
    statusEl = (
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: C.text3, fontFamily: C.mono }}>
        <Clock size={11} /> Cooldown
      </span>
    );
  } else {
    statusEl = (
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: C.amber, fontFamily: C.mono }}>
        <span style={{
          width: 6, height: 6, borderRadius: '50%', background: C.amber,
          display: 'inline-block', boxShadow: `0 0 6px ${C.amber}`,
          animation: 'pulse 1.5s ease-in-out infinite',
        }} />
        ACTIVE
      </span>
    );
  }

  // Action button
  let actionBtn = null;
  if (autonomousMode && status === 'idle') {
    actionBtn = (
      <span style={{ fontSize: 11, color: C.text3, fontFamily: C.mono, display: 'flex', alignItems: 'center', gap: 5 }}>
        <Bot size={11} style={{ color: C.amber }} /> Agent Active
      </span>
    );
  } else if (status === 'cooldown') {
    actionBtn = null;
  } else {
    const canClick = status !== 'fixing' && status !== 'cooldown';
    actionBtn = (
      <button
        onClick={handleClick}
        disabled={!canClick}
        style={{
          padding: '6px 14px', borderRadius: 7, fontSize: 11, fontWeight: 600,
          cursor: canClick ? 'pointer' : 'not-allowed',
          background: canClick ? C.amberAlpha : C.surface2,
          border: `1px solid ${canClick ? 'rgba(245,158,11,0.3)' : C.border}`,
          color: canClick ? C.amber : C.text3,
          display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s',
          opacity: canClick ? 1 : 0.5,
        }}
        onMouseEnter={e => canClick && (e.currentTarget.style.background = 'rgba(245,158,11,0.18)')}
        onMouseLeave={e => canClick && (e.currentTarget.style.background = C.amberAlpha)}
      >
        <Play size={10} />
        Auto-Fix
      </button>
    );
  }

  return (
    <div style={{
      background: C.surface2,
      border: `1px solid ${status === 'fixed' ? 'rgba(74,222,128,0.2)' : status === 'failed' ? 'rgba(248,113,113,0.2)' : 'rgba(245,158,11,0.18)'}`,
      borderRadius: 10, padding: '14px 16px',
      transition: 'border-color 0.3s',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
            color: sc.fg, background: sc.bg, padding: '2px 6px', borderRadius: 4,
          }}>
            {issue.severity?.toUpperCase()}
          </span>
          <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>{issue.rule_name}</span>
        </div>
        {statusEl}
      </div>

      {/* Metric bar */}
      <div style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ fontSize: 10, color: C.text3, fontFamily: C.mono }}>
            {issue.trigger_pattern}
          </span>
          <span style={{ fontSize: 10, color: C.text3, fontFamily: C.mono }}>
            current: <span style={{ color: C.amber }}>{(issue.current_value ?? 0).toFixed(1)}{unit}</span>
            {' / '}threshold: {threshold}{unit}
          </span>
        </div>
        {metricBar(issue.current_value, threshold, threshold + 5)}
      </div>

      {/* AI explanation + button row */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 8, marginTop: 4 }}>
        <p style={{ fontSize: 11, color: C.text3, margin: 0, lineHeight: 1.45, flex: 1 }}>
          {issue.ai_explanation || issue.description}
        </p>
        {actionBtn}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AutonomousModeToggle
// ---------------------------------------------------------------------------
function AutonomousModeToggle({ enabled, loading, onToggle }) {
  return (
    <div style={{
      background: enabled ? 'rgba(245,158,11,0.06)' : C.surface,
      border: `1px solid ${enabled ? 'rgba(245,158,11,0.25)' : C.borderAmber}`,
      borderRadius: 12, padding: '14px 18px',
      display: 'flex', alignItems: 'center', gap: 14,
      transition: 'background 0.25s, border-color 0.25s',
    }}>
      <Bot size={18} style={{ color: enabled ? C.amber : C.text3, flexShrink: 0 }} />
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>Agent Autonomous Mode</span>
          {enabled && (
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: '0.07em',
              color: C.amber, background: C.amberAlpha, padding: '2px 7px', borderRadius: 4,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: C.amber, display: 'inline-block', animation: 'pulse 1.5s ease-in-out infinite' }} />
              ON
            </span>
          )}
        </div>
        <p style={{ fontSize: 11, color: C.text3, margin: '3px 0 0', fontFamily: C.mono }}>
          {enabled
            ? 'Agent is auto-fixing LOW and MEDIUM severity issues — HIGH/CRITICAL always require manual confirmation'
            : 'Turn on to let the agent auto-fix issues without manual intervention (LOW/MEDIUM severity only)'}
        </p>
      </div>
      <button
        onClick={onToggle}
        disabled={loading}
        title={enabled ? 'Disable autonomous mode' : 'Enable autonomous mode'}
        style={{
          flexShrink: 0, position: 'relative',
          width: 42, height: 23, borderRadius: 999,
          border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
          background: enabled ? C.amber : C.surface2,
          transition: 'background 0.2s',
          opacity: loading ? 0.5 : 1,
        }}
      >
        <span style={{
          position: 'absolute', top: 3,
          left: enabled ? 21 : 3,
          width: 17, height: 17, borderRadius: '50%',
          background: enabled ? 'rgb(14,13,11)' : C.text3,
          transition: 'left 0.2s',
        }} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActivityFeed
// ---------------------------------------------------------------------------
function ActivityFeed({ entries }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.borderAmber}`,
      borderRadius: 12, overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '13px 18px', borderBottom: `1px solid ${C.border}` }}>
        <span style={{ color: C.amber }}><Activity size={14} /></span>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>Agent Activity</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5 }}>
          <Radio size={10} style={{ color: C.amber, animation: 'pulse 1.5s ease-in-out infinite' }} />
          <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: C.amber, fontFamily: C.mono }}>LIVE</span>
        </div>
      </div>

      {/* Feed */}
      <div style={{ maxHeight: 240, overflowY: 'auto', padding: '8px 0' }}>
        {entries.length === 0 ? (
          <div style={{ padding: '28px 24px', textAlign: 'center' }}>
            <p style={{ fontSize: 12, color: C.text3, margin: 0 }}>No agent activity yet</p>
          </div>
        ) : (
          entries.map((entry, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '7px 18px',
              borderBottom: i < entries.length - 1 ? `1px solid rgba(42,40,32,0.5)` : 'none',
            }}>
              {entry.success
                ? <CheckCircle size={12} style={{ color: C.teal, flexShrink: 0 }} />
                : <XCircle size={12} style={{ color: C.red, flexShrink: 0 }} />}
              <span style={{ fontSize: 11, color: C.text2, flex: 1 }}>
                {entry.rule_name || entry.rule_id}
                <span style={{ color: C.text3 }}> — {entry.action?.replace(/_/g, ' ')}</span>
                {entry.execution_time_seconds != null && (
                  <span style={{ color: C.text3, fontFamily: C.mono }}> in {entry.execution_time_seconds}s</span>
                )}
              </span>
              <span style={{ fontSize: 10, color: C.text3, fontFamily: C.mono, flexShrink: 0 }}>
                {fmt(entry.timestamp)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// IssueDetectionPanel
// ---------------------------------------------------------------------------
function IssueDetectionPanel({ issues, issueStatuses, autonomousMode, onFix, metrics }) {
  const activeIssues = issues.filter(i => i.triggered || issueStatuses[i.rule_id]?.status === 'fixing');

  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.borderAmber}`,
      borderRadius: 12, overflow: 'hidden',
    }}>
      {/* Header with live metrics strip */}
      <div style={{ borderBottom: `1px solid ${C.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '13px 18px 10px' }}>
          <span style={{ color: C.amber }}><Zap size={14} /></span>
          <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>Live Issue Detection</span>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: C.text3, fontFamily: C.mono }}>
            polling every 5s
          </span>
        </div>

        {/* Inline metrics strip */}
        {metrics && (metrics.cpu != null || metrics.memory != null || metrics.disk != null) && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, padding: '0 18px 12px' }}>
            {[
              { icon: <Cpu size={11} />,        label: 'CPU',    val: metrics.cpu,    warn: 75, crit: 90 },
              { icon: <MemoryStick size={11} />, label: 'MEMORY', val: metrics.memory, warn: 80, crit: 90 },
              { icon: <HardDrive size={11} />,   label: 'DISK',   val: metrics.disk,   warn: 80, crit: 90 },
            ].map(({ icon, label, val, warn, crit }) => (
              <div key={label}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 5 }}>
                  <span style={{ color: C.text3 }}>{icon}</span>
                  <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.09em', color: C.text3, fontFamily: C.mono }}>{label}</span>
                </div>
                {metricBar(val, warn, crit)}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: 16 }}>
        {activeIssues.length === 0 ? (
          autonomousMode ? (
            <div style={{ padding: '28px 0', textAlign: 'center' }}>
              <Shield size={28} style={{ color: C.green, margin: '0 auto 10px', opacity: 0.7 }} />
              <p style={{ fontSize: 13, color: C.text1, fontWeight: 600, margin: '0 0 4px' }}>Agent is monitoring — all systems healthy</p>
              <p style={{ fontSize: 11, color: C.text3, margin: 0 }}>Auto-fix will activate when thresholds are exceeded</p>
            </div>
          ) : (
            <div style={{ padding: '28px 0', textAlign: 'center' }}>
              <Zap size={24} style={{ color: C.amber, margin: '0 auto 10px', opacity: 0.4 }} />
              <p style={{ fontSize: 13, color: C.text1, fontWeight: 600, margin: '0 0 4px' }}>Monitoring… No issues detected</p>
              <p style={{ fontSize: 11, color: C.text3, margin: 0 }}>Issue cards appear here when thresholds are exceeded</p>
            </div>
          )
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {issues.filter(i => i.triggered || i.in_cooldown).map(issue => (
              <IssueCard
                key={issue.rule_id}
                issue={issue}
                status={issueStatuses[issue.rule_id]?.status || (issue.in_cooldown ? 'cooldown' : 'idle')}
                autonomousMode={autonomousMode}
                onFix={onFix}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Remediation() {
  const [rules,            setRules]           = useState([]);
  const [history,          setHistory]         = useState([]);
  const [stats,            setStats]           = useState(null);
  const [metrics,          setMetrics]         = useState(null);
  const [loading,          setLoading]         = useState(true);
  const [spinning,         setSpinning]        = useState(false);
  const [issues,           setIssues]          = useState([]);
  const [autonomousMode,   setAutonomousMode]  = useState(false);
  const [autonomousLoading, setAutonomousLoading] = useState(false);
  const [issueStatuses,    setIssueStatuses]   = useState({}); // { [rule_id]: { status, updatedAt } }
  const [activityFeed,     setActivityFeed]    = useState([]);

  const historyLenRef = useRef(0);
  const resetTimers   = useRef({});

  // ── Core data fetch ──────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    const [rulesData, statsData, sysData] = await Promise.all([
      apiService.getRemediationRules(),
      apiService.getRemediationStats(),
      apiService.getSystemData(),
    ]);
    setRules(rulesData);
    setStats(statsData);
    if (sysData && !sysData.error) setMetrics(sysData);
  }, []);

  // ── Issues poll (5s) ─────────────────────────────────────────────────────
  useEffect(() => {
    const fetchIssues = async () => {
      const data = await apiService.getRemediationIssues();
      setIssues(data.issues || []);
      // Sync metrics from issues endpoint too
      if (data.metrics) {
        setMetrics(prev => prev
          ? { ...prev, cpu: data.metrics.cpu_usage ?? prev.cpu, memory: data.metrics.memory_usage ?? prev.memory, disk: data.metrics.disk_usage ?? prev.disk }
          : prev
        );
      }
      // Sync cooldown status
      setIssueStatuses(prev => {
        const next = { ...prev };
        (data.issues || []).forEach(issue => {
          if (issue.in_cooldown && next[issue.rule_id]?.status !== 'fixing') {
            next[issue.rule_id] = { status: 'cooldown', updatedAt: Date.now() };
          }
          // Clear fixed/failed if issue resolved and no longer in cooldown
          if (!issue.triggered && !issue.in_cooldown) {
            if (next[issue.rule_id]?.status === 'cooldown') {
              delete next[issue.rule_id];
            }
          }
        });
        return next;
      });
    };
    fetchIssues();
    const id = setInterval(fetchIssues, 5_000);
    return () => clearInterval(id);
  }, []);

  // ── History poll (3s) — also drives activity feed ────────────────────────
  useEffect(() => {
    const pollHistory = async () => {
      const h = await apiService.getRemediationHistory();
      setHistory(h);
      if (h.length > historyLenRef.current) {
        const newEntries = h.slice(0, h.length - historyLenRef.current);
        setActivityFeed(prev => [...newEntries, ...prev].slice(0, 50));
        historyLenRef.current = h.length;
      }
    };
    pollHistory();
    const id = setInterval(pollHistory, 3_000);
    return () => clearInterval(id);
  }, []);

  // ── Autonomous mode initial load ─────────────────────────────────────────
  useEffect(() => {
    apiService.getAutonomousMode().then(d => setAutonomousMode(d.autonomous_mode));
  }, []);

  // ── Bootstrap ────────────────────────────────────────────────────────────
  useEffect(() => {
    fetchAll().finally(() => setLoading(false));
    const id = setInterval(fetchAll, 30_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleRefresh = async () => {
    setSpinning(true);
    await fetchAll();
    setTimeout(() => setSpinning(false), 600);
  };

  function setIssueStatus(ruleId, status) {
    setIssueStatuses(prev => ({ ...prev, [ruleId]: { status, updatedAt: Date.now() } }));
  }

  function clearIssueStatus(ruleId, delayMs = 8_000) {
    if (resetTimers.current[ruleId]) clearTimeout(resetTimers.current[ruleId]);
    resetTimers.current[ruleId] = setTimeout(() => {
      setIssueStatuses(prev => {
        const next = { ...prev };
        delete next[ruleId];
        return next;
      });
    }, delayMs);
  }

  async function handleFix(ruleId, issueType) {
    setIssueStatus(ruleId, 'fixing');
    try {
      const d = await apiService.triggerRemediation(issueType || '');
      // Unified response always has d.success
      const success = d.success === true;
      setIssueStatus(ruleId, success ? 'fixed' : 'failed');
      if (success) {
        const names = (d.results || []).filter(r => r.success).map(r => r.rule_name).join(', ');
        toast.success(`Fixed: ${names || issueType || 'remediation applied'}`);
      } else {
        const err = d.results?.[0]?.error_message || d.message || 'Action did not complete';
        toast.error(`Fix failed: ${err}`);
      }
      clearIssueStatus(ruleId);
      // Refresh history immediately
      const h = await apiService.getRemediationHistory();
      setHistory(h);
      if (h.length > historyLenRef.current) {
        const newEntries = h.slice(0, h.length - historyLenRef.current);
        setActivityFeed(prev => [...newEntries, ...prev].slice(0, 50));
        historyLenRef.current = h.length;
      }
    } catch (e) {
      setIssueStatus(ruleId, 'failed');
      toast.error(e?.response?.data?.error || 'Fix request failed');
      clearIssueStatus(ruleId);
    }
  }

  async function handleAutonomousToggle() {
    setAutonomousLoading(true);
    try {
      const d = await apiService.setAutonomousMode(!autonomousMode);
      setAutonomousMode(d.autonomous_mode);
      toast.success(d.message);
      if (d.safety_note) toast(d.safety_note, { icon: '⚠️', duration: 5000 });
    } catch {
      toast.error('Failed to update autonomous mode');
    } finally {
      setAutonomousLoading(false);
    }
  }

  async function toggleRule(ruleId) {
    try {
      const res = await apiService.toggleRemediationRule(ruleId);
      setRules(prev => prev.map(r => r.id === ruleId ? { ...r, enabled: res.enabled } : r));
      toast.success(`Rule ${res.enabled ? 'enabled' : 'disabled'}`);
    } catch { toast.error('Failed to toggle rule'); }
  }

  // Derived
  const liveMetricsForEval = metrics
    ? { cpu_usage: metrics.cpu, memory_usage: metrics.memory, disk_usage: metrics.disk }
    : {};
  const activeIssueCount = issues.filter(i => i.triggered).length;

  // ── Render helpers ───────────────────────────────────────────────────────
  const panel = (children, style = {}) => (
    <div style={{ background: C.surface, border: `1px solid ${C.borderAmber}`, borderRadius: 12, overflow: 'hidden', ...style }}>
      {children}
    </div>
  );
  const panelHeader = (title, icon, right) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '13px 18px', borderBottom: `1px solid ${C.border}` }}>
      <span style={{ color: C.amber }}>{icon}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>{title}</span>
      {right && <div style={{ marginLeft: 'auto' }}>{right}</div>}
    </div>
  );

  if (loading) {
    return <div style={{ padding: 24 }}><Skeleton /></div>;
  }

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 1100 }}>

      {/* Keyframes (injected once) */}
      <style>{`
        @keyframes spin  { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
      `}</style>

      {/* Page title + refresh */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: C.text1, margin: 0, fontFamily: "'Outfit', sans-serif" }}>
            Auto-Remediation
          </h2>
          <p style={{ fontSize: 12, color: C.text3, margin: '4px 0 0' }}>
            Agentic issue detection with one-click auto-fix and autonomous healing
          </p>
        </div>
        <button
          onClick={handleRefresh}
          style={{
            background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 8,
            padding: '7px 10px', cursor: 'pointer', color: C.text3, display: 'flex', alignItems: 'center', gap: 6,
            fontSize: 12, transition: 'color 0.15s, border-color 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = C.text1; e.currentTarget.style.borderColor = C.amber; }}
          onMouseLeave={e => { e.currentTarget.style.color = C.text3; e.currentTarget.style.borderColor = C.border; }}
        >
          <RefreshCw size={13} style={spinning ? { animation: 'spin 0.7s linear infinite' } : {}} />
          Refresh
        </button>
      </div>

      {/* Stats (5 cards) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
        <StatCard label="TOTAL RUNS"    value={stats?.total_attempts ?? 0}    sub={stats?.total_attempts ? 'lifetime' : 'no runs yet'}
          info="Total number of remediation actions executed since tracking began, including both manual and autonomous agent runs." />
        <StatCard label="SUCCESS RATE"  value={stats?.total_attempts ? `${(stats.success_rate ?? 0).toFixed(1)}%` : '—'}
                  sub={stats?.successful_attempts != null ? `${stats.successful_attempts} succeeded` : undefined}
          info="Percentage of runs that completed without error. Failed runs indicate a playbook action that timed out or returned a non-zero exit code — check the history table for details." />
        <StatCard label="ACTIVE RULES"  value={stats?.active_rules ?? rules.filter(r => r.enabled).length}  sub={`of ${rules.length} total`}
          info="Number of playbook rules currently enabled and monitoring for trigger conditions. Disabled rules are paused and will not fire even if their thresholds are exceeded." />
        <StatCard label="AVG EXECUTION" value={stats?.average_execution_time != null ? `${stats.average_execution_time.toFixed(1)}s` : '—'} sub="per action"
          info="Mean time in seconds for a remediation action to complete from trigger to finish. Long execution times may indicate the target process is unresponsive or network latency is high." />
        <StatCard
          label="ISSUES NOW"
          value={activeIssueCount}
          sub={activeIssueCount > 0 ? 'need attention' : 'all clear'}
          highlight={activeIssueCount > 0}
          info="Number of active rule violations right now — thresholds that are currently exceeded. These are the issues shown in the Live Issue Detection panel below."
        />
      </div>

      {/* Autonomous mode toggle */}
      <AutonomousModeToggle
        enabled={autonomousMode}
        loading={autonomousLoading}
        onToggle={handleAutonomousToggle}
      />

      {/* Live Issue Detection Panel */}
      <IssueDetectionPanel
        issues={issues}
        issueStatuses={issueStatuses}
        autonomousMode={autonomousMode}
        onFix={handleFix}
        metrics={metrics}
      />

      {/* Agent Activity Feed */}
      <ActivityFeed entries={activityFeed} />

      {/* Playbook Rules */}
      {panel(
        <>
          {panelHeader(
            'Playbook Rules',
            <Wrench size={14} />,
            <span style={{ fontSize: 10, fontWeight: 700, color: C.text3, background: C.surface2, border: `1px solid ${C.border}`, padding: '2px 8px', borderRadius: 999, fontFamily: C.mono }}>
              {rules.length}
            </span>
          )}
          {rules.length === 0 ? (
            <div style={{ padding: '40px 24px', textAlign: 'center' }}>
              <p style={{ fontSize: 13, color: C.text3, margin: 0 }}>No rules loaded</p>
            </div>
          ) : (
            <div>
              {rules.map((rule, i) => {
                const sc          = sevStyle(rule.severity);
                const isTriggered = evalTrigger(rule.trigger_pattern, liveMetricsForEval);
                const isLast      = i === rules.length - 1;
                return (
                  <div
                    key={rule.id}
                    style={{
                      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
                      padding: '14px 18px', gap: 16,
                      borderBottom: isLast ? 'none' : `1px solid ${C.border}`,
                      background: isTriggered ? 'rgba(245,158,11,0.04)' : 'transparent',
                      transition: 'background 0.15s',
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>{rule.name}</span>
                        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: sc.fg, background: sc.bg, padding: '2px 6px', borderRadius: 4 }}>
                          {rule.severity?.toUpperCase()}
                        </span>
                        {isTriggered && (
                          <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.07em', color: C.amber, background: C.amberAlpha, padding: '2px 7px', borderRadius: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ width: 5, height: 5, borderRadius: '50%', background: C.amber, display: 'inline-block', boxShadow: `0 0 4px ${C.amber}` }} />
                            TRIGGERED
                          </span>
                        )}
                        <span style={{ fontSize: 10, color: C.text3, fontFamily: C.mono }}>{rule.action?.replace(/_/g, ' ')}</span>
                      </div>
                      <p style={{ fontSize: 12, color: C.text2, margin: '0 0 4px', lineHeight: 1.45 }}>{rule.description}</p>
                      <p style={{ fontSize: 11, color: C.text3, margin: 0, fontFamily: C.mono }}>
                        if {rule.trigger_pattern}
                        {rule.cooldown_minutes && (
                          <span style={{ marginLeft: 10, opacity: 0.7 }}>
                            <Clock size={9} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }} />
                            {rule.cooldown_minutes}m cooldown
                          </span>
                        )}
                      </p>
                    </div>
                    <button
                      onClick={() => toggleRule(rule.id)}
                      style={{
                        flexShrink: 0, position: 'relative',
                        width: 36, height: 20, borderRadius: 999,
                        border: 'none', cursor: 'pointer',
                        background: rule.enabled ? C.amber : C.surface2,
                        transition: 'background 0.2s',
                      }}
                      title={rule.enabled ? 'Disable rule' : 'Enable rule'}
                    >
                      <span style={{
                        position: 'absolute', top: 3,
                        left: rule.enabled ? 17 : 3,
                        width: 14, height: 14, borderRadius: '50%',
                        background: rule.enabled ? 'rgb(14,13,11)' : C.text3,
                        transition: 'left 0.2s',
                      }} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Remediation History */}
      {panel(
        <>
          {panelHeader('Remediation History', <Clock size={14} />)}
          {history.length === 0 ? (
            <div style={{ padding: '40px 24px', textAlign: 'center' }}>
              <ShieldCheck size={28} style={{ color: C.teal, margin: '0 auto 10px', opacity: 0.6 }} />
              <p style={{ fontSize: 13, color: C.text1, fontWeight: 600, margin: '0 0 4px' }}>No executions yet</p>
              <p style={{ fontSize: 11, color: C.text3, margin: 0 }}>
                Click Auto-Fix on an issue card or enable Autonomous Mode
              </p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                    {['', 'Time', 'Rule', 'Action', 'Duration', ''].map((h, i) => (
                      <th key={i} style={{ padding: '8px 16px', fontSize: 9, fontWeight: 700, letterSpacing: '0.09em', color: C.text3, textAlign: 'left', fontFamily: C.mono, whiteSpace: 'nowrap' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {history.map((item, i) => (
                    <HistoryRow key={item.id} item={item} isLast={i === history.length - 1} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

    </div>
  );
}
