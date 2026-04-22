import React, { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };

export default function AuthCallback() {
  const { initFromOAuth } = useAuth();
  const navigate  = useNavigate();
  const location  = useLocation();
  const ran       = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const params = new URLSearchParams(location.search);
    const token  = params.get('token');
    const err    = params.get('error');

    if (err || !token) {
      navigate('/login?error=oauth_failed', { replace: true });
      return;
    }

    initFromOAuth(token)
      .then(() => navigate('/dashboard', { replace: true }))
      .catch(() => navigate('/login?error=oauth_failed', { replace: true }));
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', background: 'rgb(14,13,11)',
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <Loader size={22} color="#F59E0B"
            style={{ animation: 'spin 1s linear infinite' }} />
        </div>
        <p style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: '#4A443D' }}>
          COMPLETING SIGN IN…
        </p>
      </div>
    </div>
  );
}
