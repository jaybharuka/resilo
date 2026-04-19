/* eslint-disable unicode-bom */
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import AIAssistant from './components/AIAssistant';
import Settings from './components/Settings';
import Alerts from './components/Alerts';
import Register from './components/Register';
import Forbidden from './components/Forbidden';
import RemoteAgents from './components/RemoteAgents';
import ErrorBoundary from './components/ErrorBoundary';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './components/Login';
import AuthCallback from './components/AuthCallback';
import ForgotPassword from './components/ForgotPassword';
import ResetPassword from './components/ResetPassword';
import AcceptInvite from './components/AcceptInvite';
import HealthRibbon from './components/HealthRibbon';
import IncidentDeclare from './components/IncidentDeclare';
import ConnectionStatus from './components/ConnectionStatus';
import { RefreshCw } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };

function Topbar() {
  const { user, role, isAuthenticated } = useAuth();
  const [refreshing, setRefreshing] = React.useState(false);

  const triggerRefresh = React.useCallback(() => {
    if (refreshing) return;
    setRefreshing(true);
    try { window.dispatchEvent(new CustomEvent('aiops:refresh')); } catch {}
    setTimeout(() => setRefreshing(false), 800);
  }, [refreshing]);

  if (!isAuthenticated) return null;

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginBottom: '20px', gap: '12px' }}>
      <ConnectionStatus />
      <IncidentDeclare />
      {user?.email && (
        <span style={{ ...MONO, fontSize: '13px', letterSpacing: '0.06em', color: '#4A443D' }}>
          {user.email}
        </span>
      )}
      <span
        style={{
          ...MONO,
          fontSize: '12px',
          letterSpacing: '0.1em',
          padding: '3px 9px',
          borderRadius: '10px',
          ...(role === 'admin'
            ? { background: 'rgba(245,158,11,0.1)', color: '#F59E0B', border: '1px solid rgba(245,158,11,0.2)' }
            : { background: 'rgba(245,240,232,0.05)', color: '#6B6357', border: '1px solid rgba(42,40,32,0.9)' }
          ),
        }}
      >
        {role === 'admin' ? 'ADMIN' : 'EMPLOYEE'}
      </span>
      <button
        onClick={triggerRefresh}
        style={{
          padding: '6px',
          borderRadius: '6px',
          background: 'transparent',
          border: '1px solid rgba(42,40,32,0.9)',
          color: '#4A443D',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          opacity: refreshing ? 0.5 : 1,
          transition: 'color 0.15s, border-color 0.15s',
        }}
        title="Refresh data"
        onMouseEnter={e => { e.currentTarget.style.color = '#F59E0B'; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.3)'; }}
        onMouseLeave={e => { e.currentTarget.style.color = '#4A443D'; e.currentTarget.style.borderColor = 'rgba(42,40,32,0.9)'; }}
      >
        <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
      </button>
    </div>
  );
}

function AppShell() {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();
  const AUTH_ROUTES = ['/login', '/register', '/forgot-password', '/reset-password', '/auth/callback', '/accept-invite', '/redeem'];
  const isAuthPage   = AUTH_ROUTES.some(p => location.pathname.startsWith(p));
  const hideSidebar  = isAuthPage;

  // Redirect already-authenticated users away from the login/register pages
  if (isAuthenticated && isAuthPage) {
    return <Navigate to="/remote-agents" replace />;
  }

  // Force password change before accessing any other page
  if (isAuthenticated && user?.must_change_password && location.pathname !== '/settings' && !isAuthPage) {
    return <Navigate to="/settings" replace />;
  }

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: 'rgb(var(--bg))', color: 'rgb(var(--text))' }}>
      {!hideSidebar && <Sidebar />}
      <main
        className="flex-1 min-w-0 px-6 py-5 overflow-y-auto"
        style={{ background: 'rgb(var(--bg))', marginLeft: hideSidebar ? 0 : undefined }}
      >
        <Toaster position="top-right" toastOptions={{ duration: 2500 }} />
        {!isAuthPage && <Topbar />}
        {!isAuthPage && isAuthenticated && <HealthRibbon />}
        <Routes>
          <Route path="/remote-agents" element={<ProtectedRoute><ErrorBoundary fallbackTitle="Remote Agents failed to load"><RemoteAgents /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/dashboard"   element={<ProtectedRoute><ErrorBoundary fallbackTitle="Dashboard failed to load"><Dashboard /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/alerts"      element={<ProtectedRoute><ErrorBoundary fallbackTitle="Alerts failed to load"><Alerts /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/assistant"   element={<ProtectedRoute><ErrorBoundary fallbackTitle="AI Assistant failed to load"><AIAssistant /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/settings"    element={<ProtectedRoute><ErrorBoundary fallbackTitle="Settings failed to load"><Settings /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/register"    element={<Register />} />
          <Route path="/redeem"      element={<Navigate to="/accept-invite" replace />} />
          <Route path="/accept-invite"   element={<AcceptInvite />} />
          <Route path="/auth/callback"   element={<AuthCallback />} />
          <Route path="/login"            element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password"  element={<ResetPassword />} />
          <Route path="/forbidden"       element={<Forbidden />} />
          <Route path="/"            element={<Navigate to="/remote-agents" replace />} />
          <Route path="*"            element={<Navigate to="/remote-agents" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <ThemeProvider>
        <AuthProvider>
          <AppShell />
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}
