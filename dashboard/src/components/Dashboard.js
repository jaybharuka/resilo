import React, { useState, useEffect, useCallback } from 'react';
import { agentsApi, alertsApi, coreAxios } from '../services/resiloApi';
import { Monitor, AlertTriangle, Bot, CheckCircle, Activity, Zap, Server, RefreshCw } from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };
const UI      = { fontFamily: "'Outfit', sans-serif" };

const PANEL = {
  background: 'rgb(22, 20, 16)',
  border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: '12px',
  boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
};

const C = {
  bg: 'rgb(14,13,11)', surface: 'rgb(22,20,16)', surface2: 'rgb(31,29,24)',
  border: 'rgba(42,40,32,0.9)', amber: '#F59E0B', teal: '#2DD4BF',
  red: '#F87171', text1: '#F5F0E8', text2: '#A89F8C', text3: '#6B6357', text4: '#4A443D',
};

function fmtTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return '—'; }
}

function CountCard({ icon, label, value, sub, color }) {
  return (
    <div style={{ ...PANEL, padding: '20px 22px', borderTop: `2px solid ${color}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{ color }}>{icon}</span>
        <span style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.text4 }}>{label}</span>
      </div>
      <div style={{ ...DISPLAY, fontSize: '3rem', lineHeight: 1, color: C.text1, marginBottom: 6 }}>{value}</div>
      {sub && <div style={{ ...MONO, fontSize: 10, color: C.text3 }}>{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [agents,    setAgents]    = useState([]);
  const [alerts,    setAlerts]    = useState([]);
  const [sysHealth, setSysHealth] = useState(null);
  const [loading,   setLoading]   = useState(true);

  const load = useCallback(async () => {
    try {
      const [ag, al] = await Promise.all([agentsApi.list(), alertsApi.list()]);
      setAgents(Array.isArray(ag) ? ag : []);
      setAlerts(Array.isArray(al) ? al : []);
    } catch {}
    try {
      const r = await coreAxios.get('/api/health/system');
      setSysHealth(r.data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const liveAgents    = agents.filter(a => a.status === 'live');
  const offlineAgents = agents.filter(a => a.status === 'offline');
  const pendingAgents = agents.filter(a => a.status === 'pending');

  const criticalAlerts = alerts.filter(a => a.severity === 'critical');
  const highAlerts     = alerts.filter(a => a.severity === 'high');
  const medAlerts      = alerts.filter(a => a.severity === 'medium' || a.severity === 'warning');

  const needsAttention = liveAgents
    .filter(a => (a.cpu ?? 0) >= 85 || (a.memory ?? 0) >= 90 || (a.disk ?? 0) >= 95)
    .sort((a, b) => Math.max(b.cpu ?? 0, b.memory ?? 0, b.disk ?? 0) - Math.max(a.cpu ?? 0, a.memory ?? 0, a.disk ?? 0))
    .slice(0, 5);

  const recentDecisions = agents.flatMap(a =>
    (a.ai_history || []).map(d => ({ ...d, agent_label: a.label }))
  ).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 10);

  const allDecisionSources = recentDecisions.map(d => d.decision_source);
  const onlyRuleFallback = allDecisionSources.length > 0 && allDecisionSources.every(s => s === 'rule_fallback');

  const ai_color = sysHealth?.ai_service === 'online' ? C.teal : sysHealth?.ai_service === 'degraded' ? C.amber : C.red;
  const db_color = sysHealth?.database === 'online' ? C.teal : C.red;

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 24 }}>
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>

      {/* Rule-fallback warning banner — shown when NVIDIA_API_KEY is not set */}
      {onlyRuleFallback && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderRadius: 8, background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.35)' }}>
          <AlertTriangle size={14} color={C.amber} style={{ flexShrink: 0 }} />
          <span style={{ ...MONO, fontSize: 11, color: C.amber }}>AI RUNNING IN RULE FALLBACK MODE</span>
          <span style={{ ...UI, fontSize: 12, color: C.text2, marginLeft: 4 }}>— NVIDIA_API_KEY not set in production. Decisions are lookup-table rules, not LLM analysis. Set the key in Render → Environment to enable real AI.</span>
        </div>
      )}

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', color: C.text1, margin: 0, lineHeight: 1 }}>Dashboard</h1>
          <p style={{ ...MONO, fontSize: 11, letterSpacing: '0.1em', color: C.text4, margin: '6px 0 0' }}>RESILO OPERATIONS OVERVIEW</p>
        </div>
        <button onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 8, background: 'transparent', border: `1px solid ${C.border}`, color: C.text3, cursor: 'pointer', ...MONO, fontSize: 11 }}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {/* Agent count cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <CountCard icon={<Monitor size={14} />}   label="LIVE AGENTS"    value={liveAgents.length}    color={C.teal}  sub={`${offlineAgents.length} offline`} />
        <CountCard icon={<AlertTriangle size={14} />} label="CRITICAL"   value={criticalAlerts.length} color={C.red}   sub={`${highAlerts.length} high`} />
        <CountCard icon={<AlertTriangle size={14} />} label="HIGH"        value={highAlerts.length}    color={C.amber} sub={`${medAlerts.length} medium`} />
        <CountCard icon={<Activity size={14} />}  label="TOTAL AGENTS"  value={agents.length}         color={C.text3} sub={`${pendingAgents.length} pending`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Agents needing attention */}
        <div style={PANEL}>
          <div style={{ padding: '14px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
            <AlertTriangle size={14} color={C.amber} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>AGENTS NEEDING ATTENTION</span>
            {needsAttention.length > 0 && (
              <span style={{ marginLeft: 6, ...MONO, fontSize: 10, background: `${C.amber}18`, color: C.amber, border: `1px solid ${C.amber}40`, borderRadius: 10, padding: '1px 8px' }}>{needsAttention.length}</span>
            )}
          </div>
          {loading ? (
            <div style={{ padding: '32px 0', textAlign: 'center' }}><span style={{ ...MONO, fontSize: 11, color: C.text4 }}>LOADING…</span></div>
          ) : needsAttention.length === 0 ? (
            <div style={{ padding: '32px 0', textAlign: 'center' }}>
              <CheckCircle size={28} color={C.teal} style={{ display: 'block', margin: '0 auto 10px', opacity: 0.7 }} />
              <span style={{ ...MONO, fontSize: 11, color: C.text4 }}>All agents healthy</span>
            </div>
          ) : (
            <div style={{ padding: '12px 22px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {needsAttention.map(a => {
                const top = Math.max(a.cpu ?? 0, a.memory ?? 0, a.disk ?? 0);
                const col = top >= 95 ? C.red : C.amber;
                return (
                  <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', borderRadius: 8, background: `${col}08`, border: `1px solid ${col}25` }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: col, flexShrink: 0, animation: 'pulse 1.5s ease-in-out infinite' }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ ...UI, fontSize: 13, fontWeight: 600, color: C.text1 }}>{a.label}</span>
                      <span style={{ ...MONO, fontSize: 10, color: C.text4, marginLeft: 8 }}>{a.hostname}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 12, ...MONO, fontSize: 10 }}>
                      {a.cpu    >= 85 && <span style={{ color: C.red }}>CPU {a.cpu?.toFixed(0)}%</span>}
                      {a.memory >= 90 && <span style={{ color: C.amber }}>MEM {a.memory?.toFixed(0)}%</span>}
                      {a.disk   >= 95 && <span style={{ color: C.red }}>DISK {a.disk?.toFixed(0)}%</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Recent AI decisions */}
        <div style={PANEL}>
          <div style={{ padding: '14px 22px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Bot size={14} color={C.teal} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>RECENT AI DECISIONS</span>
            {recentDecisions.length > 0 && (
              <span style={{ marginLeft: 6, ...MONO, fontSize: 10, background: `${C.teal}18`, color: C.teal, border: `1px solid ${C.teal}40`, borderRadius: 10, padding: '1px 8px' }}>{recentDecisions.length}</span>
            )}
          </div>
          {loading ? (
            <div style={{ padding: '32px 0', textAlign: 'center' }}><span style={{ ...MONO, fontSize: 11, color: C.text4 }}>LOADING…</span></div>
          ) : recentDecisions.length === 0 ? (
            <div style={{ padding: '32px 0', textAlign: 'center' }}>
              <Bot size={28} color={C.text4} style={{ display: 'block', margin: '0 auto 10px', opacity: 0.4 }} />
              <span style={{ ...MONO, fontSize: 11, color: C.text4 }}>No AI decisions yet</span>
            </div>
          ) : (
            <div style={{ padding: '8px 22px', display: 'flex', flexDirection: 'column', gap: 0, overflowY: 'auto', maxHeight: 340 }}>
              {recentDecisions.map((d, i) => {
                const isFallback = d.decision_source === 'rule_fallback';
                const srcColor   = isFallback ? C.amber : C.teal;
                return (
                  <div key={i} style={{ padding: '10px 0', borderBottom: i < recentDecisions.length - 1 ? `1px solid rgba(42,40,32,0.5)` : 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                      <span style={{ ...MONO, fontSize: 9, padding: '1px 6px', borderRadius: 4, background: `${srcColor}15`, border: `1px solid ${srcColor}30`, color: srcColor }}>
                        {isFallback ? 'RULE' : 'AI'}
                      </span>
                      <span style={{ ...MONO, fontSize: 10, color: C.amber }}>{d.alert_category?.toUpperCase()}</span>
                      <span style={{ ...MONO, fontSize: 10, color: C.text4, marginLeft: 'auto' }}>{d.agent_label} · {fmtTime(d.timestamp)}</span>
                    </div>
                    {d.root_cause && <p style={{ ...UI, fontSize: 12, color: C.text2, margin: 0 }}>{d.root_cause}</p>}
                    {d.recommended_action && (
                      <span style={{ ...MONO, fontSize: 10, color: C.teal, display: 'flex', alignItems: 'center', gap: 5, marginTop: 4 }}>
                        <Zap size={9} /> {d.recommended_action}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

      </div>

      {/* System status bar */}
      {sysHealth && (
        <div style={{ ...PANEL, padding: '14px 22px', display: 'flex', gap: 0, flexWrap: 'wrap', overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 24 }}>
            <Server size={13} color={C.amber} />
            <span style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: C.text4 }}>SYSTEM STATUS</span>
          </div>
          {[
            { label: 'AI SERVICE', value: sysHealth.ai_service?.toUpperCase(),  color: ai_color },
            { label: 'DATABASE',   value: sysHealth.database?.toUpperCase(),    color: db_color },
            { label: 'LIVE',       value: String(sysHealth.agents_live),         color: C.teal  },
            { label: 'OFFLINE',    value: String(sysHealth.agents_offline),      color: C.red   },
            { label: 'OPEN ALERTS',value: String(sysHealth.open_alerts),         color: sysHealth.open_alerts > 0 ? C.amber : C.text3 },
            { label: 'LAST AI CALL', value: fmtTime(sysHealth.last_ai_call_at), color: C.text2 },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 20px', borderLeft: `1px solid ${C.border}` }}>
              <span style={{ ...MONO, fontSize: 9, letterSpacing: '0.1em', color: C.text4 }}>{label}</span>
              <span style={{ ...MONO, fontSize: 11, color }}>{value}</span>
            </div>
          ))}
        </div>
      )}

    </div>
  );
}
