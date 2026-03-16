/* eslint-disable unicode-bom */
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import Systems from './components/Systems';
import AiInsights from './components/AiInsights';
import AIAssistant from './components/AIAssistant';
import Settings from './components/Settings';
import Alerts from './components/Alerts';
import Security from './components/Security';
import Register from './components/Register';
import Invites from './components/Invites';
import RedeemInvite from './components/RedeemInvite';
import Forbidden from './components/Forbidden';
import Analytics from './components/Analytics';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './components/Login';
import ThemeToggle from './components/ThemeToggle';
import HealthRibbon from './components/HealthRibbon';

function Topbar() {
  const { user, role, logout, isAuthenticated } = useAuth();
  const [refreshing, setRefreshing] = React.useState(false);
  const triggerRefresh = React.useCallback(() => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      window.dispatchEvent(new CustomEvent('aiops:refresh'));
    } catch {}
    setTimeout(() => setRefreshing(false), 800);
  }, [refreshing]);

  return (
    <div className="mb-4 flex items-center justify-end gap-3">
      {isAuthenticated && (
        <span className="inline-flex items-center gap-2 text-sm text-gray-600">
          <span className={`px-2 py-0.5 rounded-full border text-xs ${role === 'admin' ? 'border-amber-300 bg-amber-50 text-amber-800' : 'border-emerald-300 bg-emerald-50 text-emerald-800'}`}>
            {role === 'admin' ? 'Admin' : 'Employee'}
          </span>
          {user?.email && <span className="hidden sm:inline text-gray-700">{user.email}</span>}
        </span>
      )}
      <button onClick={triggerRefresh} className={`text-sm px-3 py-1.5 rounded-md border border-gray-200 ${refreshing ? 'opacity-60' : 'hover:bg-gray-50'}`}>
        {refreshing ? 'Refreshing…' : 'Refresh'}
      </button>
      <ThemeToggle />
      {isAuthenticated && (
        <button onClick={logout} className="ml-2 text-sm text-gray-600 hover:text-gray-900 px-3 py-1.5 border border-gray-200 rounded-md">Logout</button>
      )}
    </div>
  );
}

function AppShell() {
  const { isAuthenticated } = useAuth();
  return (
    <div className="min-h-screen" style={{ backgroundColor: 'rgb(var(--bg))', color: 'rgb(var(--text))' }}>
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6">
          <Toaster position="top-right" toastOptions={{ duration: 2500 }} />
          <Topbar />
          {isAuthenticated && <HealthRibbon />}
          <Routes>
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/systems" element={<ProtectedRoute><Systems /></ProtectedRoute>} />
            <Route path="/ai-insights" element={<ProtectedRoute><AiInsights /></ProtectedRoute>} />
            <Route path="/assistant" element={<ProtectedRoute><AIAssistant /></ProtectedRoute>} />
            <Route path="/alerts" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
            <Route path="/security" element={<ProtectedRoute requireRole="admin"><Security /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
            <Route path="/invites" element={<ProtectedRoute requireRole="admin"><Invites /></ProtectedRoute>} />
            <Route path="/register" element={<Register />} />
            <Route path="/redeem" element={<RedeemInvite />} />
            <Route path="/analytics" element={<ProtectedRoute><Analytics /></ProtectedRoute>} />
            <Route path="/login" element={<Login />} />
            <Route path="/forbidden" element={<Forbidden />} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
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
