import React, { useEffect, useState, useCallback, useRef } from 'react';
import { apiService, authApi } from '../services/api';
import ApiKeyHeatmap from './ApiKeyHeatmap';
import { useAuth } from '../context/AuthContext';
import {
  Shield, AlertTriangle, Users, Key, Clock,
  Lock, Unlock, RefreshCw, Wifi,
  XCircle, ShieldAlert, ShieldCheck,
  UserX, MonitorCheck, Cpu, HardDrive, Thermometer
} from 'lucide-react';

/* ─── Design tokens matching site aesthetic ─── */
const MONO  = { fontFamily: "'IBM Plex Mono', monospace" };
const UI    = { fontFamily: "'Outfit', sans-serif" };
const DISP  = { fontFamily: "'Bebas Neue', sans-serif" };

const surface   = 'rgb(var(--surface))';
const border    = '1px solid rgb(var(--surface-border))';
const textPrim  = 'rgb(var(--text))';
const textMuted = 'rgb(107,99,87)';
const textSub   = 'rgb(168,159,140)';
const amber     = '#F59E0B';
const red       = '#F87171';
const teal      = '#2DD4BF';

/* ─── Shared card wrapper ─── */
function Card({ children, style = {}, glow = false }) {
  return (
    <div style={{
      background: surface,
      border: glow ? `1px solid rgba(245,158,11,0.3)` : border,
      borderRadius: '12px',
      overflow: 'hidden',
      position: 'relative',
      ...(glow && { boxShadow: '0 0 24px rgba(245,158,11,0.06)' }),
      ...style,
    }}>
      {glow && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: '1px',
          background: 'linear-gradient(90deg, transparent, rgba(245,158,11,0.6), transparent)',
        }} />
      )}
      {children}
    </div>
  );
}

/* ─── Section header ─── */
function SectionHeader({ icon, title, count, action }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '8px',
      padding: '14px 18px',
      borderBottom: border,
    }}>
      <span style={{ color: amber, display: 'flex' }}>{icon}</span>
      <span style={{ ...UI, fontSize: '13px', fontWeight: 600, color: textPrim }}>{title}</span>
      {count != null && (
        <span style={{
          ...MONO, fontSize: '10px', color: textMuted,
          background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.15)',
          padding: '2px 8px', borderRadius: '20px', marginLeft: '2px',
        }}>{count}</span>
      )}
      {action && <div style={{ marginLeft: 'auto' }}>{action}</div>}
    </div>
  );
}

/* ─── Info tip button + popover ─── */
function InfoTip({ info }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-flex', zIndex: 10 }}>
      <button
        onClick={e => { e.stopPropagation(); setOpen(v => !v); }}
        aria-label="More info"
        style={{
          width: '16px', height: '16px', borderRadius: '50%', flexShrink: 0,
          border: `1px solid ${open ? 'rgba(245,158,11,0.55)' : 'rgba(168,159,140,0.22)'}`,
          background: open ? 'rgba(245,158,11,0.13)' : 'transparent',
          color: open ? amber : 'rgba(168,159,140,0.45)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', transition: 'all 0.15s',
          ...MONO, fontSize: '9px', fontWeight: 700, lineHeight: 1,
          padding: 0,
        }}
        onMouseEnter={e => {
          if (!open) {
            e.currentTarget.style.borderColor = 'rgba(245,158,11,0.45)';
            e.currentTarget.style.color = amber;
            e.currentTarget.style.background = 'rgba(245,158,11,0.08)';
          }
        }}
        onMouseLeave={e => {
          if (!open) {
            e.currentTarget.style.borderColor = 'rgba(168,159,140,0.22)';
            e.currentTarget.style.color = 'rgba(168,159,140,0.45)';
            e.currentTarget.style.background = 'transparent';
          }
        }}
      >i</button>

      {open && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 7px)',
          right: 0,
          width: '210px',
          zIndex: 200,
          background: 'rgb(18,17,14)',
          border: '1px solid rgba(245,158,11,0.22)',
          borderRadius: '9px',
          padding: '11px 13px',
          boxShadow: '0 12px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(245,158,11,0.04)',
          animation: 'tipIn 0.14s ease',
          pointerEvents: 'auto',
        }}>
          {/* Arrow caret */}
          <div style={{
            position: 'absolute', top: '-5px', right: '4px',
            width: '8px', height: '8px',
            background: 'rgb(18,17,14)',
            border: '1px solid rgba(245,158,11,0.22)',
            borderBottom: 'none', borderRight: 'none',
            transform: 'rotate(45deg)',
          }} />
          <p style={{
            ...UI, fontSize: '11px', lineHeight: 1.6,
            color: textSub, margin: 0,
          }}>{info}</p>
        </div>
      )}
    </div>
  );
}

