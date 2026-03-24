import React, { useEffect, useState } from 'react';
import { apiService, actionsApi, realTimeService } from '../services/api';
import { DIRECT_MODE } from '../services/api';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { RefreshCw } from 'lucide-react';
import InfoTip from './InfoTip';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };

const RETRY_STEPS = [2000, 4000, 8000, 15000];

export default function HealthRibbon() {
  const { isAuthenticated, role } = useAuth();
  const [health, setHealth] = useState({ status: 'checking', latency: null });
  const [actionsEnabled, setActionsEnabled] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const [sse, setSse] = useState(() => realTimeService.getSSEStatus());

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const probe = async () => {
      const start = performance.now();
      try {
        await apiService.checkHealth();
        if (cancelled) return;
        const latency = Math.round(performance.now() - start);
        setHealth({ status: 'healthy', latency });
        if (isAuthenticated && role === 'admin') {
          try {
            const result = await actionsApi.memoryCleanup({ dryRun: true });
            if (!cancelled) setActionsEnabled(
              !(result?.error === 'System actions disabled' || result?.status === 'forbidden' || result?.code === 403)
            );
          } catch { setActionsEnabled(false); }
        } else { setActionsEnabled(false); }
        setAttempt(0);
        timer = setTimeout(probe, 10000);
      } catch {
        if (cancelled) return;
        const latency = Math.round(performance.now() - start);
        setHealth({ status: 'offline', latency });
        setActionsEnabled(false);
        const next = Math.min(attempt + 1, RETRY_STEPS.length - 1);
        setAttempt(next);
        timer = setTimeout(probe, RETRY_STEPS[next]);
      }
    };
    probe();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [attempt, isAuthenticated, role]);

  useEffect(() => {
    const unsub = realTimeService.subscribe('sse-status', (st) => setSse(st));
    setSse(realTimeService.getSSEStatus());
    return () => { try { unsub?.(); } catch {} };
  }, []);

  const isHealthy = health.status === 'healthy';
  const isOffline = health.status === 'offline';

  const dotClass = isHealthy ? 'dot-healthy animate-pulse' : isOffline ? 'dot-offline' : 'dot-checking animate-pulse';
  const labelColor = isHealthy ? '#2DD4BF' : isOffline ? '#F87171' : '#F59E0B';

  return (
    <div
      className="health-ribbon mb-4 flex items-center gap-3 px-4 py-2 rounded-lg"
      style={{
        background: 'rgba(22,20,16,0.7)',
        border: '1px solid rgba(42,40,32,0.8)',
        backdropFilter: 'blur(8px)',
        ...MONO,
        fontSize: '11px',
        letterSpacing: '0.06em',
      }}
    >
      {/* Status dot */}
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`} />

      {/* Backend status */}
      <span style={{ color: labelColor }}>
        {isHealthy ? 'BACKEND ONLINE' : isOffline ? 'BACKEND OFFLINE' : 'CHECKING…'}
      </span>

      {health.latency != null && (
        <span style={{ color: '#4A443D', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
          {health.latency}ms
          <InfoTip size={12} info="Round-trip latency to the backend API server measured at last health check. Values above 500ms may indicate server load or network issues." />
        </span>
      )}

      {DIRECT_MODE && (
        <span
          style={{
            padding: '2px 7px',
            borderRadius: '4px',
            background: 'rgba(245,158,11,0.1)',
            color: '#F59E0B',
            border: '1px solid rgba(245,158,11,0.2)',
            fontSize: '10px',
          }}
        >
          DIRECT
        </span>
      )}

      <span style={{ color: '#3A342D' }}>·</span>

      {/* SSE status */}
      <span style={{ color: '#4A443D', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
        SSE:{' '}
        <span style={{ color: sse.enabled ? (sse.connected ? '#2DD4BF' : '#F59E0B') : '#4A443D' }}>
          {sse.enabled ? (sse.connected ? 'LIVE' : 'PENDING') : 'OFF'}
        </span>
        <InfoTip size={12} info="Server-Sent Events stream from the backend. LIVE means real-time push updates are active. PENDING means the connection is being established. OFF means SSE is disabled and the app falls back to polling." />
      </span>

      {/* Actions */}
      {actionsEnabled === true && (
        <span
          style={{
            padding: '2px 7px',
            borderRadius: '4px',
            background: 'rgba(45,212,191,0.08)',
            color: '#2DD4BF',
            border: '1px solid rgba(45,212,191,0.18)',
            fontSize: '10px',
          }}
        >
          ACTIONS ON
        </span>
      )}
      {actionsEnabled === false && isAuthenticated && role === 'admin' && (
        <span style={{ color: '#4A443D' }}>ACTIONS OFF</span>
      )}

      <span style={{ flex: 1 }} />

      <Link
        to="/settings"
        style={{ color: '#6B6357', textDecoration: 'none', transition: 'color 0.15s' }}
        onMouseEnter={e => { e.target.style.color = '#F59E0B'; }}
        onMouseLeave={e => { e.target.style.color = '#6B6357'; }}
      >
        SETTINGS
      </Link>

      <button
        onClick={() => setAttempt(a => a + 1)}
        style={{
          padding: '3px',
          borderRadius: '4px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: '#4A443D',
          display: 'flex',
          alignItems: 'center',
          transition: 'color 0.15s',
        }}
        title="Refresh backend check"
        onMouseEnter={e => { e.currentTarget.style.color = '#F59E0B'; }}
        onMouseLeave={e => { e.currentTarget.style.color = '#4A443D'; }}
      >
        <RefreshCw size={11} />
      </button>
    </div>
  );
}
