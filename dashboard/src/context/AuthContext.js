import React, { createContext, useContext, useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { setTokenGetter, authApi, AUTH_BASE_URL } from '../services/api';
import { startMetricsPush, stopMetricsPush } from '../services/browserMetrics';
import { resiloApi } from '../services/resiloApi';

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
    }, 15_000);
  }

  function _stopMetrics() {
    stopMetricsPush();
    metricsPushing.current = false;
  }

  useEffect(() => {
    async function initAuth() {
      // Access token lives in memory only — on any page load, silently refresh via httpOnly cookie.
      try {
        const refreshRes = await authApi.refresh();
        if (refreshRes?.token) {
          setTokenGetter(() => refreshRes.token);
          const meData = await authApi.me();
          const u = meData?.id ? meData : meData?.user;
          if (u) { setUser(u); setRole(u.role || 'employee'); _startMetrics(u); return; }
        }
      } catch {}
      // No valid cookie / session — clear legacy storage and show login
      setTokenGetter(null);
      try { localStorage.removeItem('aiops:token'); localStorage.removeItem('aiops:refresh'); localStorage.removeItem('aiops:user'); } catch {}
      try { sessionStorage.removeItem('aiops:token'); } catch {}
      setUser(null);
    }
    initAuth();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

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
      if (res?.token) {
        setTokenGetter(() => res.token);
        let u = res.user;
        if (!u) {
          try { const meData = await authApi.me(); u = meData?.id ? meData : meData?.user; } catch {}
        }
        if (u) {
          setUser(u);
          setRole(u.role || 'employee');
          _startMetrics(u);
        }
        return { ok: true };
      } else {
        throw new Error('Invalid response from server.');
      }
    } catch (err) {
      // FastAPI uses {detail: "..."}, legacy API uses {error: "..."}
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

  const loginWithGoogle = useCallback(() => {
    window.location.href = '/auth/google';
  }, []);

  const initFromOAuth = useCallback(async (token) => {
    setAuthError(null);
    try {
      setTokenGetter(() => token);
      const meData = await authApi.me();
      const u = meData?.id ? meData : meData?.user;
      if (!u) throw new Error('Could not load user info');
      setUser(u);
      setRole(u.role || 'employee');
      _startMetrics(u);
      return { ok: true };
    } catch (err) {
      setTokenGetter(null);
      setUser(null);
      throw err;
    }
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch {}
    _stopMetrics();
    setTokenGetter(null);
    try { localStorage.removeItem('aiops:token'); localStorage.removeItem('aiops:refresh'); localStorage.removeItem('aiops:user'); } catch {}
    try { sessionStorage.removeItem('aiops:token'); } catch {}
    setUser(null);
    setRole('employee');
  }, []);

  const value = useMemo(() => ({
    user,
    role: user?.role || role,
    loading: isLoading,
    login,
    loginWithGoogle,
    initFromOAuth,
    logout,
    isAuthenticated,
    authError,
  }), [user, role, isLoading, login, loginWithGoogle, initFromOAuth, logout, isAuthenticated, authError]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
