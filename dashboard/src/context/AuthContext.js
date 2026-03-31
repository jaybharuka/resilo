import React, { createContext, useContext, useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { setTokenGetter, authApi, AUTH_BASE_URL } from '../services/api';
import { startMetricsPush, stopMetricsPush } from '../services/browserMetrics';
import { resiloApi, orgsApi } from '../services/resiloApi';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading
  const [role, setRole] = useState('employee');
  const [authError, setAuthError] = useState(null);
  const metricsPushing = useRef(false);

  function _startMetrics(u) {
    if (!u?.org_id || metricsPushing.current) return;
    metricsPushing.current = true;
    startMetricsPush(async (metrics) => {
      try { await resiloApi.pushBrowserMetrics(u.org_id, metrics); } catch {}
    }, 5_000);
  }

  function _stopMetrics() {
    stopMetricsPush();
    metricsPushing.current = false;
  }

  useEffect(() => {
    async function initAuth() {
      const storedToken = localStorage.getItem('aiops:token');
      if (storedToken) {
        setTokenGetter(() => storedToken); // Synchronous token getter for custom JWT
        try {
          const meData = await authApi.me();
          // FastAPI returns user directly; legacy Flask wraps in {user: ...}
          const u = meData?.id ? meData : meData?.user;
          if (u) {
            setUser(u);
            setRole(u.role || 'employee');
            try { localStorage.setItem('aiops:user', JSON.stringify(u)); } catch {}
            _startMetrics(u);
            orgsApi.resolveAndCache().catch(() => {});
          } else {
            setUser(null);
            try { localStorage.removeItem('aiops:user'); } catch {}
          }
        } catch (err) {
          console.error("Token validation failed", err);
          setTokenGetter(null);
          localStorage.removeItem('aiops:token');
          setUser(null);
        }
      } else {
        setUser(null);
      }
    }
    initAuth();
  }, []);

  const isLoading = user === undefined;
  const isAuthenticated = !!user;

  const login = useCallback(async (email, password) => {
    setAuthError(null);
    try {
      const res = await authApi.login({ email, password });
      // 2FA required — surface to the login page
      if (res?.requires_2fa) {
        return { ok: false, requires_2fa: true, temp_token: res.temp_token };
      }
      if (res?.token && res?.user) {
        localStorage.setItem('aiops:token', res.token);
        try { localStorage.setItem('aiops:user', JSON.stringify(res.user)); } catch {}
        setTokenGetter(() => res.token);
        setUser(res.user);
        setRole(res.user.role || 'employee');
        _startMetrics(res.user);
        orgsApi.resolveAndCache().catch(() => {});
        return { ok: true };
      } else {
        throw new Error('Invalid response from server.');
      }
    } catch (err) {
      // FastAPI uses {detail: "..."}, legacy Flask uses {error: "..."}
      const serverError = err?.response?.data?.detail || err?.response?.data?.error;
      const status = err?.response?.status;
      let msg;
      if (!err?.response) {
        msg = `Cannot reach server at ${AUTH_BASE_URL} — is the backend running?`;
      } else if (status === 429) {
        msg = err?.response?.data?.error || 'Too many attempts. Please wait and try again.';
      } else {
        msg = serverError || `Sign-in failed (HTTP ${status || 'unknown'}).`;
      }
      setAuthError(msg);
      throw new Error(msg);
    }
  }, []);

  const loginWithGoogle = useCallback(async () => {
    setAuthError('Google Login is not available in local mode.');
    throw new Error('Google Login unavailable');
  }, []);

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch {}
    _stopMetrics();
    setTokenGetter(null);
    localStorage.removeItem('aiops:token');
    localStorage.removeItem('aiops:refresh');
    localStorage.removeItem('aiops:user');
    localStorage.removeItem('aiops:pgOrgId');
    setUser(null);
    setRole('employee');
  }, []);

  const value = useMemo(() => ({
    user,
    role: user?.role || role,
    loading: isLoading,
    login,
    loginWithGoogle,
    logout,
    isAuthenticated,
    authError,
  }), [user, role, isLoading, login, loginWithGoogle, logout, isAuthenticated, authError]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
