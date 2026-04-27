import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { authApi } from '../services/api';
import { Activity, Eye, EyeOff, Loader } from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const UI      = { fontFamily: "'Outfit', sans-serif" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const C = {
  amber: '#F59E0B', amberDim: '#D97706', red: '#F87171',
  green: '#4ADE80', surface: 'rgb(22,20,16)', border: 'rgba(245,158,11,0.14)',
  text1: '#F5F0E8', text3: '#6B6357', text4: '#4A443D',
};

function _parseError(err) {
  if (!err) return null;
  const s   = String(err?.response?.status || err?.status || '');
  const msg = err?.response?.data?.detail || err?.message || String(err);
  const low = msg.toLowerCase();
  if (s === '401' || low.includes('invalid') || low.includes('incorrect') || low.includes('credentials'))
    return 'Invalid email or password.';
  if (s === '403' || low.includes('locked') || low.includes('account is locked'))
    return 'Account is temporarily locked. Please try again in 15 minutes.';
  if (s === '409' || low.includes('already exists') || low.includes('already'))
    return 'An account with this email already exists.';
  if (s === '429' || low.includes('too many') || low.includes('rate limit'))
    return 'Too many attempts — wait a few minutes before trying again.';
  if (s === '404' || low.includes('not found'))
    return 'Auth service unavailable. Please check the backend is running.';
  if (low.includes('network') || low.includes('econnrefused') || low.includes('failed to fetch') || low.includes('cannot reach'))
    return 'Unable to connect to the server. Is the backend running?';
  return msg || 'Something went wrong. Please try again.';
}

const inputStyle = {
  width: '100%', boxSizing: 'border-box',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(245,240,232,0.08)',
  borderRadius: '8px', padding: '10px 12px',
  fontSize: '14px', color: C.text1, ...UI,
  outline: 'none', transition: 'border-color 0.15s, box-shadow 0.15s',
};

function Input({ label, type = 'text', value, onChange, placeholder, autoComplete, disabled, autoFocus, inputRef }) {
  const [show, setShow] = useState(false);
  const isPw = type === 'password';
  return (
    <div>
      <label style={{ display: 'block', ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: C.text3, marginBottom: '7px' }}>
        {label}
      </label>
      <div style={{ position: 'relative' }}>
        <input
          ref={inputRef}
          type={isPw && show ? 'text' : type}
          required value={value} onChange={e => onChange(e.target.value)}
          placeholder={placeholder} autoComplete={autoComplete}
          disabled={disabled} autoFocus={autoFocus}
          style={{ ...inputStyle, opacity: disabled ? 0.6 : 1, paddingRight: isPw ? '38px' : '12px' }}
          onFocus={e => { e.target.style.borderColor = 'rgba(245,158,11,0.45)'; e.target.style.boxShadow = '0 0 0 3px rgba(245,158,11,0.08)'; }}
          onBlur={e => { e.target.style.borderColor = 'rgba(245,240,232,0.08)'; e.target.style.boxShadow = 'none'; }}
        />
        {isPw && (
          <button type="button" onClick={() => setShow(s => !s)} tabIndex={-1}
            style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: C.text3, padding: 2, display: 'flex', alignItems: 'center' }}>
            {show ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        )}
      </div>
    </div>
  );
}

function GoogleButton({ onClick, disabled }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
        padding: '10px 16px', borderRadius: '8px', cursor: disabled ? 'not-allowed' : 'pointer',
        background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(245,240,232,0.15)',
        color: C.text1, ...UI, fontSize: '14px', fontWeight: 500,
        transition: 'background 0.15s, border-color 0.15s, box-shadow 0.15s', opacity: disabled ? 0.5 : 1 }}
      onMouseEnter={e => { if (!disabled) { e.currentTarget.style.background = 'rgba(255,255,255,0.08)'; e.currentTarget.style.borderColor = 'rgba(245,240,232,0.28)'; e.currentTarget.style.boxShadow = '0 0 14px rgba(255,255,255,0.04)'; }}}
      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; e.currentTarget.style.borderColor = 'rgba(245,240,232,0.15)'; e.currentTarget.style.boxShadow = 'none'; }}>
      <svg width="16" height="16" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
      </svg>
      Continue with Google
    </button>
  );
}

function Divider() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ flex: 1, height: 1, background: 'rgba(245,240,232,0.07)' }} />
      <span style={{ ...MONO, fontSize: 9, letterSpacing: '0.1em', color: C.text4 }}>OR</span>
      <div style={{ flex: 1, height: 1, background: 'rgba(245,240,232,0.07)' }} />
    </div>
  );
}