/* ─── Stat tile ─── */
function StatTile({ icon, label, value, sub, color = textSub, warn = false, ok = false, crit = false, info }) {
  const c = crit ? red : warn ? amber : ok ? teal : color;
  return (
    <div style={{
      background: surface,
      border: crit ? `1px solid rgba(248,113,113,0.2)` : warn ? `1px solid rgba(245,158,11,0.2)` : border,
      borderRadius: '10px',
      padding: '18px 16px',
      position: 'relative',
    }}>
      {/* Top accent line */}
      {(crit || warn || ok) && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: '2px',
          borderRadius: '10px 10px 0 0',
          background: crit
            ? 'linear-gradient(90deg, transparent, rgba(248,113,113,0.7), transparent)'
            : warn
            ? 'linear-gradient(90deg, transparent, rgba(245,158,11,0.7), transparent)'
            : 'linear-gradient(90deg, transparent, rgba(45,212,191,0.7), transparent)',
        }} />
      )}
      {/* Info button — top right */}
      {info && (
        <div style={{ position: 'absolute', top: '10px', right: '10px' }}>
          <InfoTip info={info} />
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
        <span style={{ color: c, display: 'flex', opacity: 0.8 }}>{icon}</span>
        <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: textMuted, textTransform: 'uppercase' }}>
          {label}
        </span>
      </div>
      <div style={{ ...DISP, fontSize: '38px', color: c, lineHeight: 1 }}>{value ?? '—'}</div>
      {sub && <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '5px' }}>{sub}</div>}
    </div>
  );
}

/* ─── Inline refresh button ─── */
function RefreshBtn({ loading, onClick }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      style={{
        display: 'flex', alignItems: 'center', gap: '5px',
        ...MONO, fontSize: '10px', letterSpacing: '0.05em', color: textMuted,
        background: 'transparent', border: '1px solid rgb(var(--surface-border))',
        borderRadius: '6px', padding: '4px 10px', cursor: loading ? 'default' : 'pointer',
        opacity: loading ? 0.5 : 1, transition: 'color 0.15s, border-color 0.15s',
      }}
      onMouseEnter={e => { if (!loading) { e.currentTarget.style.color = amber; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.3)'; } }}
      onMouseLeave={e => { e.currentTarget.style.color = textMuted; e.currentTarget.style.borderColor = 'rgb(var(--surface-border))'; }}
    >
      <RefreshCw size={11} style={{ transition: 'transform 0.4s' }} className={loading ? 'animate-spin' : ''} />
      Refresh
    </button>
  );
}

/* ─── Severity badge ─── */
function SevBadge({ sev }) {
  const cfg = {
    critical: { bg: 'rgba(248,113,113,0.1)', color: red,   border: 'rgba(248,113,113,0.25)' },
    warning:  { bg: 'rgba(245,158,11,0.1)',  color: amber,  border: 'rgba(245,158,11,0.25)' },
    error:    { bg: 'rgba(248,113,113,0.08)', color: red,   border: 'rgba(248,113,113,0.2)' },
  }[sev] || { bg: 'rgba(168,159,140,0.08)', color: textMuted, border: 'rgba(168,159,140,0.15)' };
  return (
    <span style={{
      ...MONO, fontSize: '9px', letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600,
      padding: '2px 7px', borderRadius: '4px',
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
    }}>{sev}</span>
  );
}

/* ─── Category icon map ─── */
const CATEGORY_ICON = {
  performance: <Cpu size={13} />,
  disk:        <HardDrive size={13} />,
  network:     <Wifi size={13} />,
  hardware:    <Thermometer size={13} />,
};

/* ─── Skeleton loader ─── */
function Skeleton({ h = 16, w = '100%', r = 6 }) {
  return (
    <div style={{
      height: h, width: w, borderRadius: r,
      background: 'rgba(168,159,140,0.06)',
      animation: 'pulse 1.5s ease-in-out infinite',
    }} />
  );
}

/* ─── Format relative time ─── */
function relTime(iso) {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1)  return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24)  return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch { return '—'; }
}

