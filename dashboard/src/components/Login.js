import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Activity } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

export default function Login() {
  const { login, loading, authError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || '/dashboard';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const displayError = authError || error;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err?.message || 'Sign-in failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const busy = loading || submitting;

  const inputStyle = {
    width: '100%',
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(245,240,232,0.08)',
    borderRadius: '8px',
    padding: '10px 12px',
    fontSize: '14px',
    color: '#F5F0E8',
    ...UI,
    outline: 'none',
    transition: 'border-color 0.15s, box-shadow 0.15s',
  };

  return (
    <div
      className="login-bg grid-bg min-h-screen flex items-center justify-center px-4"
      style={{ position: 'relative' }}
    >
      {/* Decorative horizontal rule at top */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          height: '2px',
          background: 'linear-gradient(90deg, transparent 0%, #F59E0B 40%, #FCD34D 50%, #F59E0B 60%, transparent 100%)',
        }}
      />

      <div className="w-full max-w-sm" style={{ position: 'relative', zIndex: 1 }}>

        {/* Logo mark */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '56px',
              height: '56px',
              borderRadius: '14px',
              background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              boxShadow: '0 0 40px rgba(245,158,11,0.35), 0 8px 24px rgba(0,0,0,0.4)',
              marginBottom: '20px',
            }}
          >
            <Activity size={24} color="#0C0B09" strokeWidth={2.5} />
          </div>

          <h1
            style={{
              ...DISPLAY,
              fontSize: '3rem',
              letterSpacing: '0.1em',
              color: '#F5F0E8',
              lineHeight: 1,
              margin: 0,
            }}
          >
            Resilo
          </h1>
          <p
            style={{
              ...MONO,
              fontSize: '11px',
              letterSpacing: '0.14em',
              color: '#4A443D',
              marginTop: '8px',
            }}
          >
            INTELLIGENT OPERATIONS PLATFORM
          </p>
        </div>

        {/* Card */}
        <div
          style={{
            position: 'relative',
            background: 'rgb(22, 20, 16)',
            border: '1px solid rgba(245,158,11,0.14)',
            borderRadius: '16px',
            padding: '32px',
            boxShadow: '0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(245,158,11,0.04) inset',
          }}
        >
          {/* Amber top rule inside card */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: '40px',
              right: '40px',
              height: '1px',
              background: 'linear-gradient(90deg, transparent, rgba(245,158,11,0.5), transparent)',
              borderRadius: '1px',
            }}
          />

          {displayError && (
            <div
              style={{
                marginBottom: '20px',
                borderRadius: '8px',
                border: '1px solid rgba(248,113,113,0.25)',
                background: 'rgba(248,113,113,0.07)',
                color: '#F87171',
                padding: '10px 14px',
                fontSize: '13px',
                ...UI,
              }}
            >
              {displayError}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <div>
              <label
                style={{
                  display: 'block',
                  ...MONO,
                  fontSize: '10px',
                  letterSpacing: '0.14em',
                  color: '#6B6357',
                  marginBottom: '7px',
                }}
              >
                EMAIL
              </label>
              <input
                type="text"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={busy}
                style={{ ...inputStyle, opacity: busy ? 0.6 : 1 }}
                placeholder="you@company.com"
                autoComplete="email"
                onFocus={e => {
                  e.target.style.borderColor = 'rgba(245,158,11,0.45)';
                  e.target.style.boxShadow = '0 0 0 3px rgba(245,158,11,0.08)';
                }}
                onBlur={e => {
                  e.target.style.borderColor = 'rgba(245,240,232,0.08)';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>

            <div>
              <label
                style={{
                  display: 'block',
                  ...MONO,
                  fontSize: '10px',
                  letterSpacing: '0.14em',
                  color: '#6B6357',
                  marginBottom: '7px',
                }}
              >
                PASSWORD
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                style={{ ...inputStyle, opacity: busy ? 0.6 : 1 }}
                placeholder="••••••••"
                autoComplete="current-password"
                onFocus={e => {
                  e.target.style.borderColor = 'rgba(245,158,11,0.45)';
                  e.target.style.boxShadow = '0 0 0 3px rgba(245,158,11,0.08)';
                }}
                onBlur={e => {
                  e.target.style.borderColor = 'rgba(245,240,232,0.08)';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>

            <button
              type="submit"
              disabled={busy}
              style={{
                width: '100%',
                borderRadius: '8px',
                padding: '12px 16px',
                ...MONO,
                fontSize: '12px',
                letterSpacing: '0.14em',
                fontWeight: 500,
                color: busy ? 'rgba(12,11,9,0.5)' : '#0C0B09',
                background: busy
                  ? 'rgba(245,158,11,0.3)'
                  : 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                border: 'none',
                cursor: busy ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s',
                boxShadow: busy ? 'none' : '0 4px 20px rgba(245,158,11,0.3)',
                marginTop: '4px',
              }}
              onMouseEnter={e => {
                if (!busy) {
                  e.currentTarget.style.boxShadow = '0 6px 28px rgba(245,158,11,0.45)';
                  e.currentTarget.style.transform = 'translateY(-1px)';
                }
              }}
              onMouseLeave={e => {
                e.currentTarget.style.boxShadow = '0 4px 20px rgba(245,158,11,0.3)';
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              {submitting ? 'AUTHENTICATING…' : 'SIGN IN'}
            </button>
          </form>

          <p style={{ marginTop: '20px', fontSize: '12px', color: '#4A443D', textAlign: 'center', ...UI }}>
            Forgot your password?{' '}
            <a
              href="/forgot-password"
              style={{ color: '#F59E0B', textDecoration: 'none' }}
              onMouseEnter={e => { e.target.style.textDecoration = 'underline'; }}
              onMouseLeave={e => { e.target.style.textDecoration = 'none'; }}
            >
              Reset it here
            </a>
          </p>

          <p style={{ marginTop: '12px', fontSize: '12px', color: '#4A443D', textAlign: 'center', ...UI }}>
            New here?{' '}
            <a
              href="/register"
              style={{ color: '#F59E0B', textDecoration: 'none' }}
              onMouseEnter={e => { e.target.style.textDecoration = 'underline'; }}
              onMouseLeave={e => { e.target.style.textDecoration = 'none'; }}
            >
              Create an organization
            </a>
          </p>
        </div>

        <p
          style={{
            marginTop: '20px',
            ...MONO,
            fontSize: '10px',
            letterSpacing: '0.08em',
            color: '#3A342D',
            textAlign: 'center',
          }}
        >
          Admin access unlocks system actions and advanced controls.
        </p>
      </div>
    </div>
  );
}
