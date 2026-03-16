import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { authApi, setAuthTokenOnClient, setRefreshTokenOnClient } from '../services/api';
import toast from 'react-hot-toast';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem('aiops:user');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [token, setToken] = useState(() => localStorage.getItem('aiops:token'));
  const [loading, setLoading] = useState(false);

  // Sync axios auth header
  useEffect(() => {
    setAuthTokenOnClient(token || undefined);
  }, [token]);

  // Define logout handler BEFORE any effects that reference it
  const doLogout = useCallback(async (serverLogout = true) => {
    try {
      const tk = localStorage.getItem('aiops:token');
      if (serverLogout && tk) {
        await authApi.logout();
      }
    } catch {
      // ignore
    } finally {
      setUser(null);
      setToken(null);
      localStorage.removeItem('aiops:token');
      localStorage.removeItem('aiops:user');
      localStorage.removeItem('aiops:refresh');
      navigate('/login', { replace: true });
    }
  }, [navigate]);

  // Auto-logout on global unauthorized events
  useEffect(() => {
    const handler = () => doLogout(false);
    window.addEventListener('aiops:unauthorized', handler);
    return () => window.removeEventListener('aiops:unauthorized', handler);
  }, [doLogout]);

  // Restore session
  useEffect(() => {
    let mounted = true;
    (async () => {
      if (!token) return;
      try {
        const me = await authApi.me();
        if (!mounted) return;
        setUser(me.user);
      } catch {
        // invalid token
        doLogout(false);
      }
    })();
    return () => { mounted = false; };
  }, [token]);

  const doLogin = useCallback(async (email, password, rolePreference) => {
    setLoading(true);
    try {
      const res = await authApi.login({ email, password, role: rolePreference });
      const { token: tk, refresh_token: rt, user: u } = res;
      setToken(tk);
      setUser(u);
      localStorage.setItem('aiops:token', tk);
      if (rt) {
        setRefreshTokenOnClient(rt);
        try { localStorage.setItem('aiops:refresh', rt); } catch {}
      }
      localStorage.setItem('aiops:user', JSON.stringify(u));
      try { toast.success('Signed in'); } catch {}
      // Redirect to intended page or dashboard
      const from = (location.state && location.state.from) || { pathname: '/dashboard' };
      navigate(from, { replace: true });
      return { ok: true };
    } catch (e) {
      const msg = e?.response?.data?.error || e.message;
      try { toast.error(msg || 'Login failed'); } catch {}
      return { ok: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, [location.state, navigate]);

  const value = useMemo(() => ({
    user,
    role: user?.role || 'employee',
    token,
    loading,
    login: doLogin,
    logout: doLogout,
    isAuthenticated: !!user && !!token,
  }), [user, token, loading, doLogin, doLogout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
