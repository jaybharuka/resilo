import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { authApi } from '../services/api';
import { Activity, Eye, EyeOff } from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const INPUT = {
  width: '100%', padding: '10px 14px', borderRadius: '8px',
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(245,240,232,0.1)',
  color: '#F5F0E8', outline: 'none', fontSize: '14px', boxSizing: 'border-box',
};

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm]   = useState({ email: '', username: '', full_name: '', password: '', confirm: '' });
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState('');

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    if (form.password !== form.confirm) { setError('Passwords do not match.'); return; }
    setBusy(true); setError('');
    try {
      await authApi.registerOrg({ email: form.email, username: form.username, password: form.password, full_name: form.full_name });
      navigate('/login', { replace: true, state: { registered: true } });
    } catch (err) {
      setError(err?.response?.data?.detail || 'Registration failed.');
    } finally { setBusy(false); }
  }

  return (
    <div className="login-bg grid-bg min-h-screen flex items-center justify-center px-4"
      style={{ position: 'relative' }}>

      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #F59E0B 40%, #FCD34D 50%, #F59E0B 60%, transparent 100%)' }} />

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', maxWidth: '400px' }}>

        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: '52px', height: '52px', borderRadius: '13px', marginBottom: '16px',
            background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
            boxShadow: '0 0 36px rgba(245,158,11,0.35), 0 8px 24px rgba(0,0,0,0.4)' }}>
            <Activity size={22} color="#0C0B09" strokeWidth={2.5} />
          </div>
          <h1 style={{ ...DISPLAY, fontSize: '2.8rem', letterSpacing: '0.1em', color: '#F5F0E8', lineHeight: 1, margin: 0 }}>Resilo</h1>
          <p style={{ ...MONO, fontSize: '10px', letterSpacing: '0.14em', color: '#4A443D', marginTop: '6px' }}>INTELLIGENT OPERATIONS PLATFORM</p>
        </div>

        <form onSubmit={handleSubmit} style={{ width: '100%', background: 'rgb(22,20,16)',
          border: '1px solid rgba(245,158,11,0.14)', borderRadius: '14px',
          padding: '28px 28px 24px', boxShadow: '0 32px 80px rgba(0,0,0,0.6)' }}>

          <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#6B6357', marginBottom: '20px', textAlign: 'center' }}>CREATE YOUR ACCOUNT</p>

          {error && (
            <div style={{ ...MONO, fontSize: '12px', color: '#F87171', background: 'rgba(248,113,113,0.08)',
              border: '1px solid rgba(248,113,113,0.2)', borderRadius: '6px', padding: '10px 12px', marginBottom: '16px' }}>
              {error}
            </div>
          )}

          {[['full_name','FULL NAME','text','Your name'],['email','EMAIL','email','you@example.com'],['username','USERNAME','text','yourhandle']].map(([k,label,type,ph]) => (
            <div key={k} style={{ marginBottom: '14px' }}>
              <label style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#6B6357', display: 'block', marginBottom: '6px' }}>{label}</label>
              <input type={type} required value={form[k]} onChange={set(k)} style={INPUT} placeholder={ph} />
            </div>
          ))}

          <div style={{ marginBottom: '14px', position: 'relative' }}>
            <label style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#6B6357', display: 'block', marginBottom: '6px' }}>PASSWORD</label>
            <input type={showPw ? 'text' : 'password'} required value={form.password} onChange={set('password')}
              style={{ ...INPUT, paddingRight: '42px' }} placeholder="min 8 characters" minLength={8} />
            <button type="button" onClick={() => setShowPw(p => !p)}
              style={{ position: 'absolute', right: '12px', top: '34px', background: 'none', border: 'none', color: '#6B6357', cursor: 'pointer', padding: 0 }}>
              {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#6B6357', display: 'block', marginBottom: '6px' }}>CONFIRM PASSWORD</label>
            <input type="password" required value={form.confirm} onChange={set('confirm')} style={INPUT} placeholder="••••••••" />
          </div>

          <button type="submit" disabled={busy} style={{ width: '100%', padding: '11px',
            background: busy ? 'rgba(245,158,11,0.4)' : 'linear-gradient(135deg,#F59E0B,#D97706)',
            border: 'none', borderRadius: '8px', color: '#0C0B09', cursor: busy ? 'not-allowed' : 'pointer',
            ...MONO, fontSize: '12px', letterSpacing: '0.12em', fontWeight: 700,
            boxShadow: busy ? 'none' : '0 4px 20px rgba(245,158,11,0.3)', transition: 'all 0.15s' }}>
            {busy ? 'CREATING…' : 'CREATE ACCOUNT →'}
          </button>

          <p style={{ ...MONO, fontSize: '11px', color: '#4A443D', textAlign: 'center', marginTop: '18px', marginBottom: 0 }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: '#F59E0B', textDecoration: 'none' }}>Sign in</Link>
          </p>
        </form>

        <p style={{ marginTop: '18px', ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: '#3A342D', textAlign: 'center' }}>
          RESILO · INTELLIGENT OPERATIONS · v2
        </p>
      </div>
    </div>
  );
}