function PrimaryButton({ children, busy, label }) {
  return (
    <button type="submit" disabled={busy}
      style={{ width: '100%', borderRadius: '8px', padding: '12px 16px',
        ...MONO, fontSize: '12px', letterSpacing: '0.14em', fontWeight: 500,
        color: busy ? 'rgba(12,11,9,0.5)' : '#0C0B09',
        background: busy ? 'rgba(245,158,11,0.3)' : `linear-gradient(135deg, ${C.amber} 0%, ${C.amberDim} 100%)`,
        border: 'none', cursor: busy ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
        boxShadow: busy ? 'none' : '0 4px 20px rgba(245,158,11,0.3)' }}
      onMouseEnter={e => { if (!busy) { e.currentTarget.style.boxShadow = '0 6px 28px rgba(245,158,11,0.45)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = busy ? 'none' : '0 4px 20px rgba(245,158,11,0.3)'; e.currentTarget.style.transform = 'translateY(0)'; }}>
      {busy
        ? <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <Loader size={13} className="animate-spin" />{label}
          </span>
        : children}
    </button>
  );
}

export default function Login() {
  const { login, loading, authError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || '/dashboard';

  const [mode, setMode]           = useState('signin');
  const [error, setError]         = useState(null);
  const [success, setSuccess]     = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const emailRef = useRef(null);

  const [si, setSi]     = useState({ email: '', password: '' });
  const [su, setSu]     = useState({ name: '', email: '', password: '' });
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const qErr   = params.get('error');
    if (qErr === 'oauth_failed')
      setError('Google sign-in failed. Please try again or use email/password.');
    if (qErr === 'oauth_not_configured')
      setError('Google login is not configured. Contact your administrator.');
  }, [location.search]);

  useEffect(() => { emailRef.current?.focus(); }, [mode]);

  const busy = loading || submitting;
  const displayError = _parseError(authError) || error;

  const switchMode = (m) => {
    if (m === mode) return;
    setVisible(false);
    setTimeout(() => { setMode(m); setError(null); setSuccess(null); setVisible(true); }, 140);
  };

  const handleSignIn = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(si.email, si.password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(_parseError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSignUp = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const username = su.email.split('@')[0].replace(/[^a-z0-9_]/gi, '_').toLowerCase();
      await authApi.registerOrg({
        full_name: su.name,
        email: su.email,
        username,
        password: su.password,
      });
      setSuccess('Account created. Signing you in…');
      const created = su.email;
      setSu({ name: '', email: '', password: '' });
      setTimeout(() => {
        switchMode('signin');
        setSi(p => ({ ...p, email: created }));
      }, 1000);
    } catch (err) {
      setError(_parseError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogle = () => { window.location.href = '/auth/google'; };

  return (
    <div className="login-bg grid-bg min-h-screen flex items-center justify-center px-4"
      style={{ position: 'relative' }}>

      {/* Top accent bar */}
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #F59E0B 40%, #FCD34D 50%, #F59E0B 60%, transparent 100%)' }} />

      <div className="w-full max-w-sm" style={{ position: 'relative', zIndex: 1 }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: '52px', height: '52px', borderRadius: '13px', marginBottom: '16px',
            background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
            boxShadow: '0 0 36px rgba(245,158,11,0.35), 0 8px 24px rgba(0,0,0,0.4)' }}>
            <Activity size={22} color="#0C0B09" strokeWidth={2.5} />
          </div>
          <h1 style={{ ...DISPLAY, fontSize: '2.8rem', letterSpacing: '0.1em', color: C.text1, lineHeight: 1, margin: 0 }}>
            Resilo
          </h1>
          <p style={{ ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: C.text4, marginTop: '6px' }}>
            INTELLIGENT OPERATIONS PLATFORM
          </p>
        </div>

        {/* Card */}
        <div style={{ position: 'relative', background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: '16px', boxShadow: '0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(245,158,11,0.04) inset',
          overflow: 'hidden' }}>

          {/* Amber inner top rule */}
          <div style={{ position: 'absolute', top: 0, left: '40px', right: '40px', height: '1px',
            background: 'linear-gradient(90deg, transparent, rgba(245,158,11,0.5), transparent)' }} />

          {/* Tab toggle */}
          <div style={{ display: 'flex', borderBottom: '1px solid rgba(245,240,232,0.07)', padding: '20px 28px 0', background: 'rgba(0,0,0,0.15)' }}>
            {[['signin', 'Sign In'], ['signup', 'Sign Up']].map(([key, label]) => (
              <button key={key} type="button" onClick={() => switchMode(key)}
                style={{ flex: 1, paddingBottom: '12px', background: 'none', border: 'none',
                  cursor: 'pointer', ...MONO, fontSize: '11px', letterSpacing: '0.1em',
                  color: mode === key ? C.amber : C.text3,
                  borderBottom: mode === key ? `2px solid ${C.amber}` : '2px solid transparent',
                  transition: 'color 0.15s, border-color 0.15s',
                  marginBottom: '-1px' }}>
                {label.toUpperCase()}
              </button>
            ))}
          </div>

          <div style={{ padding: '28px', transition: 'opacity 0.14s ease', opacity: visible ? 1 : 0 }}>

            {/* Success banner */}
            {success && (
              <div style={{ marginBottom: '20px', borderRadius: '8px', padding: '10px 14px',
                border: '1px solid rgba(74,222,128,0.25)', background: 'rgba(74,222,128,0.07)',
                color: C.green, fontSize: '13px', ...UI }}>
                {success}
              </div>
            )}

            {/* Error banner */}
            {displayError && !success && (
              <div style={{ marginBottom: '20px', borderRadius: '8px', padding: '10px 14px',
                border: '1px solid rgba(248,113,113,0.25)', background: 'rgba(248,113,113,0.07)',
                color: C.red, fontSize: '13px', ...UI }}>
                {displayError}
              </div>
            )}

            {/* ── SIGN IN ── */}
            {mode === 'signin' && (
              <form onSubmit={handleSignIn} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <Input label="EMAIL" type="email" value={si.email} onChange={v => setSi(p => ({...p, email: v}))}
                  placeholder="you@company.com" autoComplete="email" disabled={busy} inputRef={emailRef} />
                <Input label="PASSWORD" type="password" value={si.password} onChange={v => setSi(p => ({...p, password: v}))}
                  placeholder="••••••••" autoComplete="current-password" disabled={busy} />
                <PrimaryButton busy={busy} label="AUTHENTICATING…">SIGN IN</PrimaryButton>
                <Divider />
                <GoogleButton onClick={handleGoogle} disabled={busy} />
              </form>
            )}

            {/* ── SIGN UP ── */}
            {mode === 'signup' && (
              <form onSubmit={handleSignUp} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <Input label="FULL NAME" value={su.name} onChange={v => setSu(p => ({...p, name: v}))}
                  placeholder="Jane Smith" autoComplete="name" disabled={busy} inputRef={emailRef} />
                <Input label="EMAIL" type="email" value={su.email} onChange={v => setSu(p => ({...p, email: v}))}
                  placeholder="you@company.com" autoComplete="email" disabled={busy} />
                <Input label="PASSWORD" type="password" value={su.password} onChange={v => setSu(p => ({...p, password: v}))}
                  placeholder="Min. 8 characters" autoComplete="new-password" disabled={busy} />
                <div style={{ marginTop: '2px' }}>
                  <PrimaryButton busy={busy} label="CREATING ACCOUNT…">CREATE ACCOUNT</PrimaryButton>
                </div>
                <Divider />
                <GoogleButton onClick={handleGoogle} disabled={busy} />
              </form>
            )}

            <p style={{ marginTop: '20px', fontSize: '11px', color: C.text4, textAlign: 'center', ...UI }}>
              {mode === 'signin'
                ? <>No account?{' '}<button type="button" onClick={() => switchMode('signup')}
                    style={{ background: 'none', border: 'none', color: C.amber, cursor: 'pointer', fontSize: '11px', ...UI, padding: 0 }}>
                    Create one free →
                  </button></>
                : <>Already have an account?{' '}<button type="button" onClick={() => switchMode('signin')}
                    style={{ background: 'none', border: 'none', color: C.amber, cursor: 'pointer', fontSize: '11px', ...UI, padding: 0 }}>
                    Sign in →
                  </button></>
              }
            </p>

            <p style={{ marginTop: '16px', ...MONO, fontSize: '9px', letterSpacing: '0.08em',
              color: '#2E2A24', textAlign: 'center' }}>
              🔒 Secure login · Powered by Resilo Auth
            </p>
          </div>
        </div>

        <p style={{ marginTop: '18px', ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: '#3A342D', textAlign: 'center' }}>
          RESILO · INTELLIGENT OPERATIONS · v2
        </p>
      </div>
    </div>
  );
}
