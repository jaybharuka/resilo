import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children, requireRole }) {
  const { isAuthenticated, loading, role } = useAuth();
  const location = useLocation();

  // Firebase is still initialising — show nothing to avoid a flicker redirect
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (requireRole && role !== requireRole) {
    return <Navigate to="/forbidden" replace />;
  }
  return children;
}
