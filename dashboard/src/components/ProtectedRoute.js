import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children, requireRole }) {
  const { role } = useAuth();
  if (requireRole && role !== requireRole) {
    return <Navigate to="/forbidden" replace />;
  }
  return children;
}
