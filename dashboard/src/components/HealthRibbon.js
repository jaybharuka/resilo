import React, { useEffect, useState } from 'react';
import { apiService, actionsApi, realTimeService } from '../services/api';
import { DIRECT_MODE } from '../services/api';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Simple exponential backoff intervals (ms)
const RETRY_STEPS = [2000, 4000, 8000, 15000];

export default function HealthRibbon() {
  const { isAuthenticated, role } = useAuth();
  const [health, setHealth] = useState({ status: 'checking', latency: null, lastChecked: null });
  const [actionsEnabled, setActionsEnabled] = useState(null); // null=unknown true/false
  const [attempt, setAttempt] = useState(0);
  const [sse, setSse] = useState(() => realTimeService.getSSEStatus());

  useEffect(() => {
    let cancelled = false;
    let timer = null;

    const probe = async () => {
      const start = performance.now();
      try {
        const res = await apiService.checkHealth();
        if (cancelled) return;
        const latency = Math.round(performance.now() - start);
        setHealth({ status: 'healthy', latency, lastChecked: new Date().toISOString() });
        // Only probe actions if authenticated (and preferably admin)
  if (isAuthenticated && role === 'admin') {
          try {
            const result = await actionsApi.memoryCleanup({ dryRun: true });
            if (cancelled) return;
            // If backend returns 403 or explicit disabled flag -> actions disabled
            const enabled = !(result?.error === 'System actions disabled' || result?.status === 'forbidden' || result?.code === 403);
            setActionsEnabled(enabled);
          } catch (e) {
            setActionsEnabled(false);
          }
        } else {
          setActionsEnabled(false);
        }
        // Reset attempt on success
        setAttempt(0);
        timer = setTimeout(probe, 10000); // steady-state every 10s
      } catch (err) {
        if (cancelled) return;
        const latency = Math.round(performance.now() - start);
        setHealth({ status: 'offline', latency, lastChecked: new Date().toISOString() });
        setActionsEnabled(false);
        const nextAttempt = Math.min(attempt + 1, RETRY_STEPS.length - 1);
        setAttempt(nextAttempt);
        timer = setTimeout(probe, RETRY_STEPS[nextAttempt]);
      }
    };

    probe();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [attempt, isAuthenticated, role]);

  useEffect(() => {
    const unsub = realTimeService.subscribe('sse-status', (st) => setSse(st));
    // Emit current on mount
    setSse(realTimeService.getSSEStatus());
    return () => { try { unsub && unsub(); } catch {} };
  }, []);

  const color = health.status === 'healthy' ? 'bg-green-500' : health.status === 'offline' ? 'bg-red-500' : 'bg-yellow-500';
  const pulse = health.status === 'healthy' ? 'animate-pulse' : '';

  return (
    <div className={`mb-4 rounded-md border border-gray-200 shadow-sm bg-white px-4 py-2 flex items-center justify-between text-sm`}>      
      <div className="flex items-center gap-2">
        <span className={`inline-block w-3 h-3 rounded-full ${color} ${pulse}`}></span>
        <span className="font-medium">Backend: {health.status}</span>
        {health.latency != null && (
          <span className="text-gray-500">{health.latency}ms</span>
        )}
        {DIRECT_MODE && (
          <span className="ml-2 px-2 py-0.5 text-xs rounded bg-indigo-50 text-indigo-700 border border-indigo-200">Direct Mode</span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="hidden sm:inline text-xs text-gray-600">
          SSE: {sse.enabled ? (sse.connected ? 'connected' : 'pending') : 'off'}
        </span>
        {actionsEnabled === true && <span className="text-green-600 font-medium">Actions Enabled</span>}
        {actionsEnabled === false && <span className="text-gray-500">Actions Disabled</span>}
        <Link to="/settings" className="text-xs text-blue-700 hover:underline">Settings</Link>
        <button
          onClick={() => setAttempt(a => a + 1)}
          className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
        >Refresh</button>
      </div>
    </div>
  );
}
