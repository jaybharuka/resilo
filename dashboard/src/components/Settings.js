import React, { useEffect, useState, useCallback } from 'react';
import { integrationsApi, authApi, apiService, realTimeService } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  User, Key, Radio, Bell, Shield,
  RefreshCw, Copy, Eye, EyeOff, Cpu, HardDrive,
  LogOut, Lock, Unlock, CheckCircle2,
  Palette, Activity, ShieldCheck, Users,
  MemoryStick, Wifi, ChevronRight, Wrench, SlidersHorizontal
} from 'lucide-react';
import { getThresholds, saveThresholds, THRESHOLD_DEFAULTS } from '../utils/thresholds';

/* ─── Design tokens ─── */
const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };
const DISP = { fontFamily: "'Bebas Neue', sans-serif" };

const surface    = 'rgb(var(--surface))';
const bdr        = '1px solid rgb(var(--surface-border))';
const textPrim   = 'rgb(var(--text))';
const textMuted  = 'rgb(107,99,87)';
const textSub    = 'rgb(168,159,140)';
const amber      = '#F59E0B';
const red        = '#F87171';
const teal       = '#2DD4BF';

/* ─── Section card ─── */
function Section({ icon, title, badge, children }) {
  return (
    <div style={{ background: surface, border: bdr, borderRadius: '12px', overflow: 'hidden' }}>
      <div style={{
        padding: '14px 20px', borderBottom: bdr,
        display: 'flex', alignItems: 'center', gap: '10px',
      }}>
        <span style={{ color: amber, display: 'flex', flexShrink: 0 }}>{icon}</span>
        <span style={{ ...UI, fontSize: '13px', fontWeight: 600, color: textPrim }}>{title}</span>
        {badge && (
          <span style={{
            ...MONO, fontSize: '9px', letterSpacing: '0.1em', textTransform: 'uppercase',
            padding: '2px 8px', borderRadius: '20px',
            background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.15)',
            color: amber,
          }}>{badge}</span>
        )}
      </div>
      <div style={{ padding: '20px' }}>{children}</div>
    </div>
  );
}

/* ─── Row layout ─── */
function Row({ label, hint, children }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      gap: '16px', padding: '12px 0', borderBottom: bdr,
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ ...UI, fontSize: '13px', fontWeight: 500, color: textPrim }}>{label}</div>
        {hint && <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '3px' }}>{hint}</div>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        {children}
      </div>
    </div>
  );
}

/* ─── Input ─── */
function Input({ value, onChange, type = 'text', placeholder, disabled, width, min, max, step }) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      type={type} value={value} onChange={onChange}
      placeholder={placeholder} disabled={disabled}
      min={min} max={max} step={step}
      onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={{
        width: width || '100%',
        background: 'rgba(42,40,32,0.35)',
        border: `1px solid ${focused ? 'rgba(245,158,11,0.4)' : 'rgb(var(--surface-border))'}`,
        borderRadius: '8px', padding: '8px 12px',
        ...MONO, fontSize: '12px', color: textPrim,
        outline: 'none', transition: 'border-color 0.15s',
        opacity: disabled ? 0.5 : 1,
      }}
    />
  );
}

