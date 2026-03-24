import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { authApi } from '../services/api';
import { Eye, EyeOff, CheckCircle } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: '#6B6357', display: 'block', marginBottom: 6 }}>
        {label.toUpperCase()}
      </label>
      {children}
    </div>
  );
}

const inputStyle = {
  width: '100%', background: '#0D0C0A', border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: 7, padding: '10px 14px', color: '#F5F0E8',
  ...UI, fontSize: 14, outline: 'none', boxSizing: 'border-box',
};

export default function AcceptInvite() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') || '';

  const [form, setForm] = useState({ email: '', username: '', password: '', confirm: '', full_name: '' });
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!token) setError('No invite token found in the URL. Please use the link from your invitation email.');
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.email || !form.username || !form.password) { setError('All fields are required'); return; }
    if (form.password.length < 8) { setError('Password must be at least 8 characters'); return; }
    if (form.password !== form.confirm) { setError('Passwords do not match'); return; }

    setLoading(true);
    try {
      await authApi.acceptInvite({ token, email: form.email, username: form.username, password: form.password, full_name: form.full_name });
      setDone(true);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to create account. The invite may have expired.');
    } finally { setLoading(false); }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0C0B09', padding: 20 }}>
      <div style={{ width: '100%', maxWidth: 420 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: 12, boxShadow: '0 0 24px rgba(245,158,11,0.3)' }}>
            <span style={{ fontSize: 22 }}>⚡</span>
          </div>
          <h1 style={{ ...UI, fontSize: 20, fontWeight: 700, color: '#F5F0E8', margin: 0 }}>Resilo</h1>
          <p style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: '#4A443D', marginTop: 4 }}>SET UP YOUR ACCOUNT</p>
        </div>

        <div style={{ background: '#111009', border: '1px solid rgba(42,40,32,0.9)', borderRadius: 12, padding: 28 }}>
          {done ? (
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <CheckCircle size={40} color="#34D399" style={{ marginBottom: 16 }} />
              <h2 style={{ ...UI, fontSize: 18, fontWeight: 600, color: '#F5F0E8', marginBottom: 8 }}>Account Created!</h2>
              <p style={{ ...UI, fontSize: 14, color: '#9CA3AF', marginBottom: 24 }}>Your account is ready. You can now sign in.</p>
              <button
                onClick={() => navigate('/login')}
                style={{ ...UI, background: '#F59E0B', color: '#0C0B09', border: 'none', borderRadius: 8, padding: '10px 24px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
              >
                Go to Login
              </button>
            </div>
          ) : (
            <form onSubmit={submit}>
              <h2 style={{ ...UI, fontSize: 16, fontWeight: 600, color: '#F5F0E8', marginTop: 0, marginBottom: 20 }}>
                You've been invited to join
              </h2>

              <Field label="Full Name (optional)">
                <input style={inputStyle} value={form.full_name} onChange={e => set('full_name', e.target.value)} placeholder="Jane Smith" />
              </Field>
              <Field label="Email">
                <input style={inputStyle} type="email" value={form.email} onChange={e => set('email', e.target.value)} placeholder="you@company.com" />
              </Field>
              <Field label="Username">
                <input style={inputStyle} value={form.username} onChange={e => set('username', e.target.value)} placeholder="jsmith" />
              </Field>
              <Field label="Password">
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPw ? 'text' : 'password'}
                    style={{ ...inputStyle, paddingRight: 42 }}
                    value={form.password}
                    onChange={e => set('password', e.target.value)}
                    placeholder="Min 8 characters"
                  />
                  <button type="button" onClick={() => setShowPw(s => !s)}
                    style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6B6357' }}>
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </Field>
              <Field label="Confirm Password">
                <input
                  type="password"
                  style={inputStyle}
                  value={form.confirm}
                  onChange={e => set('confirm', e.target.value)}
                  placeholder="Repeat password"
                />
              </Field>

              {error && (
                <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 7, padding: '10px 14px', marginBottom: 16 }}>
                  <p style={{ ...UI, fontSize: 13, color: '#EF4444', margin: 0 }}>{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !token}
                style={{ width: '100%', background: '#F59E0B', color: '#0C0B09', border: 'none', borderRadius: 8, padding: '11px', fontSize: 14, fontWeight: 600, cursor: 'pointer', ...UI, opacity: loading ? 0.7 : 1 }}
              >
                {loading ? 'Creating account…' : 'Create Account'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
