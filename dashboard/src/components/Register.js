import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../services/api';
import { Activity, Building2, UserPlus, Eye, EyeOff, ArrowLeft } from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const UI      = { fontFamily: "'Outfit', sans-serif" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const inputBase = {
  width: '100%',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(245,240,232,0.08)',
  borderRadius: '8px',
  padding: '10px 12px',
  fontSize: '14px',
  color: '#F5F0E8',
  ...UI,
  outline: 'none',
  boxSizing: 'border-box',
  transition: 'border-color 0.15s, box-shadow 0.15s',
};

function Field({ label, type = 'text', value, onChange, placeholder, autoComplete }) {
  const [show, setShow] = useState(false);
  const isPw = type === 'password';
  return (
    <div>
      <label style={{ display: 'block', ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: '#6B6357', marginBottom: '7px' }}>
        {label}
      </label>
      <div style={{ position: 'relative' }}>
        <input
          type={isPw && show ? 'text' : type}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          style={{ ...inputBase, paddingRight: isPw ? 40 : 12 }}
          onFocus={e => { e.target.style.borderColor = 'rgba(245,158,11,0.45)'; e.target.style.boxShadow = '0 0 0 3px rgba(245,158,11,0.08)'; }}
          onBlur={e => { e.target.style.borderColor = 'rgba(245,240,232,0.08)'; e.target.style.boxShadow = 'none'; }}
        />
        {isPw && (
          <button type="button" onClick={() => setShow(s => !s)}
            style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6B6357', padding: 4 }}>
            {show ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Create Organization (Admin) ───────────────────────────────────────────────
function CreateOrgForm({ onBack }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: '', email: '', username: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    setBusy(true);
    try {
      await authApi.registerOrg(form);
      setDone(true);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Registration failed.');
    } finally { setBusy(false); }
  };

  if (done) return (
    <div style={{ textAlign: 'center', padding: '12px 0' }}>
      <div style={{ fontSize: 40, marginBottom: 16, color: '#34D399' }}>✓</div>
      <h2 style={{ ...UI, fontSize: 20, fontWeight: 700, color: '#34D399', margin: '0 0 10px' }}>Account created!</h2>
      <p style={{ ...UI, fontSize: 14, color: '#9CA3AF', marginBottom: 24, lineHeight: 1.6 }}>
        Your account is ready. Sign in with your credentials.
      </p>
      <button onClick={() => navigate('/login')}
        style={{ padding: '11px 28px', borderRadius: 8, background: 'linear-gradient(135deg, #F59E0B, #D97706)', color: '#0C0B09', border: 'none', cursor: 'pointer', ...MONO, fontSize: 12, letterSpacing: '0.1em', boxShadow: '0 4px 20px rgba(245,158,11,0.3)' }}>
        GO TO SIGN IN
      </button>
    </div>
  );

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <button type="button" onClick={onBack}
        style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#6B6357', cursor: 'pointer', ...MONO, fontSize: 10, letterSpacing: '0.1em', padding: 0, marginBottom: 2 }}>
        <ArrowLeft size={12} /> BACK
      </button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <div style={{ width: 34, height: 34, borderRadius: 9, background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Building2 size={17} color="#F59E0B" />
        </div>
        <div>
          <p style={{ ...UI, fontSize: 15, fontWeight: 700, color: '#F5F0E8', margin: 0 }}>Create Account</p>
          <p style={{ ...MONO, fontSize: 9, color: '#6B6357', margin: 0, letterSpacing: '0.1em' }}>FREE ACCOUNT</p>
        </div>
      </div>

      {error && (
        <div style={{ borderRadius: 8, border: '1px solid rgba(248,113,113,0.25)', background: 'rgba(248,113,113,0.07)', color: '#F87171', padding: '10px 14px', fontSize: 13, ...UI }}>
          {error}
        </div>
      )}

      <Field label="YOUR FULL NAME" value={form.full_name} onChange={v => set('full_name', v)} placeholder="Jane Smith" />
      <Field label="EMAIL" type="email" value={form.email} onChange={v => set('email', v)} placeholder="jane@acme.com" autoComplete="email" />
      <Field label="USERNAME" value={form.username} onChange={v => set('username', v)} placeholder="janesmith" autoComplete="username" />
      <Field label="PASSWORD" type="password" value={form.password} onChange={v => set('password', v)} placeholder="Min 8 characters" autoComplete="new-password" />

      <button type="submit" disabled={busy}
        style={{ width: '100%', borderRadius: 8, padding: '12px 16px', marginTop: 4, ...MONO, fontSize: 12, letterSpacing: '0.14em', color: busy ? 'rgba(12,11,9,0.5)' : '#0C0B09', background: busy ? 'rgba(245,158,11,0.3)' : 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)', border: 'none', cursor: busy ? 'not-allowed' : 'pointer', boxShadow: busy ? 'none' : '0 4px 20px rgba(245,158,11,0.3)', transition: 'all 0.15s' }}>
        {busy ? 'CREATING…' : 'CREATE ACCOUNT'}
      </button>
    </form>
  );
}

// ── Join with Invite (Employee) ───────────────────────────────────────────────
function JoinForm({ onBack }) {
  const navigate = useNavigate();
  const [token, setToken] = useState('');

  const submit = (e) => {
    e.preventDefault();
    const t = token.trim();
    if (!t) return;
    navigate(`/accept-invite?token=${encodeURIComponent(t)}`);
  };

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <button type="button" onClick={onBack}
        style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#6B6357', cursor: 'pointer', ...MONO, fontSize: 10, letterSpacing: '0.1em', padding: 0, marginBottom: 2 }}>
        <ArrowLeft size={12} /> BACK
      </button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <div style={{ width: 34, height: 34, borderRadius: 9, background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <UserPlus size={17} color="#60A5FA" />
        </div>
        <div>
          <p style={{ ...UI, fontSize: 15, fontWeight: 700, color: '#F5F0E8', margin: 0 }}>Join an Organization</p>
          <p style={{ ...MONO, fontSize: 9, color: '#6B6357', margin: 0, letterSpacing: '0.1em' }}>USE YOUR INVITE LINK OR TOKEN</p>
        </div>
      </div>

      <p style={{ ...UI, fontSize: 13, color: '#9CA3AF', margin: 0, lineHeight: 1.6 }}>
        Your admin should have sent you an invite link. Paste the full URL or just the token.
      </p>

      <div>
        <label style={{ display: 'block', ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: '#6B6357', marginBottom: '7px' }}>
          INVITE LINK OR TOKEN
        </label>
        <input
          value={token}
          onChange={e => {
            let val = e.target.value.trim();
            try { const u = new URL(val); const t = u.searchParams.get('token'); if (t) val = t; } catch {}
            setToken(val);
          }}
          placeholder="Paste invite link or token here…"
          style={{ ...inputBase }}
          onFocus={e => { e.target.style.borderColor = 'rgba(96,165,250,0.45)'; e.target.style.boxShadow = '0 0 0 3px rgba(96,165,250,0.08)'; }}
          onBlur={e => { e.target.style.borderColor = 'rgba(245,240,232,0.08)'; e.target.style.boxShadow = 'none'; }}
        />
      </div>

      <button type="submit" disabled={!token.trim()}
        style={{ width: '100%', borderRadius: 8, padding: '12px 16px', marginTop: 4, ...MONO, fontSize: 12, letterSpacing: '0.14em', color: '#F5F0E8', background: token.trim() ? 'rgba(96,165,250,0.15)' : 'rgba(96,165,250,0.05)', border: `1px solid ${token.trim() ? 'rgba(96,165,250,0.4)' : 'rgba(96,165,250,0.15)'}`, cursor: token.trim() ? 'pointer' : 'not-allowed', transition: 'all 0.15s' }}>
        CONTINUE WITH INVITE
      </button>
    </form>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Register() {
  const navigate = useNavigate();
  const [mode, setMode] = useState(null); // null | 'admin' | 'employee'

  return (
    <div className="login-bg grid-bg min-h-screen flex items-center justify-center px-4" style={{ position: 'relative' }}>
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: 2, background: 'linear-gradient(90deg, transparent 0%, #F59E0B 40%, #FCD34D 50%, #F59E0B 60%, transparent 100%)' }} />

      <div style={{ width: '100%', maxWidth: 420, position: 'relative', zIndex: 1 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 56, height: 56, borderRadius: 14, background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)', boxShadow: '0 0 40px rgba(245,158,11,0.35), 0 8px 24px rgba(0,0,0,0.4)', marginBottom: 20 }}>
            <Activity size={24} color="#0C0B09" strokeWidth={2.5} />
          </div>
          <h1 style={{ ...DISPLAY, fontSize: '3rem', letterSpacing: '0.1em', color: '#F5F0E8', lineHeight: 1, margin: 0 }}>Resilo</h1>
          <p style={{ ...MONO, fontSize: 11, letterSpacing: '0.14em', color: '#4A443D', marginTop: 8 }}>CREATE YOUR ACCOUNT</p>
        </div>

        {/* Card */}
        <div style={{ position: 'relative', background: 'rgb(22,20,16)', border: '1px solid rgba(245,158,11,0.14)', borderRadius: 16, padding: 32, boxShadow: '0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(245,158,11,0.04) inset' }}>
          <div style={{ position: 'absolute', top: 0, left: 40, right: 40, height: 1, background: 'linear-gradient(90deg, transparent, rgba(245,158,11,0.5), transparent)' }} />

          {mode === null && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <p style={{ ...UI, fontSize: 14, color: '#9CA3AF', textAlign: 'center', marginBottom: 6 }}>
                How would you like to get started?
              </p>

              {/* Admin path */}
              <button onClick={() => setMode('admin')}
                style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 18px', background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 10, cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s', width: '100%' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.1)'; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.35)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.06)'; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.2)'; }}
              >
                <div style={{ width: 42, height: 42, borderRadius: 10, background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Building2 size={19} color="#F59E0B" />
                </div>
                <div style={{ minWidth: 0 }}>
                  <p style={{ ...UI, fontSize: 14, fontWeight: 600, color: '#F5F0E8', margin: 0 }}>Create an Organization</p>
                  <p style={{ ...UI, fontSize: 12, color: '#6B6357', margin: '3px 0 0' }}>Start fresh — you'll be the admin, invite your team</p>
                </div>
              </button>

              {/* Employee path */}
              <button onClick={() => setMode('employee')}
                style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 18px', background: 'rgba(96,165,250,0.05)', border: '1px solid rgba(96,165,250,0.15)', borderRadius: 10, cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s', width: '100%' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(96,165,250,0.1)'; e.currentTarget.style.borderColor = 'rgba(96,165,250,0.3)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(96,165,250,0.05)'; e.currentTarget.style.borderColor = 'rgba(96,165,250,0.15)'; }}
              >
                <div style={{ width: 42, height: 42, borderRadius: 10, background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <UserPlus size={19} color="#60A5FA" />
                </div>
                <div style={{ minWidth: 0 }}>
                  <p style={{ ...UI, fontSize: 14, fontWeight: 600, color: '#F5F0E8', margin: 0 }}>Join with an Invite</p>
                  <p style={{ ...UI, fontSize: 12, color: '#6B6357', margin: '3px 0 0' }}>Your admin sent you an invite link — use it here</p>
                </div>
              </button>

              <p style={{ ...UI, fontSize: 12, color: '#4A443D', textAlign: 'center', marginTop: 6 }}>
                Already have an account?{' '}
                <button onClick={() => navigate('/login')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#F59E0B', ...UI, fontSize: 12 }}>
                  Sign in
                </button>
              </p>
            </div>
          )}

          {mode === 'admin'    && <CreateOrgForm onBack={() => setMode(null)} />}
          {mode === 'employee' && <JoinForm      onBack={() => setMode(null)} />}
        </div>
      </div>
    </div>
  );
}
