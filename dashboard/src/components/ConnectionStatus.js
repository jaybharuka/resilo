import React, { useState, useEffect } from 'react';
import { realTimeService } from '../services/api';

const C = {
  teal: '#2DD4BF', amber: '#F59E0B', red: '#F87171',
  text3: 'rgb(107,99,87)', mono: "'IBM Plex Mono', monospace",
};

/**
 * ConnectionStatus — small dot + label in the Topbar.
 * Subscribes to the SSE status events from RealTimeService.
 */
export default function ConnectionStatus() {
  const [status, setStatus] = useState('connecting');

  useEffect(() => {
    const unsub = realTimeService.subscribe('sse-status', ({ connected, enabled }) => {
      if (!enabled)     setStatus('disabled');
      else if (connected) setStatus('live');
      else              setStatus('polling');
    });
    // Derive initial state from service
    setStatus(realTimeService.sseConnected ? 'live' : 'polling');
    return () => unsub && unsub();
  }, []);

  const meta = {
    live:       { color: C.teal,  label: 'LIVE',     title: 'Real-time stream connected'         },
    polling:    { color: C.amber, label: 'POLLING',  title: 'Polling every 5s (SSE offline)'     },
    disabled:   { color: C.text3, label: 'OFFLINE',  title: 'Real-time stream disabled'          },
    connecting: { color: C.amber, label: 'INIT',     title: 'Establishing connection…'           },
  }[status] || { color: C.text3, label: 'UNKNOWN', title: '' };

  return (
    <div title={meta.title} style={{ display: 'flex', alignItems: 'center', gap: 5, userSelect: 'none' }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%', background: meta.color, flexShrink: 0,
        boxShadow: status === 'live' ? `0 0 6px ${meta.color}90` : 'none',
        animation: status === 'live' || status === 'polling' ? 'pulse 2s infinite' : 'none',
      }} />
      <span style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.08em', color: C.text3 }}>
        {meta.label}
      </span>
    </div>
  );
}
