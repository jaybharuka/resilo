import React, { createContext, useContext, useEffect, useState, useMemo, useCallback } from 'react';
import { setTokenGetter, authApi } from '../services/api';
import { clearMetricsConsent } from '../components/MetricsConsent';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading
  const [role, setRole] = useState('employee');
  const [authError, setAuthError] = useState(null); 
  
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
        return { ok: true };
      } else {
        throw new Error('Invalid response from server.');
      }
    } catch (err) {
      // FastAPI uses {detail: "..."}, legacy Flask uses {error: "..."}
      const serverError = err?.response?.data?.detail || err?.response?.data?.error;
      setAuthError(serverError || 'Sign-in failed.');
      throw new Error(serverError || 'Sign-in failed.');
    }
  }, []);

  const loginWithGoogle = useCallback(async () => {
    setAuthError('Google Login is not available in local mode.');
    throw new Error('Google Login unavailable');
  }, []);

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch {}
    clearMetricsConsent(user?.id);
    setTokenGetter(null);
    localStorage.removeItem('aiops:token');
    localStorage.removeItem('aiops:refresh');
    localStorage.removeItem('aiops:user');
    setUser(null);
    setRole('employee');
  }, [user?.id]);

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