/* ─── Role pill ─── */
function RolePill({ role }) {
  const isAdmin = role === 'admin';
  return (
    <span style={{
      ...MONO, fontSize: '9px', letterSpacing: '0.08em', textTransform: 'uppercase',
      padding: '2px 7px', borderRadius: '4px',
      background: isAdmin ? 'rgba(245,158,11,0.1)' : 'rgba(168,159,140,0.08)',
      color: isAdmin ? amber : textMuted,
      border: `1px solid ${isAdmin ? 'rgba(245,158,11,0.2)' : 'rgba(168,159,140,0.12)'}`,
    }}>{role}</span>
  );
}

/* ─────────────────────────────────────────── */
export default function Security() {
  const { user } = useAuth();

  const [overview, setOverview]     = useState(null);
  const [sessions, setSessions]     = useState([]);
  const [loginEvents, setLoginEvents] = useState([]);
  const [anomalies, setAnomalies]   = useState([]);
  const [twoFaStatus, setTwoFaStatus] = useState(null);

  const [loading, setLoading]           = useState(true);
  const [refreshing, setRefreshing]     = useState(false);
  const [revoking, setRevoking]         = useState(null); // session id being revoked
  const [error, setError]               = useState('');
  const [revokeMsg, setRevokeMsg]       = useState('');
  const mounted = useRef(true);

  const fetchAll = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    try {
      const [ov, sess, events, anom, fa] = await Promise.all([
        apiService.getSecurityOverview(),
        apiService.getSecuritySessions(),
        apiService.getLoginEvents(),
        apiService.getAlerts(),
        authApi.get2faStatus().catch(() => null),
      ]);
      if (!mounted.current) return;
      setOverview(ov);
      setSessions(Array.isArray(sess) ? sess : []);
      setLoginEvents(Array.isArray(events) ? events : []);
      setAnomalies(Array.isArray(anom) ? anom : []);
      setTwoFaStatus(fa);
      setError('');
    } catch (e) {
      if (mounted.current) setError('Failed to load security data. Ensure you are signed in as admin.');
    } finally {
      if (mounted.current) { setLoading(false); setRefreshing(false); }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    fetchAll();
    return () => { mounted.current = false; };
  }, [fetchAll]);

  const handleRevoke = useCallback(async (sessionId) => {
    if (revoking) return;
    setRevoking(sessionId);
    setRevokeMsg('');
    try {
      await apiService.revokeSession(sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      setOverview(prev => prev ? { ...prev, active_sessions: Math.max(0, (prev.active_sessions || 1) - 1) } : prev);
      setRevokeMsg('Session revoked.');
    } catch {
      setRevokeMsg('Failed to revoke session.');
    } finally {
      setRevoking(null);
      setTimeout(() => setRevokeMsg(''), 3000);
    }
  }, [revoking]);

  /* ─── Skeleton state ─── */
  if (loading) {
    return (
      <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div>
          <Skeleton h={28} w={160} r={6} />
          <div style={{ marginTop: '6px' }}><Skeleton h={14} w={280} r={4} /></div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
          {[1,2,3,4,5,6].map(i => <Skeleton key={i} h={100} r={10} />)}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <Skeleton h={260} r={12} />
          <Skeleton h={260} r={12} />
        </div>
        <Skeleton h={180} r={12} />
      </div>
    );
  }

  /* ─── Compute security score (0-100) ─── */
  const score = (() => {
    if (!overview) return null;
    let s = 100;
    s -= Math.min(30, (overview.anomalies_active || 0) * 10);
    s -= Math.min(20, (overview.failed_logins_last_hour || 0) * 2);
    s -= Math.min(15, (overview.locked_accounts || 0) * 5);
    s -= Math.min(10, (overview.rate_limited_ips || 0) * 5);
    const totalUsers = overview.total_users || 1;
    const twoFaCoverage = (overview.users_with_2fa || 0) / totalUsers;
    if (twoFaCoverage < 0.5) s -= 15;
    else if (twoFaCoverage < 1) s -= 5;
    return Math.max(0, Math.round(s));
  })();

  const scoreColor = score == null ? textMuted : score >= 80 ? teal : score >= 60 ? amber : red;
  const scoreLabel = score == null ? '—' : score >= 80 ? 'SECURE' : score >= 60 ? 'FAIR' : 'AT RISK';

  /* ─── Failed logins grouped by email (deduplicate events) ─── */
  const failedByEmail = loginEvents
    .filter(e => e.type === 'failed_login')
    .reduce((acc, e) => {
      acc[e.identifier] = (acc[e.identifier] || []);
      acc[e.identifier].push(e.timestamp);
      return acc;
    }, {});

  const ipAttempts = loginEvents
    .filter(e => e.type === 'ip_attempt')
    .reduce((acc, e) => {
      acc[e.identifier] = (acc[e.identifier] || []);
      acc[e.identifier].push(e.timestamp);
      return acc;
    }, {});

  const twoFaCoverage = overview && overview.total_users > 0
    ? Math.round((overview.users_with_2fa / overview.total_users) * 100)
    : 0;

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <style>{`@keyframes tipIn{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}`}</style>

      {/* ─── Page header ─── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ ...UI, fontSize: '22px', fontWeight: 700, color: textPrim, margin: 0 }}>
              Security
            </h2>
            {score != null && (
              <span style={{
                ...MONO, fontSize: '10px', letterSpacing: '0.12em',
                padding: '3px 10px', borderRadius: '20px',
                background: `rgba(${scoreColor === teal ? '45,212,191' : scoreColor === amber ? '245,158,11' : '248,113,113'},0.1)`,
                color: scoreColor,
                border: `1px solid rgba(${scoreColor === teal ? '45,212,191' : scoreColor === amber ? '245,158,11' : '248,113,113'},0.25)`,
              }}>{scoreLabel}</span>
            )}
          </div>
          <p style={{ ...UI, fontSize: '13px', color: textMuted, margin: '4px 0 0' }}>
            Auth, sessions, anomalies and 2FA — admin view.
          </p>
        </div>
        <RefreshBtn loading={refreshing} onClick={() => fetchAll(true)} />
      </div>

      {error && (
        <div style={{
          ...UI, fontSize: '13px', color: red, padding: '10px 14px', borderRadius: '8px',
          background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
        }}>{error}</div>
      )}
      {revokeMsg && (
        <div style={{
          ...MONO, fontSize: '11px', color: teal, padding: '8px 14px', borderRadius: '8px',
          background: 'rgba(45,212,191,0.06)', border: '1px solid rgba(45,212,191,0.2)',
        }}>{revokeMsg}</div>
      )}

      {/* ─── Overview stat tiles ─── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
        <StatTile
          icon={<Shield size={14} />}
          label="Security Score"
          value={score ?? '—'}
          sub={overview?.timestamp ? `as of ${relTime(overview.timestamp)}` : undefined}
          color={scoreColor}
          ok={score >= 80}
          warn={score >= 60 && score < 80}
          crit={score != null && score < 60}
          info="Composite 0–100 score. Starts at 100 and deducts: −10 per active system anomaly (max −30), −2 per failed login attempt (max −20), −5 per locked account (max −15), −5 per rate-limited IP (max −10), −5 to −15 for low 2FA adoption. Green ≥80, amber ≥60, red <60."
        />
        <StatTile
          icon={<Clock size={14} />}
          label="Active Sessions"
          value={overview?.active_sessions ?? '—'}
          sub={`of ${overview?.total_users ?? '?'} users`}
          ok={!overview || overview.active_sessions > 0}
          info="Count of non-expired, non-revoked JWT sessions currently in the database. Each successful login creates a session valid for 24 hours. Sessions can be individually revoked from the Active Sessions panel below."
        />
        <StatTile
          icon={<Key size={14} />}
          label="2FA Coverage"
          value={`${twoFaCoverage}%`}
          sub={`${overview?.users_with_2fa ?? 0} / ${overview?.total_users ?? 0} users`}
          ok={twoFaCoverage >= 80}
          warn={twoFaCoverage > 0 && twoFaCoverage < 80}
          crit={twoFaCoverage === 0 && (overview?.total_users || 0) > 0}
          info="Percentage of active users with TOTP two-factor authentication enabled. Sourced from the users table (totp_enabled = 1). Users can enable 2FA via Settings. Green ≥80%, amber >0%, red = no users have 2FA."
        />
        <StatTile
          icon={<ShieldAlert size={14} />}
          label="Failed Logins/hr"
          value={overview?.failed_logins_last_hour ?? '—'}
          sub="last 60 minutes"
          warn={(overview?.failed_logins_last_hour || 0) > 0 && (overview?.failed_logins_last_hour || 0) < 10}
          crit={(overview?.failed_logins_last_hour || 0) >= 10}
          ok={(overview?.failed_logins_last_hour || 0) === 0}
          info="Failed login attempts recorded by the in-memory rate limiter in the last 60 minutes. Thresholds: 5 failures per email within 15 minutes triggers a lockout; 10 attempts per IP per minute triggers an IP block. Resets automatically when the window expires."
        />
        <StatTile
          icon={<UserX size={14} />}
          label="Locked Accounts"
          value={overview?.locked_accounts ?? '—'}
          sub="rate-limit lockouts"
          crit={(overview?.locked_accounts || 0) > 0}
          ok={(overview?.locked_accounts || 0) === 0}
          info="Accounts that hit the per-email failure threshold: 5 failed attempts within a 15-minute window. The lockout lasts 15 minutes from the first recorded attempt and resets automatically. No manual intervention required unless the count is persistently high."
        />
        <StatTile
          icon={<AlertTriangle size={14} />}
          label="Active Anomalies"
          value={overview?.anomalies_active ?? '—'}
          sub="system threshold alerts"
          crit={(overview?.anomalies_active || 0) > 0}
          ok={(overview?.anomalies_active || 0) === 0}
          info="Real-time alerts triggered when live psutil metrics breach thresholds: CPU ≥75% (critical ≥90%), memory ≥80% (critical ≥90%), disk ≥80% (critical ≥90%), outbound network >2 MB/s, CPU temperature ≥75°C (critical ≥85°C). Refreshes every 30 seconds."
        />
      </div>

      {/* ─── Sessions + Auth Events row ─── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>

        {/* Active Sessions */}
        <Card>
          <SectionHeader
            icon={<MonitorCheck size={14} />}
            title="Active Sessions"
            count={sessions.length}
          />
          <div style={{ maxHeight: '280px', overflowY: 'auto' }}>
            {sessions.length === 0 ? (
              <div style={{ padding: '32px 18px', textAlign: 'center' }}>
                <Clock size={22} style={{ color: textMuted, opacity: 0.4, margin: '0 auto 8px' }} />
                <p style={{ ...UI, fontSize: '13px', color: textMuted }}>No active sessions</p>
              </div>
            ) : sessions.map((s) => {
              const isCurrentUser = s.user_id === user?.id;
              return (
                <div key={s.id} style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '11px 18px',
                  borderBottom: border,
                  background: isCurrentUser ? 'rgba(245,158,11,0.03)' : 'transparent',
                }}>
                  <div style={{
                    width: '30px', height: '30px', borderRadius: '8px',
                    background: isCurrentUser ? 'rgba(245,158,11,0.12)' : 'rgba(168,159,140,0.08)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    <Users size={13} style={{ color: isCurrentUser ? amber : textMuted }} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                      <span style={{ ...UI, fontSize: '12px', fontWeight: 600, color: textPrim }}>
                        {s.username}
                      </span>
                      <RolePill role={s.role} />
                      {isCurrentUser && (
                        <span style={{ ...MONO, fontSize: '9px', color: amber, letterSpacing: '0.08em' }}>you</span>
                      )}
                    </div>
                    <span style={{ ...MONO, fontSize: '10px', color: textMuted }}>
                      {relTime(s.created_at)} · exp {relTime(s.expires_at)}
                    </span>
                  </div>
                  {!isCurrentUser && (
                    <button
                      onClick={() => handleRevoke(s.id)}
                      disabled={revoking === s.id}
                      title="Revoke session"
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        width: '26px', height: '26px', borderRadius: '6px',
                        background: 'transparent', border: '1px solid rgba(248,113,113,0.2)',
                        color: 'rgba(248,113,113,0.5)', cursor: 'pointer',
                        transition: 'all 0.15s', flexShrink: 0,
                        opacity: revoking === s.id ? 0.4 : 1,
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(248,113,113,0.1)'; e.currentTarget.style.color = red; e.currentTarget.style.borderColor = 'rgba(248,113,113,0.4)'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'rgba(248,113,113,0.5)'; e.currentTarget.style.borderColor = 'rgba(248,113,113,0.2)'; }}
                    >
                      {revoking === s.id
                        ? <RefreshCw size={11} className="animate-spin" />
                        : <XCircle size={12} />}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        {/* Auth Events */}
        <Card>
          <SectionHeader
            icon={<ShieldAlert size={14} />}
            title="Auth Events"
            count={loginEvents.length || undefined}
          />
          <div style={{ maxHeight: '280px', overflowY: 'auto' }}>
            {loginEvents.length === 0 ? (
              <div style={{ padding: '32px 18px', textAlign: 'center' }}>
                <ShieldCheck size={22} style={{ color: teal, opacity: 0.5, margin: '0 auto 8px' }} />
                <p style={{ ...UI, fontSize: '13px', color: textMuted }}>No failed auth events in the last hour</p>
              </div>
            ) : loginEvents.map((ev, i) => {
              const isFail = ev.type === 'failed_login';
              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: '10px',
                  padding: '10px 18px',
                  borderBottom: i < loginEvents.length - 1 ? border : 'none',
                }}>
                  <div style={{
                    width: '6px', height: '6px', borderRadius: '50%', marginTop: '5px', flexShrink: 0,
                    background: isFail ? red : amber,
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                      <span style={{ ...MONO, fontSize: '11px', color: isFail ? red : amber, fontWeight: 600 }}>
                        {isFail ? 'FAILED LOGIN' : 'IP THROTTLE'}
                      </span>
                    </div>
                    <p style={{
                      ...MONO, fontSize: '11px', color: textSub,
                      margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>{ev.identifier}</p>
                    <p style={{ ...MONO, fontSize: '10px', color: textMuted, margin: '1px 0 0' }}>
                      {relTime(ev.timestamp)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
          {/* Summary rows */}
          {(Object.keys(failedByEmail).length > 0 || Object.keys(ipAttempts).length > 0) && (
            <div style={{
              borderTop: border, padding: '10px 18px',
              display: 'flex', gap: '16px', flexWrap: 'wrap',
            }}>
              {Object.keys(failedByEmail).length > 0 && (
                <span style={{ ...MONO, fontSize: '10px', color: red }}>
                  {Object.keys(failedByEmail).length} email{Object.keys(failedByEmail).length > 1 ? 's' : ''} failed
                </span>
              )}
              {Object.keys(ipAttempts).length > 0 && (
                <span style={{ ...MONO, fontSize: '10px', color: amber }}>
                  {Object.keys(ipAttempts).length} IP{Object.keys(ipAttempts).length > 1 ? 's' : ''} throttled
                </span>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* ─── 2FA Status panel ─── */}
      <Card glow={!twoFaStatus?.enabled}>
        <SectionHeader icon={<Key size={14} />} title="Two-Factor Authentication" />
        <div style={{ padding: '18px' }}>
          {twoFaStatus == null ? (
            <p style={{ ...UI, fontSize: '13px', color: textMuted }}>Unable to load 2FA status.</p>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
              {/* Your 2FA status */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                padding: '14px 18px', borderRadius: '10px',
                background: twoFaStatus.enabled ? 'rgba(45,212,191,0.06)' : 'rgba(248,113,113,0.06)',
                border: `1px solid ${twoFaStatus.enabled ? 'rgba(45,212,191,0.2)' : 'rgba(248,113,113,0.2)'}`,
                flex: '1 1 220px',
              }}>
                {twoFaStatus.enabled
                  ? <Lock size={20} style={{ color: teal, flexShrink: 0 }} />
                  : <Unlock size={20} style={{ color: red, flexShrink: 0 }} />}
                <div>
                  <div style={{ ...UI, fontSize: '13px', fontWeight: 600, color: twoFaStatus.enabled ? teal : red }}>
                    {twoFaStatus.enabled ? '2FA Enabled' : '2FA Not Enabled'}
                  </div>
                  <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '2px' }}>
                    {twoFaStatus.enabled
                      ? 'Your account is protected with TOTP'
                      : 'Enable 2FA in Settings → Security'}
                  </div>
                </div>
              </div>

              {/* Fleet 2FA overview */}
              {overview && (
                <div style={{
                  display: 'flex', gap: '24px', flex: '1 1 280px', flexWrap: 'wrap',
                }}>
                  <div>
                    <div style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: textMuted, textTransform: 'uppercase', marginBottom: '4px' }}>Fleet Coverage</div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                      <span style={{ ...DISP, fontSize: '32px', color: twoFaCoverage >= 80 ? teal : twoFaCoverage > 0 ? amber : red }}>
                        {twoFaCoverage}%
                      </span>
                    </div>
                    <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '2px' }}>
                      {overview.users_with_2fa} of {overview.total_users} users
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div style={{ flex: 1, minWidth: '120px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '6px' }}>
                    <div style={{ ...MONO, fontSize: '9px', color: textMuted, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                      Adoption
                    </div>
                    <div style={{ height: '6px', borderRadius: '3px', background: 'rgba(168,159,140,0.1)', overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', borderRadius: '3px',
                        width: `${twoFaCoverage}%`,
                        background: twoFaCoverage >= 80 ? teal : twoFaCoverage > 0 ? amber : red,
                        transition: 'width 0.5s ease',
                      }} />
                    </div>
                    <div style={{ ...MONO, fontSize: '10px', color: textMuted }}>
                      {twoFaCoverage >= 80 ? 'Good coverage' : twoFaCoverage > 0 ? 'Needs improvement' : 'No 2FA configured'}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* ─── System Anomalies ─── */}
      <Card>
        <SectionHeader
          icon={<AlertTriangle size={14} />}
          title="System Anomalies"
          count={anomalies.length > 0 ? anomalies.length : undefined}
        />
        {anomalies.length === 0 ? (
          <div style={{ padding: '36px 18px', textAlign: 'center' }}>
            <ShieldCheck size={26} style={{ color: teal, opacity: 0.6, margin: '0 auto 10px' }} />
            <p style={{ ...UI, fontSize: '13px', color: textMuted, margin: 0 }}>All systems normal — no threshold violations</p>
          </div>
        ) : (
          <div>
            {anomalies.map((a, i) => (
              <div key={a.id || i} style={{
                display: 'flex', gap: '14px', padding: '14px 18px',
                borderBottom: i < anomalies.length - 1 ? border : 'none',
                alignItems: 'flex-start',
              }}>
                <div style={{
                  width: '32px', height: '32px', borderRadius: '8px', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: a.severity === 'critical' ? 'rgba(248,113,113,0.1)' : 'rgba(245,158,11,0.1)',
                  color: a.severity === 'critical' ? red : amber,
                }}>
                  {CATEGORY_ICON[a.category] || <AlertTriangle size={13} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '3px' }}>
                    <span style={{ ...UI, fontSize: '13px', fontWeight: 600, color: textPrim }}>
                      {a.message}
                    </span>
                    <SevBadge sev={a.severity} />
                  </div>
                  {a.details && (
                    <p style={{ ...UI, fontSize: '12px', color: textSub, margin: '2px 0' }}>{a.details}</p>
                  )}
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '4px' }}>
                    {a.source && (
                      <span style={{ ...MONO, fontSize: '10px', color: textMuted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        {a.source}
                      </span>
                    )}
                    {a.recommendation && (
                      <span style={{ ...UI, fontSize: '11px', color: textMuted }}>
                        → {a.recommendation}
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ flexShrink: 0, textAlign: 'right' }}>
                  {a.timestamp && (
                    <span style={{ ...MONO, fontSize: '10px', color: textMuted }}>
                      {relTime(typeof a.timestamp === 'number'
                        ? new Date(a.timestamp * 1000).toISOString()
                        : a.timestamp)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ─── API key usage heatmap ─── */}
      <ApiKeyHeatmap hours={24} />

      {/* ─── Auto-refresh indicator ─── */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <span style={{ ...MONO, fontSize: '10px', color: 'rgba(107,99,87,0.5)', letterSpacing: '0.06em' }}>
          AUTO-REFRESH · 30s
        </span>
      </div>
    </div>
  );
}
