/* eslint-disable unicode-bom */
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import AIAssistant from './components/AIAssistant';
import Settings from './components/Settings';
import Alerts from './components/Alerts';
import Security from './components/Security';
import Register from './components/Register';
import Forbidden from './components/Forbidden';
import Insights from './components/Insights';
import Remediation from './components/Remediation';
import Analytics from './components/Analytics';
import InfraHub from './components/InfraHub';
import MTTRDashboard from './components/MTTRDashboard';
import OnboardingWizard from './components/OnboardingWizard';
import NotificationSettings from './components/resilo/NotificationSettings';
import ErrorBoundary from './components/ErrorBoundary';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './components/Login';
import ForgotPassword from './components/ForgotPassword';
import ResetPassword from './components/ResetPassword';
import AcceptInvite from './components/AcceptInvite';
import HealthRibbon from './components/HealthRibbon';
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
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginBottom: '20px', gap: '8px' }}>
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
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const hideSidebar = location.pathname === '/login';
  return (
    <div className="min-h-screen flex" style={{ backgroundColor: 'rgb(var(--bg))', color: 'rgb(var(--text))' }}>
      {!hideSidebar && <Sidebar />}
      <main
        className="flex-1 min-w-0 px-6 py-5 overflow-y-auto"
        style={{ background: 'rgb(var(--bg))', marginLeft: hideSidebar ? 0 : undefined }}
      >
        <Toaster position="top-right" toastOptions={{ duration: 2500 }} />
        <Topbar />
        {isAuthenticated && <HealthRibbon />}
        <Routes>
          <Route path="/dashboard"   element={<ProtectedRoute><ErrorBoundary fallbackTitle="Dashboard failed to load"><Dashboard /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/onboarding"  element={<ProtectedRoute><ErrorBoundary fallbackTitle="Onboarding failed to load"><OnboardingWizard /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/insights"    element={<ProtectedRoute><ErrorBoundary fallbackTitle="Insights failed to load"><Insights /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/assistant"   element={<ProtectedRoute><ErrorBoundary fallbackTitle="AI Assistant failed to load"><AIAssistant /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/alerts"      element={<ProtectedRoute><ErrorBoundary fallbackTitle="Alerts failed to load"><Alerts /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/remediation" element={<ProtectedRoute><ErrorBoundary fallbackTitle="Remediation failed to load"><Remediation /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/security"    element={<ProtectedRoute requireRole="admin"><ErrorBoundary fallbackTitle="Security failed to load"><Security /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/settings"    element={<ProtectedRoute><ErrorBoundary fallbackTitle="Settings failed to load"><Settings /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/analytics"   element={<ProtectedRoute><ErrorBoundary fallbackTitle="Analytics failed to load"><Analytics /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/mttr"        element={<ProtectedRoute><ErrorBoundary fallbackTitle="MTTR Dashboard failed to load"><MTTRDashboard /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/infra"       element={<ProtectedRoute><ErrorBoundary fallbackTitle="Infrastructure Hub failed to load"><InfraHub /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/devices"       element={<Navigate to="/infra" replace />} />
          <Route path="/users"         element={<Navigate to="/infra" replace />} />
          <Route path="/remote-agents" element={<Navigate to="/infra" replace />} />
          <Route path="/invites"       element={<Navigate to="/infra" replace />} />
          <Route path="/notifications" element={<ProtectedRoute><ErrorBoundary fallbackTitle="Notifications failed to load"><NotificationSettings /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/register"    element={<Register />} />
          <Route path="/redeem"      element={<Navigate to="/accept-invite" replace />} />
          <Route path="/accept-invite"   element={<AcceptInvite />} />
          <Route path="/login"            element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password"  element={<ResetPassword />} />
          <Route path="/forbidden"       element={<Forbidden />} />
          <Route path="/"            element={<Navigate to="/dashboard" replace />} />
          <Route path="*"            element={<Navigate to="/dashboard" replace />} />
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
