import React, { useEffect, useState } from 'react';
import { Clock3, AlertTriangle, Wrench, TimerReset } from 'lucide-react';
import { apiService } from '../services/api';

const C = {
  surface: 'rgb(22,20,16)',
  border: 'rgba(42,40,32,1)',
  amber: '#F59E0B',
  teal: '#2DD4BF',
  red: '#F87171',
  text1: 'rgb(245,240,232)',
  text2: 'rgb(168,159,140)',
  text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace",
};

function fmt(v) {
  if (!Number.isFinite(v)) return '0s';
  if (v < 60) return `${Math.round(v)}s`;
  return `${Math.floor(v / 60)}m ${Math.round(v % 60)}s`;
}

function Stat({ icon, label, value, color }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <span style={{ color }}>{icon}</span>
        <span style={{ color: C.text3, fontSize: 10, letterSpacing: '0.08em', fontFamily: C.mono }}>{label}</span>
      </div>
      <div style={{ color: C.text1, fontSize: 24, fontFamily: "'Bebas Neue', sans-serif" }}>{value}</div>
    </div>
  );
}

export default function MTTRDashboard() {
  const [data, setData] = useState({ incident_count: 0, timeline: [] });

  useEffect(() => {
    apiService.getMttrDashboard(14).then((d) => setData(d || { incident_count: 0, timeline: [] }));
  }, []);

  return (
    <div style={{ padding: 24, maxWidth: 1100, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, color: C.text1, fontFamily: "'Outfit', sans-serif" }}>MTTR Dashboard</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12 }}>
        <Stat icon={<AlertTriangle size={14} />} label="INCIDENTS" value={data.incident_count || 0} color={C.red} />
        <Stat icon={<Clock3 size={14} />} label="TTD AVG" value={fmt(data.ttd_avg_seconds || 0)} color={C.teal} />
        <Stat icon={<Wrench size={14} />} label="TTR AVG" value={fmt(data.ttr_avg_seconds || 0)} color={C.amber} />
        <Stat icon={<TimerReset size={14} />} label="MTTR AVG" value={fmt(data.mttr_avg_seconds || 0)} color={C.amber} />
      </div>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${C.border}`, color: C.text2, fontFamily: C.mono, fontSize: 11 }}>INCIDENT TIMELINE</div>
        {data.timeline?.length ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                {['Action','Status','TTD','TTR','MTTR'].map((h) => <th key={h} style={{ textAlign: 'left', padding: '10px 16px', color: C.text3, fontFamily: C.mono, fontSize: 10 }}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.timeline.slice(0, 30).map((row) => (
                <tr key={row.incident_id} style={{ borderBottom: `1px solid ${C.border}` }}>
                  <td style={{ padding: '10px 16px', color: C.text1, fontSize: 12 }}>{String(row.action || '').replace(/_/g, ' ')}</td>
                  <td style={{ padding: '10px 16px', color: row.status === 'success' ? C.teal : C.red, fontSize: 12 }}>{row.status}</td>
                  <td style={{ padding: '10px 16px', color: C.text2, fontFamily: C.mono, fontSize: 11 }}>{fmt(row.ttd_seconds || 0)}</td>
                  <td style={{ padding: '10px 16px', color: C.text2, fontFamily: C.mono, fontSize: 11 }}>{fmt(row.ttr_seconds || 0)}</td>
                  <td style={{ padding: '10px 16px', color: C.text2, fontFamily: C.mono, fontSize: 11 }}>{fmt(row.mttr_seconds || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={{ padding: 16, color: C.text3 }}>No incidents yet.</div>}
      </div>
    </div>
  );
}