/* ─── Buttons ─── */
function Btn({ children, onClick, disabled, variant = 'ghost', size = 'sm', type = 'button', style: sx = {} }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
    borderRadius: '8px', cursor: disabled ? 'not-allowed' : 'pointer',
    ...UI, fontWeight: 500, opacity: disabled ? 0.5 : 1,
    transition: 'all 0.15s', border: 'none',
    padding: size === 'sm' ? '7px 14px' : '9px 18px',
    fontSize: size === 'sm' ? '12px' : '13px',
  };
  const variants = {
    primary: { background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)', color: '#0C0B09' },
    danger:  { background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.25)', color: red },
    ghost:   { background: 'transparent', border: bdr, color: textSub },
    teal:    { background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.25)', color: teal },
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      style={{ ...base, ...variants[variant], ...sx }}
      onMouseEnter={e => { if (!disabled && variant === 'ghost') { e.currentTarget.style.color = amber; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.3)'; } }}
      onMouseLeave={e => { if (!disabled && variant === 'ghost') { e.currentTarget.style.color = textSub; e.currentTarget.style.borderColor = 'rgb(var(--surface-border))'; } }}
    >{children}</button>
  );
}

/* ─── Toggle switch ─── */
function Toggle({ on, onChange, disabled }) {
  return (
    <button
      onClick={() => !disabled && onChange(!on)}
      style={{
        width: '38px', height: '20px', borderRadius: '10px', border: 'none', cursor: disabled ? 'default' : 'pointer',
        background: on ? 'linear-gradient(135deg, #F59E0B, #D97706)' : 'rgba(107,99,87,0.3)',
        position: 'relative', transition: 'background 0.2s', flexShrink: 0,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <span style={{
        position: 'absolute', top: '3px', left: on ? '21px' : '3px',
        width: '14px', height: '14px', borderRadius: '50%',
        background: on ? '#0C0B09' : 'rgb(107,99,87)',
        transition: 'left 0.2s',
      }} />
    </button>
  );
}

/* ─── Status badge ─── */
function StatusBadge({ ok, label }) {
  return (
    <span style={{
      ...MONO, fontSize: '9px', letterSpacing: '0.1em', textTransform: 'uppercase',
      padding: '3px 8px', borderRadius: '4px',
      background: ok ? 'rgba(45,212,191,0.1)' : 'rgba(248,113,113,0.1)',
      border: `1px solid ${ok ? 'rgba(45,212,191,0.25)' : 'rgba(248,113,113,0.25)'}`,
      color: ok ? teal : red,
    }}>{label}</span>
  );
}

/* ─── Threshold row ─── */
function ThresholdRow({ icon, label, warnKey, critKey, values, onChange }) {
  const warn = values[warnKey] ?? THRESHOLD_DEFAULTS[warnKey];
  const crit = values[critKey] ?? THRESHOLD_DEFAULTS[critKey];
  return (
    <div style={{ padding: '12px 0', borderBottom: bdr }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
        <span style={{ color: textMuted, display: 'flex' }}>{icon}</span>
        <span style={{ ...UI, fontSize: '13px', color: textPrim }}>{label}</span>
      </div>
      {/* Visual scale */}
      <div style={{ position: 'relative', height: '4px', borderRadius: '2px', background: 'rgba(168,159,140,0.1)', marginBottom: '10px' }}>
        <div style={{ position: 'absolute', left: 0, width: `${warn}%`, height: '100%', borderRadius: '2px', background: 'rgba(45,212,191,0.4)' }} />
        <div style={{ position: 'absolute', left: `${warn}%`, width: `${crit - warn}%`, height: '100%', background: 'rgba(245,158,11,0.5)' }} />
        <div style={{ position: 'absolute', left: `${crit}%`, right: 0, height: '100%', borderRadius: '0 2px 2px 0', background: 'rgba(248,113,113,0.5)' }} />
        {/* Markers */}
        <div style={{ position: 'absolute', left: `${warn}%`, top: '-3px', width: '2px', height: '10px', background: amber, transform: 'translateX(-1px)' }} />
        <div style={{ position: 'absolute', left: `${crit}%`, top: '-3px', width: '2px', height: '10px', background: red, transform: 'translateX(-1px)' }} />
      </div>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ ...MONO, fontSize: '10px', color: amber }}>WARN</span>
          <Input
            type="number" value={warn} min={1} max={crit - 1} step={1} width="70px"
            onChange={e => {
              const v = Math.min(Number(e.target.value), crit - 1);
              onChange(warnKey, Math.max(1, v));
            }}
          />
          <span style={{ ...MONO, fontSize: '10px', color: textMuted }}>%</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ ...MONO, fontSize: '10px', color: red }}>CRIT</span>
          <Input
            type="number" value={crit} min={warn + 1} max={100} step={1} width="70px"
            onChange={e => {
              const v = Math.max(Number(e.target.value), warn + 1);
              onChange(critKey, Math.min(100, v));
            }}
          />
          <span style={{ ...MONO, fontSize: '10px', color: textMuted }}>%</span>
        </div>
      </div>
    </div>
  );
}

