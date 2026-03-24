import React, { useState, useEffect } from 'react';
import { userApi, apiService } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Monitor, Users, Server, CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };
const UI = { fontFamily: "'Outfit', sans-serif" };
const PANEL = {
  background: 'rgb(22, 20, 16)',
  border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: '12px',
  boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
};

export default function TeamAndDevices() {
  const { role } = useAuth();
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        setLoading(true);
        const [usersData, devicesData] = await Promise.all([
          role === 'admin' ? userApi.list().catch(() => []) : Promise.resolve([]),
          apiService.getDevices().catch(() => [])
        ]);
        if (mounted) {
          setUsers(Array.isArray(usersData) ? usersData : []);
          setDevices(Array.isArray(devicesData) ? devicesData : []);
          setLoading(false);
        }
      } catch (err) {
        console.error(err);
        if (mounted) setLoading(false);
      }
    };
    fetchData();
    return () => { mounted = false; };
  }, [role]);

  const getStatusColor = (s) => {
    const s2 = (s || '').toLowerCase();
    if (s2 === 'online' || s2 === 'healthy') return '#2DD4BF';
    if (s2 === 'warning') return '#F59E0B';
    if (s2 === 'critical' || s2 === 'error') return '#F87171';
    return '#6B6357';
  };
  const getStatusIcon = (s) => {
    const color = getStatusColor(s);
    const s2 = (s || '').toLowerCase();
    if (s2 === 'online' || s2 === 'healthy') return <CheckCircle2 size={16} color={color} />;
    if (s2 === 'warning') return <AlertTriangle size={16} color={color} />;
    if (s2 === 'critical' || s2 === 'error') return <AlertCircle size={16} color={color} />;
    return <Monitor size={16} color={color} />;
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px', color: '#F5F0E8', ...UI }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', margin: 0, lineHeight: 1 }}>
            {role === 'admin' ? 'Users & Devices' : 'Devices'}
          </h1>
          <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: '#4A443D', marginTop: '6px' }}>
            RESOURCE MANAGEMENT
          </p>
        </div>
      </div>
      {loading ? (
        <div style={{ ...MONO, color: '#F59E0B', fontSize: '12px' }} className="animate-pulse">
          LOADING DATA...
        </div>
      ) : (
        <div className={`grid grid-cols-1 ${role === 'admin' ? 'lg:grid-cols-2' : 'lg:grid-cols-1'} gap-5`}>
          <div style={PANEL} className="flex flex-col">
            <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(42,40,32,0.9)', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Server size={16} color="#2DD4BF" />
              <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>FLEET STATUS</span>
              <span style={{ marginLeft: 'auto', background: 'rgba(45,212,191,0.1)', color: '#2DD4BF', padding: '2px 8px', borderRadius: '12px', ...MONO, fontSize: '10px' }}>
                {devices.length} TOTAL
              </span>
            </div>
            <div style={{ padding: '20px', flex: 1, display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {devices.length === 0 ? <p style={{ color: '#6B6357', fontSize: '13px' }}>No devices.</p> : devices.map((d, i) => (
                <div key={d.id || i} style={{ background: 'rgba(42,40,32,0.3)', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {getStatusIcon(d.status)}
                      <span style={{ fontWeight: 500, fontSize: '15px' }}>{d.name}</span>
                    </div>
                    <span style={{ ...MONO, fontSize: '10px', color: getStatusColor(d.status), textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {d.status}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {[ 
                      { l: 'CPU USAGE', v: d.cpu || 0, c: (d.cpu > 80 ? '#F87171' : '#F59E0B') },
                      { l: 'MEMORY', v: d.memory || 0, c: (d.memory > 85 ? '#F87171' : '#2DD4BF') },
                      { l: 'DISK', v: d.disk || 0, c: '#2DD4BF' }
                    ].map(m => (
                      <div key={m.l} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ ...MONO, fontSize: '9px', color: '#6B6357' }}>{m.l}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <div style={{ flex: 1, height: '4px', background: 'rgba(42,40,32,0.9)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${m.v}%`, background: m.c }} />
                          </div>
                          <span style={{ ...MONO, fontSize: '11px', color: '#A89F8C' }}>{m.v}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(42,40,32,0.5)', paddingTop: '10px', marginTop: '4px' }}>
                    <span style={{ fontSize: '11px', color: '#6B6357' }}><span style={MONO}>OS:</span> {d.os || 'Unknown'}</span>
                    <span style={{ fontSize: '11px', color: '#6B6357' }}><span style={MONO}>LAST SEEN:</span> {d.lastSeen ? new Date(d.lastSeen).toLocaleTimeString() : 'N/A'}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          {role === 'admin' && (
            <div style={PANEL} className="flex flex-col">
              <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(42,40,32,0.9)', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Users size={16} color="#F59E0B" />
                <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>ACTIVE USERS</span>
                <span style={{ marginLeft: 'auto', background: 'rgba(245,158,11,0.1)', color: '#F59E0B', padding: '2px 8px', borderRadius: '12px', ...MONO, fontSize: '10px' }}>
                  {users.length} REGISTERED
                </span>
              </div>
              <div style={{ padding: '20px', flex: 1, overflowY: 'auto' }}>
                <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['USER', 'ROLE', 'STATUS'].map((h, j) => <th key={j} style={{ paddingBottom: '12px', ...MONO, fontSize: '10px', color: '#6B6357', letterSpacing: '0.05em', borderBottom: '1px solid rgba(42,40,32,0.9)', textAlign: j===2?'right':'left' }}>{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {users.length === 0 ? (
                      <tr><td colSpan={3} style={{ paddingTop: '20px', color: '#6B6357', fontSize: '13px', textAlign: 'center' }}>No users.</td></tr>
                    ) : users.map((u, i) => (
                      <tr key={u.id || i} style={{ borderBottom: '1px solid rgba(42,40,32,0.4)' }}>
                        <td style={{ padding: '12px 0' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{ width: '28px', height: '28px', borderRadius: '6px', background: 'rgba(245,158,11,0.1)', color: '#F59E0B', display: 'flex', alignItems: 'center', justifyContent: 'center', ...MONO, fontSize: '12px' }}>
                              {(u.full_name || u.username || 'U').charAt(0).toUpperCase()}
                            </div>
                            <div>
                              <div style={{ fontSize: '13px', fontWeight: 500 }}>{u.full_name || u.username}</div>
                              <div style={{ ...MONO, fontSize: '10px', color: '#6B6357' }}>{u.email}</div>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: '12px 0' }}>
                          <span style={{ padding: '2px 8px', borderRadius: '12px', ...MONO, fontSize: '10px', background: u.role === 'admin' ? 'rgba(248,113,113,0.1)' : 'rgba(45,212,191,0.1)', color: u.role === 'admin' ? '#F87171' : '#2DD4BF' }}>
                            {u.role ? u.role.toUpperCase() : 'USER'}
                          </span>
                        </td>
                        <td style={{ padding: '12px 0', textAlign: 'right' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px' }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: (u.is_active || u.is_active===undefined) ? '#2DD4BF' : '#6B6357' }} />
                            <span style={{ ...MONO, fontSize: '10px', color: '#A89F8C' }}>{(u.is_active || u.is_active===undefined) ? 'ACTIVE' : 'INACTIVE'}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
