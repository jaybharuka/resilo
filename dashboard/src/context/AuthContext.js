import React, { createContext, useContext, useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { setTokenGetter, authApi } from '../services/api';
import { startMetricsPush, stopMetricsPush } from '../services/browserMetrics';
import { resiloApi } from '../services/resiloApi';

const AuthContext = createContext(null);
const TOKEN_KEY = 'resilo_token';
const USER_KEY  = 'resilo_user';

export function AuthProvider({ children }) {
  const [user, setUser]           = useState(undefined);
  const [role, setRole]           = useState('employee');
  const [loading, setLoading]     = useState(true);
  const [authError, setAuthError] = useState(null);
  const metricsPushing            = useRef(false);

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
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) { setUser(null); setLoading(false); return; }
    setTokenGetter(() => token);
    authApi.me()
      .then(u => { setUser(u); setRole(u.role || 'employee'); _startMetrics(u); })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        setTokenGetter(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async ({ email, password }) => {
    setAuthError(null);
    try {
      const res = await authApi.login({ email, password });
      if (res?.token) {
        localStorage.setItem(TOKEN_KEY, res.token);
        localStorage.setItem(USER_KEY, JSON.stringify(res.user));
        setTokenGetter(() => res.token);
        setUser(res.user);
        setRole(res.user?.role || 'employee');
        _startMetrics(res.user);
      }
      return res;
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Login failed.';
      setAuthError(msg);
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    _stopMetrics();
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setTokenGetter(null);
    setUser(null);
    setRole('employee');
    try { await authApi.logout(); } catch {}
  }, []);

  const isAuthenticated = !!user;

  const value = useMemo(() => ({
    user,
    role: user?.role || role,
    loading,
    login,
    loginWithGoogle: login,
    initFromOAuth: login,
    logout,
    isAuthenticated,
    authError,
    setAuthError,
  }), [user, role, loading, login, logout, isAuthenticated, authError]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