/* ─── Copy button ─── */
function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }); }}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        ...MONO, fontSize: '10px', color: copied ? teal : textMuted,
        background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px 6px',
        transition: 'color 0.15s',
      }}
    >
      {copied ? <CheckCircle2 size={12} /> : <Copy size={12} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

/* ─── Notification result ─── */
function NotifResult({ res }) {
  if (!res) return null;
  return (
    <div style={{
      marginTop: '10px', padding: '8px 12px', borderRadius: '8px',
      background: res.ok ? 'rgba(45,212,191,0.06)' : 'rgba(248,113,113,0.06)',
      border: `1px solid ${res.ok ? 'rgba(45,212,191,0.2)' : 'rgba(248,113,113,0.2)'}`,
      ...MONO, fontSize: '11px',
      color: res.ok ? teal : red,
    }}>
      {res.ok ? '✓ Test sent successfully' : `✗ ${res.error || res.response_text || 'Unknown error'}`}
    </div>
  );
}

/* ════════════════════════════════════════════ */
export default function Settings() {
  const { user, role, logout } = useAuth();
  const { theme, cycleTheme } = useTheme();

  /* ── Account / password ── */
  const [pwForm, setPwForm] = useState({ newPw: '', confirm: '', show: false, busy: false, error: '' });

  /* ── 2FA ── */
  const [twoFa, setTwoFa] = useState({
    status: null, loading: true,
    phase: 'idle',   // idle | setup | disabling
    setupData: null, // { secret, uri }
    code: '', busy: false, error: '',
  });

  /* ── Realtime ── */
  const [pollMs, setPollMs]     = useState(realTimeService.intervalMs || 5000);
  const [sse, setSse]           = useState(realTimeService.getSSEStatus());
  const [health, setHealth]     = useState(null);
  const [healthBusy, setHealthBusy] = useState(false);

  /* ── Thresholds ── */
  const [thresh, setThresh]     = useState(getThresholds());
  const [threshDirty, setThreshDirty] = useState(false);

  /* ── Remediation (admin) ── */
  const [remSettings, setRemSettings] = useState({ autonomous: false, dryRun: true, loading: true });

  /* ── Notifications ── */
  const [slack, setSlack]   = useState({ webhook: '', busy: false, result: null });
  const [discord, setDiscord] = useState({ webhook: '', busy: false, result: null });

  /* ── Connectivity ── */
  const [apiBase, setApiBase] = useState(() => {
    try { return localStorage.getItem('aiops:apiBase') || ''; } catch { return ''; }
  });

  /* ────────────────── init ────────────────── */
  useEffect(() => {
    /* 2FA status */
    authApi.get2faStatus()
      .then(s => setTwoFa(p => ({ ...p, status: s, loading: false })))
      .catch(() => setTwoFa(p => ({ ...p, loading: false })));

    /* Remediation autonomous mode */
    if (role === 'admin') {
      apiService.getAutonomousMode()
        .then(d => setRemSettings(p => ({ ...p, autonomous: d?.autonomous_mode ?? false, loading: false })))
        .catch(() => setRemSettings(p => ({ ...p, loading: false })));
    }

    /* SSE listener */
    const unsub = realTimeService.subscribe('sse-status', st => setSse(st));
    setSse(realTimeService.getSSEStatus());

    /* dry-run default from localStorage */
    try {
      const dr = localStorage.getItem('aiops:dryRunDefault');
      if (dr !== null) setRemSettings(p => ({ ...p, dryRun: dr !== 'false' }));
    } catch {}

    return () => { try { unsub?.(); } catch {} };
  }, [role]);

  /* ────────────────── handlers ────────────────── */

  /* Change password */
  const handleChangePassword = useCallback(async () => {
    const { newPw, confirm } = pwForm;
    if (newPw.length < 8) return setPwForm(p => ({ ...p, error: 'Minimum 8 characters.' }));
    if (newPw !== confirm) return setPwForm(p => ({ ...p, error: 'Passwords do not match.' }));
    setPwForm(p => ({ ...p, busy: true, error: '' }));
    try {
      await authApi.changePassword(newPw);
      toast.success('Password updated.');
      setPwForm({ newPw: '', confirm: '', show: false, busy: false, error: '' });
    } catch (e) {
      const msg = e?.response?.data?.error || 'Update failed.';
      setPwForm(p => ({ ...p, busy: false, error: msg }));
    }
  }, [pwForm]);

  /* 2FA setup */
  const handle2faSetup = useCallback(async () => {
    setTwoFa(p => ({ ...p, busy: true, error: '' }));
    try {
      const data = await authApi.setup2fa();
      setTwoFa(p => ({ ...p, busy: false, phase: 'setup', setupData: data, code: '' }));
    } catch { setTwoFa(p => ({ ...p, busy: false, error: 'Setup failed. Try again.' })); }
  }, []);

  const handle2faEnable = useCallback(async () => {
    setTwoFa(p => ({ ...p, busy: true, error: '' }));
    try {
      await authApi.enable2fa(twoFa.code);
      setTwoFa(p => ({ ...p, busy: false, phase: 'idle', setupData: null, code: '',
        status: { enabled: true, configured: true }, error: '' }));
      toast.success('2FA enabled.');
    } catch { setTwoFa(p => ({ ...p, busy: false, error: 'Invalid code — try again.' })); }
  }, [twoFa.code]);

  const handle2faDisable = useCallback(async () => {
    setTwoFa(p => ({ ...p, busy: true, error: '' }));
    try {
      await authApi.disable2fa(twoFa.code);
      setTwoFa(p => ({ ...p, busy: false, phase: 'idle', code: '',
        status: { enabled: false, configured: false }, error: '' }));
      toast.success('2FA disabled.');
    } catch { setTwoFa(p => ({ ...p, busy: false, error: 'Invalid code — try again.' })); }
  }, [twoFa.code]);

  /* Thresholds */
  const handleThreshChange = (key, val) => {
    setThresh(prev => ({ ...prev, [key]: val }));
    setThreshDirty(true);
  };
  const handleThreshSave = () => {
    if (saveThresholds(thresh)) {
      setThreshDirty(false);
      toast.success('Thresholds saved — Dashboard updates on next refresh.');
    } else {
      toast.error('Failed to save thresholds.');
    }
  };
  const handleThreshReset = () => {
    setThresh({ ...THRESHOLD_DEFAULTS });
    setThreshDirty(true);
  };

  /* Remediation */
  const handleAutonomousToggle = useCallback(async (val) => {
    setRemSettings(p => ({ ...p, autonomous: val }));
    try {
      await apiService.setAutonomousMode(val);
      toast.success(`Autonomous mode ${val ? 'enabled' : 'disabled'}.`);
    } catch {
      setRemSettings(p => ({ ...p, autonomous: !val }));
      toast.error('Failed to update autonomous mode.');
    }
  }, []);

  const handleDryRunToggle = (val) => {
    setRemSettings(p => ({ ...p, dryRun: val }));
    try { localStorage.setItem('aiops:dryRunDefault', String(val)); } catch {}
    toast.success(`Default dry-run ${val ? 'on' : 'off'}.`);
  };

  /* Health check */
  const checkHealth = useCallback(async () => {
    setHealthBusy(true);
    try {
      const res = await apiService.checkHealth();
      setHealth(res);
    } catch { setHealth({ status: 'error' }); }
    finally { setHealthBusy(false); }
  }, []);

  /* Notifications */
  const testSlack = async () => {
    setSlack(p => ({ ...p, busy: true, result: null }));
    try {
      const res = await integrationsApi.testSlack({ webhook_url: slack.webhook || undefined });
      setSlack(p => ({ ...p, busy: false, result: res }));
    } catch (e) { setSlack(p => ({ ...p, busy: false, result: { ok: false, error: e.message } })); }
  };
  const testDiscord = async () => {
    setDiscord(p => ({ ...p, busy: true, result: null }));
    try {
      const res = await integrationsApi.testDiscord({ webhook_url: discord.webhook || undefined });
      setDiscord(p => ({ ...p, busy: false, result: res }));
    } catch (e) { setDiscord(p => ({ ...p, busy: false, result: { ok: false, error: e.message } })); }
  };

  /* Connectivity */
  const applyApiBase = () => {
    try {
      if (apiBase.trim()) localStorage.setItem('aiops:apiBase', apiBase.trim());
      else localStorage.removeItem('aiops:apiBase');
      toast.success('API endpoint saved — reloading…');
      setTimeout(() => window.location.reload(), 700);
    } catch { toast.error('Failed to save.'); }
  };

  const currentApiUrl = (() => {
    try { return localStorage.getItem('aiops:apiBase') || window.location.origin; } catch { return window.location.origin; }
  })();

  /* ── theme label ── */
  const themeLabel = theme === 'dark' ? 'Ops Dark' : theme === 'high-contrast' ? 'High Contrast' : 'Light';
  const themeNext  = theme === 'dark' ? 'Light' : theme === 'light' ? 'High Contrast' : 'Ops Dark';

  /* ── initials ── */
  const initials = (() => {
    const n = user?.full_name || user?.username || user?.email || '';
    return n.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2) || '??';
  })();

  /* ── format TOTP secret ── */
  const fmtSecret = (s = '') => s.match(/.{1,4}/g)?.join(' ') || s;

  return (
    <div style={{ padding: '24px', maxWidth: '760px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <style>{`
        @keyframes sIn { from { opacity:0; transform:translateY(8px) } to { opacity:1; transform:translateY(0) } }
        .s-section { animation: sIn 0.2s ease both; }
      `}</style>

      {/* ─── Header ─── */}
      <div>
        <h2 style={{ ...UI, fontSize: '22px', fontWeight: 700, color: textPrim, margin: 0 }}>Settings</h2>
        <p style={{ ...MONO, fontSize: '11px', color: textMuted, margin: '4px 0 0', letterSpacing: '0.04em' }}>
          Account, integrations, thresholds and preferences.
        </p>
      </div>

      {/* ══ 1. ACCOUNT ══ */}
      <div className="s-section" style={{ animationDelay: '0ms' }}>
        <Section icon={<User size={14} />} title="Account">
          {/* User identity */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '14px',
            padding: '14px 16px', marginBottom: '16px', borderRadius: '10px',
            background: 'rgba(245,158,11,0.04)', border: '1px solid rgba(245,158,11,0.12)',
          }}>
            <div style={{
              width: '42px', height: '42px', borderRadius: '10px', flexShrink: 0,
              background: 'linear-gradient(135deg, rgba(245,158,11,0.2), rgba(245,158,11,0.08))',
              border: '1px solid rgba(245,158,11,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              ...DISP, fontSize: '20px', color: amber,
            }}>{initials}</div>
            <div>
              <div style={{ ...UI, fontSize: '14px', fontWeight: 600, color: textPrim }}>
                {user?.full_name || user?.username || '—'}
              </div>
              <div style={{ ...MONO, fontSize: '11px', color: textSub, marginTop: '2px' }}>
                {user?.email}
              </div>
              <div style={{ marginTop: '4px' }}>
                <span style={{
                  ...MONO, fontSize: '9px', letterSpacing: '0.1em', textTransform: 'uppercase',
                  padding: '2px 8px', borderRadius: '4px',
                  background: role === 'admin' ? 'rgba(245,158,11,0.1)' : 'rgba(168,159,140,0.08)',
                  color: role === 'admin' ? amber : textMuted,
                  border: `1px solid ${role === 'admin' ? 'rgba(245,158,11,0.2)' : 'rgba(168,159,140,0.12)'}`,
                }}>{role}</span>
              </div>
            </div>
          </div>

          {/* Change password */}
          <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.08em', color: textMuted, marginBottom: '10px', textTransform: 'uppercase' }}>
            Change Password
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ position: 'relative' }}>
              <Input
                type={pwForm.show ? 'text' : 'password'}
                placeholder="New password (min 8 characters)"
                value={pwForm.newPw}
                onChange={e => setPwForm(p => ({ ...p, newPw: e.target.value, error: '' }))}
              />
              <button
                onClick={() => setPwForm(p => ({ ...p, show: !p.show }))}
                style={{
                  position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer', color: textMuted,
                  display: 'flex', padding: '2px',
                }}
              >
                {pwForm.show ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
            <Input
              type={pwForm.show ? 'text' : 'password'}
              placeholder="Confirm new password"
              value={pwForm.confirm}
              onChange={e => setPwForm(p => ({ ...p, confirm: e.target.value, error: '' }))}
            />
            {pwForm.error && (
              <span style={{ ...MONO, fontSize: '10px', color: red }}>{pwForm.error}</span>
            )}
            <div>
              <Btn variant="primary" onClick={handleChangePassword} disabled={pwForm.busy || !pwForm.newPw}>
                {pwForm.busy ? <><RefreshCw size={12} className="animate-spin" /> Updating…</> : 'Update Password'}
              </Btn>
            </div>
          </div>

          {/* Theme */}
          <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: bdr, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ ...UI, fontSize: '13px', color: textPrim }}>Interface Theme</div>
              <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '2px' }}>
                Current: <span style={{ color: amber }}>{themeLabel}</span> · Next: {themeNext}
              </div>
            </div>
            <Btn variant="ghost" onClick={cycleTheme}>
              <Palette size={12} /> Switch Theme
            </Btn>
          </div>

          {/* Logout */}
          <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: bdr, display: 'flex', justifyContent: 'flex-end' }}>
            <Btn variant="danger" onClick={logout}>
              <LogOut size={12} /> Sign Out
            </Btn>
          </div>
        </Section>
      </div>

      {/* ══ 2. TWO-FACTOR AUTH ══ */}
      <div className="s-section" style={{ animationDelay: '40ms' }}>
        <Section icon={<Key size={14} />} title="Two-Factor Authentication"
          badge={twoFa.status?.enabled ? 'enabled' : undefined}>
          {twoFa.loading ? (
            <div style={{ height: '48px', background: 'rgba(168,159,140,0.06)', borderRadius: '8px', animation: 'pulse 1.5s infinite' }} />
          ) : twoFa.phase === 'idle' ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
                {twoFa.status?.enabled
                  ? <Lock size={18} style={{ color: teal }} />
                  : <Unlock size={18} style={{ color: red }} />}
                <div>
                  <div style={{ ...UI, fontSize: '13px', fontWeight: 600, color: twoFa.status?.enabled ? teal : red }}>
                    {twoFa.status?.enabled ? 'Authenticator app connected' : 'Two-factor authentication is off'}
                  </div>
                  <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '2px' }}>
                    {twoFa.status?.enabled
                      ? 'Your account requires a TOTP code on each sign-in.'
                      : 'Enable TOTP to add a second layer of security to your account.'}
                  </div>
                </div>
              </div>
              {twoFa.status?.enabled ? (
                <Btn variant="danger" onClick={() => setTwoFa(p => ({ ...p, phase: 'disabling', code: '', error: '' }))}>
                  <Unlock size={12} /> Disable 2FA
                </Btn>
              ) : (
                <Btn variant="primary" onClick={handle2faSetup} disabled={twoFa.busy}>
                  {twoFa.busy ? <><RefreshCw size={12} className="animate-spin" /> Setting up…</> : <><Key size={12} /> Set Up 2FA</>}
                </Btn>
              )}
              {twoFa.error && <div style={{ ...MONO, fontSize: '10px', color: red, marginTop: '8px' }}>{twoFa.error}</div>}
            </div>
          ) : twoFa.phase === 'setup' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ ...MONO, fontSize: '10px', color: amber, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                Step 1 — Add this key to your authenticator app
              </div>
              {/* Secret display */}
              <div style={{
                background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)',
                borderRadius: '10px', padding: '14px 16px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ ...MONO, fontSize: '10px', color: textMuted, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Secret Key</span>
                  <CopyBtn text={twoFa.setupData?.secret || ''} />
                </div>
                <div style={{ ...MONO, fontSize: '16px', letterSpacing: '0.2em', color: amber, wordBreak: 'break-all' }}>
                  {fmtSecret(twoFa.setupData?.secret)}
                </div>
                <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '8px' }}>
                  Google Authenticator / Authy / 1Password → Add → Manual entry
                </div>
              </div>
              {/* otpauth URI */}
              {twoFa.setupData?.uri && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{
                    flex: 1, background: 'rgba(42,40,32,0.35)', border: bdr, borderRadius: '8px',
                    padding: '6px 10px', ...MONO, fontSize: '10px', color: textMuted,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>{twoFa.setupData.uri}</div>
                  <CopyBtn text={twoFa.setupData.uri} />
                </div>
              )}
              <div style={{ ...MONO, fontSize: '10px', color: amber, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                Step 2 — Enter the 6-digit code from your app
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <Input
                  value={twoFa.code} placeholder="000000"
                  onChange={e => setTwoFa(p => ({ ...p, code: e.target.value.replace(/\D/g, '').slice(0, 6), error: '' }))}
                  width="120px"
                />
                <Btn variant="primary" onClick={handle2faEnable} disabled={twoFa.busy || twoFa.code.length < 6}>
                  {twoFa.busy ? <><RefreshCw size={12} className="animate-spin" /> Verifying…</> : 'Verify & Enable'}
                </Btn>
                <Btn variant="ghost" onClick={() => setTwoFa(p => ({ ...p, phase: 'idle', setupData: null, code: '', error: '' }))}>
                  Cancel
                </Btn>
              </div>
              {twoFa.error && <div style={{ ...MONO, fontSize: '10px', color: red }}>{twoFa.error}</div>}
            </div>
          ) : twoFa.phase === 'disabling' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ ...UI, fontSize: '13px', color: textSub }}>
                Enter the 6-digit code from your authenticator app to confirm disabling 2FA.
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <Input
                  value={twoFa.code} placeholder="000000"
                  onChange={e => setTwoFa(p => ({ ...p, code: e.target.value.replace(/\D/g, '').slice(0, 6), error: '' }))}
                  width="120px"
                />
                <Btn variant="danger" onClick={handle2faDisable} disabled={twoFa.busy || twoFa.code.length < 6}>
                  {twoFa.busy ? <><RefreshCw size={12} className="animate-spin" /> Disabling…</> : 'Confirm Disable'}
                </Btn>
                <Btn variant="ghost" onClick={() => setTwoFa(p => ({ ...p, phase: 'idle', code: '', error: '' }))}>
                  Cancel
                </Btn>
              </div>
              {twoFa.error && <div style={{ ...MONO, fontSize: '10px', color: red }}>{twoFa.error}</div>}
            </div>
          ) : null}
        </Section>
      </div>

      {/* ══ 3. REALTIME ══ */}
      <div className="s-section" style={{ animationDelay: '80ms' }}>
        <Section icon={<Radio size={14} />} title="Realtime & Session">
          <Row
            label="Polling Interval"
            hint="Background refresh cadence for system metrics, insights, alerts, and processes"
          >
            <Input type="number" value={pollMs} onChange={e => setPollMs(Number(e.target.value))}
              min={1000} step={500} width="90px" />
            <span style={{ ...MONO, fontSize: '10px', color: textMuted }}>ms</span>
            <Btn variant="primary" size="sm" onClick={() => { realTimeService.setIntervalMs(pollMs); toast.success(`Polling set to ${pollMs}ms`); }}>
              Apply
            </Btn>
          </Row>
          <Row
            label="Server-Sent Events"
            hint="Real-time push from backend — reduces polling load when connected"
          >
            <StatusBadge ok={sse.connected} label={sse.enabled ? (sse.connected ? 'connected' : 'pending') : 'disabled'} />
            <Toggle on={sse.enabled} onChange={v => { realTimeService.setSSEnabled(v); toast.success(`SSE ${v ? 'enabled' : 'disabled'}`); }} />
          </Row>
          <Row label="Backend Health" hint="Check connection to backend API server">
            {health && (
              <StatusBadge
                ok={health.status === 'ok' || health.status === 'healthy'}
                label={health.status}
              />
            )}
            {health?.timestamp && (
              <span style={{ ...MONO, fontSize: '10px', color: textMuted }}>
                {new Date(health.timestamp).toLocaleTimeString()}
              </span>
            )}
            <Btn variant="ghost" size="sm" onClick={checkHealth} disabled={healthBusy}>
              {healthBusy ? <RefreshCw size={11} className="animate-spin" /> : <Activity size={11} />}
              {healthBusy ? 'Checking…' : 'Check'}
            </Btn>
          </Row>
          <div style={{ paddingTop: '12px' }}>
            <Btn variant="ghost" size="sm" onClick={async () => {
              const t = toast.loading('Refreshing session…');
              try { const res = await authApi.refresh(); localStorage.setItem('aiops:token', res.token); toast.success('Session refreshed', { id: t }); }
              catch { toast.error('Session refresh failed', { id: t }); }
            }}>
              <RefreshCw size={11} /> Refresh Session Token
            </Btn>
          </div>
        </Section>
      </div>

      {/* ══ 4. THRESHOLDS ══ */}
      <div className="s-section" style={{ animationDelay: '120ms' }}>
        <Section icon={<SlidersHorizontal size={14} />} title="Alert Thresholds"
          badge={threshDirty ? 'unsaved' : undefined}>
          <p style={{ ...UI, fontSize: '12px', color: textMuted, margin: '0 0 14px' }}>
            Controls when Dashboard, Security, and Anomaly panels classify metrics as warning or critical.
            Changes persist in your browser and take effect on the next data refresh.
          </p>
          <ThresholdRow icon={<Cpu size={13} />} label="CPU Usage"
            warnKey="cpu_warn" critKey="cpu_crit" values={thresh} onChange={handleThreshChange} />
          <ThresholdRow icon={<MemoryStick size={13} />} label="Memory Usage"
            warnKey="mem_warn" critKey="mem_crit" values={thresh} onChange={handleThreshChange} />
          <ThresholdRow icon={<HardDrive size={13} />} label="Disk Usage"
            warnKey="disk_warn" critKey="disk_crit" values={thresh} onChange={handleThreshChange} />
          <div style={{ display: 'flex', gap: '8px', paddingTop: '14px' }}>
            <Btn variant="primary" onClick={handleThreshSave} disabled={!threshDirty}>
              <CheckCircle2 size={12} /> Save Thresholds
            </Btn>
            <Btn variant="ghost" onClick={handleThreshReset}>
              Reset to Defaults
            </Btn>
          </div>
          {/* Legend */}
          <div style={{ display: 'flex', gap: '16px', marginTop: '12px', flexWrap: 'wrap' }}>
            {[['teal', 'Normal'], ['amber', 'Warning'], ['red', 'Critical']].map(([c, lbl]) => (
              <div key={c} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '2px', background: c === 'teal' ? teal : c === 'amber' ? amber : red, opacity: 0.6 }} />
                <span style={{ ...MONO, fontSize: '10px', color: textMuted }}>{lbl}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>

      {/* ══ 5. REMEDIATION (admin) ══ */}
      {role === 'admin' && (
        <div className="s-section" style={{ animationDelay: '160ms' }}>
          <Section icon={<Wrench size={14} />} title="Remediation" badge="admin">
            <Row
              label="Autonomous Mode"
              hint="Automatically execute fixes for LOW and HIGH severity issues — HIGH and CRITICAL always require manual confirmation"
            >
              {remSettings.loading
                ? <div style={{ width: '38px', height: '20px', background: 'rgba(168,159,140,0.1)', borderRadius: '10px' }} />
                : <Toggle on={remSettings.autonomous} onChange={handleAutonomousToggle} />}
            </Row>
            <Row
              label="Default Dry-Run"
              hint="Pre-check all memory and disk cleanup actions before executing — shows what would be changed"
            >
              <Toggle on={remSettings.dryRun} onChange={handleDryRunToggle} />
            </Row>
            <div style={{ paddingTop: '12px' }}>
              <Link to="/remediation" style={{ textDecoration: 'none' }}>
                <Btn variant="ghost" size="sm">
                  <Wrench size={11} /> Manage Remediation Rules <ChevronRight size={11} />
                </Btn>
              </Link>
            </div>
          </Section>
        </div>
      )}

      {/* ══ 6. NOTIFICATIONS ══ */}
      <div className="s-section" style={{ animationDelay: '200ms' }}>
        <Section icon={<Bell size={14} />} title="Notifications">
          {/* Slack */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <span style={{ ...MONO, fontSize: '10px', color: textSub, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Slack</span>
            </div>
            <p style={{ ...UI, fontSize: '12px', color: textMuted, margin: '0 0 8px' }}>
              Webhook URL — or set <code style={{ ...MONO, fontSize: '11px', background: 'rgba(168,159,140,0.1)', padding: '1px 5px', borderRadius: '4px' }}>SLACK_ALERTS_WEBHOOK</code> in backend environment.
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Input value={slack.webhook} onChange={e => setSlack(p => ({ ...p, webhook: e.target.value }))}
                placeholder="https://hooks.slack.com/services/…" type="url" />
              <Btn variant="primary" onClick={testSlack} disabled={slack.busy} sx={{ flexShrink: 0 }}>
                {slack.busy ? <RefreshCw size={11} className="animate-spin" /> : null}
                {slack.busy ? 'Sending…' : 'Test'}
              </Btn>
            </div>
            <NotifResult res={slack.result} />
          </div>
          {/* Discord */}
          <div style={{ borderTop: bdr, paddingTop: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <span style={{ ...MONO, fontSize: '10px', color: textSub, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Discord</span>
            </div>
            <p style={{ ...UI, fontSize: '12px', color: textMuted, margin: '0 0 8px' }}>
              Webhook URL — or set <code style={{ ...MONO, fontSize: '11px', background: 'rgba(168,159,140,0.1)', padding: '1px 5px', borderRadius: '4px' }}>DISCORD_WEBHOOK_URL</code> in backend environment.
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Input value={discord.webhook} onChange={e => setDiscord(p => ({ ...p, webhook: e.target.value }))}
                placeholder="https://discord.com/api/webhooks/…" type="url" />
              <Btn variant="primary" onClick={testDiscord} disabled={discord.busy} sx={{ flexShrink: 0 }}>
                {discord.busy ? <RefreshCw size={11} className="animate-spin" /> : null}
                {discord.busy ? 'Sending…' : 'Test'}
              </Btn>
            </div>
            <NotifResult res={discord.result} />
          </div>
        </Section>
      </div>

      {/* ══ 7. CONNECTIVITY ══ */}
      <div className="s-section" style={{ animationDelay: '240ms' }}>
        <Section icon={<Wifi size={14} />} title="Connectivity">
          <Row label="Current Endpoint" hint="Active API base URL">
            <span style={{ ...MONO, fontSize: '11px', color: teal }}>{currentApiUrl}</span>
          </Row>
          <div style={{ marginTop: '14px' }}>
            <div style={{ ...UI, fontSize: '13px', color: textPrim, marginBottom: '6px' }}>Override API Base URL</div>
            <p style={{ ...UI, fontSize: '12px', color: textMuted, margin: '0 0 8px' }}>
              Use when frontend and backend are on different hosts or ports. Leave blank to auto-detect.
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Input value={apiBase} onChange={e => setApiBase(e.target.value)}
                placeholder="http://192.168.1.x:5000" type="url" />
              <Btn variant="primary" onClick={applyApiBase} sx={{ flexShrink: 0 }}>
                Apply & Reload
              </Btn>
            </div>
          </div>
        </Section>
      </div>

      {/* ══ 8. ADMIN ══ */}
      {role === 'admin' && (
        <div className="s-section" style={{ animationDelay: '280ms' }}>
          <Section icon={<ShieldCheck size={14} />} title="Admin" badge="admin">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <Link to="/invites" style={{ textDecoration: 'none' }}>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 14px', borderRadius: '9px',
                  background: 'rgba(245,158,11,0.04)', border: '1px solid rgba(245,158,11,0.12)',
                  transition: 'background 0.15s',
                  cursor: 'pointer',
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(245,158,11,0.08)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(245,158,11,0.04)'}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Users size={14} style={{ color: amber }} />
                    <div>
                      <div style={{ ...UI, fontSize: '13px', fontWeight: 500, color: textPrim }}>Invite Users</div>
                      <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '2px' }}>
                        Generate one-time invite tokens for secure onboarding
                      </div>
                    </div>
                  </div>
                  <ChevronRight size={14} style={{ color: textMuted }} />
                </div>
              </Link>

              <Link to="/security" style={{ textDecoration: 'none' }}>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 14px', borderRadius: '9px',
                  background: 'rgba(248,113,113,0.04)', border: '1px solid rgba(248,113,113,0.12)',
                  transition: 'background 0.15s', cursor: 'pointer',
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(248,113,113,0.08)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(248,113,113,0.04)'}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Shield size={14} style={{ color: red }} />
                    <div>
                      <div style={{ ...UI, fontSize: '13px', fontWeight: 500, color: textPrim }}>Security Center</div>
                      <div style={{ ...MONO, fontSize: '10px', color: textMuted, marginTop: '2px' }}>
                        Active sessions, auth events, 2FA coverage, anomalies
                      </div>
                    </div>
                  </div>
                  <ChevronRight size={14} style={{ color: textMuted }} />
                </div>
              </Link>
            </div>
          </Section>
        </div>
      )}

      {/* ─── Footer ─── */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '4px' }}>
        <span style={{ ...MONO, fontSize: '10px', color: 'rgba(107,99,87,0.4)', letterSpacing: '0.06em' }}>
          RESILO · ADMIN CONSOLE
        </span>
      </div>
    </div>
  );
}
