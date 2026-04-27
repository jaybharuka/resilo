import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Activity, Eye, EyeOff } from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const INPUT = {
  width: '100%', padding: '10px 14px', borderRadius: '8px',
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(245,240,232,0.1)',
  color: '#F5F0E8', outline: 'none', fontSize: '14px', boxSizing: 'border-box',
};

export default function Login() {
  const { login, authError } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]     = useState(false);
  const [busy, setBusy]         = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await login({ email, password });
      navigate('/remote-agents', { replace: true });
    } catch {}
    finally { setBusy(false); }
  }

  return (
    <div className="login-bg grid-bg min-h-screen flex items-center justify-center px-4"
      style={{ position: 'relative' }}>

      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #F59E0B 40%, #FCD34D 50%, #F59E0B 60%, transparent 100%)' }} />

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', maxWidth: '380px' }}>

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

          <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#6B6357', marginBottom: '20px', textAlign: 'center' }}>SIGN IN TO YOUR ACCOUNT</p>

          {authError && (
            <div style={{ ...MONO, fontSize: '12px', color: '#F87171', background: 'rgba(248,113,113,0.08)',
              border: '1px solid rgba(248,113,113,0.2)', borderRadius: '6px', padding: '10px 12px', marginBottom: '16px' }}>
              {authError}
            </div>
          )}

          <div style={{ marginBottom: '14px' }}>
            <label style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#6B6357', display: 'block', marginBottom: '6px' }}>EMAIL</label>
            <input type="email" required autoComplete="email" value={email}
              onChange={e => setEmail(e.target.value)} style={INPUT} placeholder="you@example.com" />
          </div>

          <div style={{ marginBottom: '20px', position: 'relative' }}>
            <label style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#6B6357', display: 'block', marginBottom: '6px' }}>PASSWORD</label>
            <input type={showPw ? 'text' : 'password'} required autoComplete="current-password" value={password}
              onChange={e => setPassword(e.target.value)} style={{ ...INPUT, paddingRight: '42px' }} placeholder="••••••••" />
            <button type="button" onClick={() => setShowPw(p => !p)}
              style={{ position: 'absolute', right: '12px', top: '34px', background: 'none', border: 'none', color: '#6B6357', cursor: 'pointer', padding: 0 }}>
              {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          <button type="submit" disabled={busy} style={{ width: '100%', padding: '11px',
            background: busy ? 'rgba(245,158,11,0.4)' : 'linear-gradient(135deg,#F59E0B,#D97706)',
            border: 'none', borderRadius: '8px', color: '#0C0B09', cursor: busy ? 'not-allowed' : 'pointer',
            ...MONO, fontSize: '12px', letterSpacing: '0.12em', fontWeight: 700,
            boxShadow: busy ? 'none' : '0 4px 20px rgba(245,158,11,0.3)', transition: 'all 0.15s' }}>
            {busy ? 'SIGNING IN…' : 'SIGN IN →'}
          </button>

          <p style={{ ...MONO, fontSize: '11px', color: '#4A443D', textAlign: 'center', marginTop: '18px', marginBottom: 0 }}>
            No account?{' '}
            <Link to="/register" style={{ color: '#F59E0B', textDecoration: 'none' }}>Create one</Link>
          </p>
        </form>

        <p style={{ marginTop: '18px', ...MONO, fontSize: '9px', letterSpacing: '0.08em', color: '#3A342D', textAlign: 'center' }}>
          RESILO · INTELLIGENT OPERATIONS · v2
        </p>
      </div>
    </div>
  );
}
