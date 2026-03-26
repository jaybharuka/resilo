/**
 * MetricsConsent.js
 *
 * One-time consent banner shown after login.
 * Key is scoped to the user ID so each account gets its own prompt.
 * Automatically re-shows if the user has never consented on this browser.
 *
 * When the user clicks ALLOW:
 *   - Collects CPU/memory/network from local agent (localhost:9090) or browser APIs
 *   - Pushes to backend every 10 s so the dashboard shows this machine's data
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Monitor, X, Cpu, CheckCircle, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { startMetricsPush, stopMetricsPush, isLocalAgentAvailable } from '../services/browserMetrics';
import { resiloApi } from '../services/resiloApi';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

function consentKey(userId) {
  return `aiops:metrics_consent:${userId || 'anon'}`;
}

export default function MetricsConsent() {
  const { user, isAuthenticated } = useAuth();
  const [visible,      setVisible]      = useState(false);
  const [granted,      setGranted]      = useState(false);
  const [pushError,    setPushError]    = useState(null);
  const [source,       setSource]       = useState(null);
  const [showAgentTip, setShowAgentTip] = useState(false);
  const pushStarted = useRef(false);

  // ── Detect consent state for this user ──────────────────────────────────
  useEffect(() => {
    if (!isAuthenticated || !user?.id) return;

    const stored = localStorage.getItem(consentKey(user.id));
    if (stored === 'granted') {
      if (!pushStarted.current) _startPush();
    } else if (!stored) {
      const t = setTimeout(() => setVisible(true), 1200);
      return () => clearTimeout(t);
    }
    // 'dismissed' → stay hidden
  }, [isAuthenticated, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Start push loop ──────────────────────────────────────────────────────
  const _startPush = useCallback(async () => {
    if (!user?.org_id || pushStarted.current) return;
    pushStarted.current = true;
    setPushError(null);

    startMetricsPush(async (metrics) => {
      try {
        await resiloApi.pushBrowserMetrics(user.org_id, metrics);
        setSource(metrics.source);
        setPushError(null);
      } catch (err) {
        setPushError('Could not reach backend');
      }
    }, 10_000);

    // Surface source label after first collection
    setTimeout(() => {
      setSource(isLocalAgentAvailable() ? 'local-agent' : 'browser');
    }, 2500);
  }, [user]);

  const handleAllow = useCallback(async () => {
    localStorage.setItem(consentKey(user?.id), 'granted');
    setGranted(true);
    await _startPush();
    setTimeout(() => setVisible(false), 1800);
  }, [user, _startPush]);

  const handleDismiss = useCallback(() => {
    localStorage.setItem(consentKey(user?.id), 'dismissed');
    setVisible(false);
    stopMetricsPush();
    pushStarted.current = false;
  }, [user]);

  // ── Status chip (visible after consent granted) ──────────────────────────
  if (!visible && granted && source) {
    return (
      <div style={{
        position: 'fixed', bottom: '20px', right: '20px', zIndex: 9999,
        background: 'rgb(22,20,16)',
        border: `1px solid ${pushError ? 'rgba(239,68,68,0.3)' : 'rgba(45,212,191,0.3)'}`,
        borderRadius: '10px', padding: '8px 14px',
        display: 'flex', alignItems: 'center', gap: '8px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
      }}>
        {pushError
          ? <AlertCircle size={13} color="#EF4444" />
          : <CheckCircle  size={13} color="#2DD4BF" />}
        <span style={{ ...MONO, fontSize: '10px', color: pushError ? '#EF4444' : '#2DD4BF',
          letterSpacing: '0.08em' }}>
          {pushError ? 'metrics offline' : `monitoring · ${source}`}
        </span>
      </div>
    );
  }

  if (!visible) return null;

  return (
    <div style={{
      position: 'fixed', bottom: '24px', right: '24px', zIndex: 9999,
      background: 'rgb(18,17,13)',
      border: '1px solid rgba(245,158,11,0.25)',
      borderRadius: '16px', padding: '20px 22px',
      width: '340px',
      boxShadow: '0 20px 60px rgba(0,0,0,0.7)',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '34px', height: '34px', borderRadius: '9px',
            background: 'rgba(245,158,11,0.08)',
            border: '1px solid rgba(245,158,11,0.18)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Monitor size={16} color="#F59E0B" />
          </div>
          <div>
            <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.12em', color: '#F59E0B' }}>
              SYSTEM MONITORING
            </div>
            <div style={{ ...UI, fontSize: '11px', color: '#4A443D', marginTop: '1px' }}>
              for this machine
            </div>
          </div>
        </div>
        <button onClick={handleDismiss}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#3A342D', padding: '2px' }}>
          <X size={14} />
        </button>
      </div>

      <p style={{ ...UI, fontSize: '13px', color: '#7A7068', lineHeight: 1.6, marginBottom: '16px' }}>
        Allow Resilo to collect <strong style={{ color: '#C9C0B4' }}>CPU, memory, and network
        metrics</strong> from this machine and send them to your dashboard in real time?
      </p>

      {/* Agent tip */}
      <div
        onClick={() => setShowAgentTip(v => !v)}
        style={{
          ...MONO, fontSize: '10px', color: '#4A443D', cursor: 'pointer',
          marginBottom: showAgentTip ? '10px' : '16px',
          display: 'flex', alignItems: 'center', gap: '6px',
          userSelect: 'none',
        }}
      >
        <Cpu size={11} color="#6B6357" />
        <span>Run local agent for real CPU &amp; disk %</span>
        <span style={{ color: '#3A342D', marginLeft: 'auto' }}>{showAgentTip ? '▲' : '▼'}</span>
      </div>

      {showAgentTip && (
        <div style={{
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(40,38,30,1)',
          borderRadius: '8px', padding: '10px 12px', marginBottom: '16px',
        }}>
          <div style={{ ...MONO, fontSize: '10px', color: '#6B6357', marginBottom: '6px' }}>
            Run once on this machine:
          </div>
          <code style={{ ...MONO, fontSize: '11px', color: '#F59E0B' }}>
            pip install psutil
          </code>
          <br />
          <code style={{ ...MONO, fontSize: '11px', color: '#F59E0B' }}>
            python local_agent.py
          </code>
          <div style={{ ...MONO, fontSize: '10px', color: '#3A342D', marginTop: '6px' }}>
            Serves real metrics at localhost:9090 · auto-detected by the dashboard
          </div>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button onClick={handleAllow} style={{
          flex: 1, padding: '11px',
          borderRadius: '9px',
          background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
          border: 'none', cursor: 'pointer',
          ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#0C0B09', fontWeight: 700,
        }}>
          ALLOW
        </button>
        <button onClick={handleDismiss} style={{
          flex: 1, padding: '11px',
          borderRadius: '9px',
          background: 'transparent',
          border: '1px solid rgba(40,38,30,1)',
          cursor: 'pointer',
          ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#3A342D',
        }}>
          NOT NOW
        </button>
      </div>
    </div>
  );
}

/** Call this from the logout handler to restart consent on next login */
export function clearMetricsConsent(userId) {
  try {
    localStorage.removeItem(consentKey(userId));
    stopMetricsPush();
  } catch { /* ignore */ }
}
