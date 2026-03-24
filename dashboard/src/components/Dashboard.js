import React, { useState, useEffect } from 'react';
import { apiService, systemApi, realTimeService } from '../services/api';
import { metricStatus } from '../utils/thresholds';
import { useResiloStore } from '../store/useResiloStore';
import ActionPanel from './ActionPanel';
import MetricCard from './resilo/MetricCard';
import InfoTip from './InfoTip';
import AlertsTable from './resilo/AlertsTable';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, Clock, Cpu, Server, Zap } from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };
const UI      = { fontFamily: "'Outfit', sans-serif" };

const PANEL = {
  background: 'rgb(22, 20, 16)',
  border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: '12px',
  boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
};

export default function Dashboard() {
  const { alerts, startPolling } = useResiloStore();

  const [systemData, setSystemData] = useState({
    cpu: 0, memory: 0, disk: 0, network_in: 0, network_out: 0, status: 'unknown', temperature: null,
  });
  const [systemInfo, setSystemInfo] = useState({ uptime: 'N/A', load_avg: 'N/A', platform: 'N/A', cpu_cores: 'N/A' });
  const [metricsHistory, setMetricsHistory] = useState([]);

  useEffect(() => {
    let mounted = true;
    let pollInterval = null;
    let infoInterval = null;

    const stopResiloPolling = startPolling();

    const normalizeAndSet = (data) => {
      if (!mounted) return;
      const cpu = data.cpu ?? 0;
      const mem = data.memory ?? 0;
      const disk = data.disk ?? data.storage ?? 0;

      setSystemData({
        cpu, memory: mem, disk,
        network_in:  data.network_in  ?? data.network?.received ?? 0,
        network_out: data.network_out ?? data.network?.sent ?? 0,
        status: data.status || 'unknown',
        temperature: data.temperature ?? null,
      });

      setMetricsHistory(prev => {
        const now = new Date();
        const h = now.getHours().toString().padStart(2, '0');
        const m = now.getMinutes().toString().padStart(2, '0');
        const s = now.getSeconds().toString().padStart(2, '0');
        const newEntry = { time: `${h}:${m}:${s}`, cpu, memory: mem };
        const updated = [...prev, newEntry];
        return updated.length > 20 ? updated.slice(updated.length - 20) : updated;
      });
    };

    const unsub = realTimeService.subscribe('system', normalizeAndSet);

    const fetchOnce = async () => {
      try { const data = await apiService.getSystemData(); normalizeAndSet(data); } catch {}
    };
    const fetchInfo = async () => {
      try { const info = await systemApi.getSystemInfo(); if (info && mounted) setSystemInfo(info); } catch {}
    };

    const ensureData = async () => {
      await Promise.all([fetchOnce(), fetchInfo()]);
      pollInterval = setInterval(fetchOnce, 4000);
      infoInterval = setInterval(fetchInfo, 5000);
    };

    const timer = setTimeout(ensureData, 100);

    return () => {
      mounted = false;
      stopResiloPolling();
      clearTimeout(timer);
      if (pollInterval) clearInterval(pollInterval);
      if (infoInterval) clearInterval(infoInterval);
      unsub && unsub();
    };
  }, [startPolling]);

  const displayMetrics = metricsHistory.length > 2 ? metricsHistory : [{ time: '...', cpu: 0, memory: 0 }];

  const overallStatus = systemData.status === 'healthy' ? 'healthy'
    : systemData.status === 'warning' ? 'warning'
    : systemData.status === 'unknown' ? 'warning'
    : 'critical';

  const statusColor = { healthy: '#2DD4BF', warning: '#F59E0B', critical: '#F87171' }[overallStatus] || '#6B6357';

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', color: '#F5F0E8', margin: 0, lineHeight: 1 }}>
            System Overview
          </h1>
          <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: '#4A443D', marginTop: '6px' }}>
            RESILO OPERATIONS DASHBOARD
          </p>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '7px 14px',
            borderRadius: '20px',
            background: 'rgba(22,20,16,0.8)',
            border: '1px solid rgba(42,40,32,0.9)',
            ...MONO,
            fontSize: '11px',
            letterSpacing: '0.1em',
            color: '#2DD4BF',
          }}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: '#2DD4BF',
              boxShadow: '0 0 8px rgba(45,212,191,0.6)',
              animation: 'pulse 2s infinite',
              display: 'inline-block',
            }}
          />
          LIVE
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        <MetricCard
          title="CPU Usage"
          value={systemData.cpu}
          unit="%"
          status={metricStatus('cpu', systemData.cpu)}
          trend={0}
          info="Percentage of CPU time spent on non-idle processes, sampled via psutil. Thresholds are configurable in Settings — warn and critical levels trigger alerts and auto-remediation rules."
        />
        <MetricCard
          title="Memory Usage"
          value={systemData.memory}
          unit="%"
          status={metricStatus('mem', systemData.memory)}
          trend={0}
          info="RAM utilisation as a percentage of total installed memory. Includes all user-space processes. High values may indicate memory leaks or insufficient capacity."
        />
        <MetricCard
          title="Disk Usage"
          value={systemData.disk}
          unit="%"
          status={metricStatus('disk', systemData.disk)}
          trend={0}
          info="Percentage of disk space used on the primary partition. Approaching 100% can cause write failures and service crashes. Log rotation and cleanup rules fire automatically."
        />
        <MetricCard
          title="Network In"
          value={(systemData.network_in / 1024 / 1024).toFixed(1)}
          unit="MB/s"
          status="healthy"
          trend={0}
          info="Inbound network throughput in megabytes per second, summed across all interfaces. Spikes may indicate backup jobs, deployments, or unexpected traffic."
        />
      </div>

      {/* Charts + Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Time-series chart */}
        <div className="col-span-2" style={PANEL}>
          <div style={{ padding: '20px 22px', borderBottom: '1px solid rgba(42,40,32,0.9)', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Activity size={16} color="#F59E0B" />
            <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>
              SYSTEM PERFORMANCE
            </span>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '16px' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '5px', ...UI, fontSize: '12px', color: '#6B6357' }}>
                <span style={{ width: '24px', height: '2px', background: '#F59E0B', display: 'inline-block', borderRadius: '1px' }} />
                CPU
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '5px', ...UI, fontSize: '12px', color: '#6B6357' }}>
                <span style={{ width: '24px', height: '2px', background: '#2DD4BF', display: 'inline-block', borderRadius: '1px' }} />
                Memory
              </span>
            </div>
          </div>
          <div style={{ padding: '20px 22px', height: '280px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={displayMetrics}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(42,40,32,0.8)" vertical={false} />
                <XAxis
                  dataKey="time"
                  stroke="#3A342D"
                  tick={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", fill: '#4A443D' }}
                />
                <YAxis
                  stroke="#3A342D"
                  tick={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", fill: '#4A443D' }}
                  domain={[0, 100]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgb(31,29,24)',
                    borderColor: 'rgba(42,40,32,0.9)',
                    borderRadius: '8px',
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: '11px',
                  }}
                  labelStyle={{ color: '#A89F8C' }}
                  itemStyle={{ color: '#F5F0E8' }}
                />
                <Line type="monotone" dataKey="cpu"    stroke="#F59E0B" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="memory" stroke="#2DD4BF" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Action panel */}
        <div className="col-span-1" style={{ ...PANEL, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '20px 22px', borderBottom: '1px solid rgba(42,40,32,0.9)', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Zap size={16} color="#F59E0B" />
            <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>
              SYSTEM ACTIONS
            </span>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
            <ActionPanel />
          </div>
        </div>

      </div>

      {/* Alerts + System Health */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Active alerts */}
        <div style={{ ...PANEL, overflow: 'hidden' }}>
          <div style={{ padding: '18px 22px', borderBottom: '1px solid rgba(42,40,32,0.9)', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: '#F87171',
                boxShadow: '0 0 8px rgba(248,113,113,0.5)',
                display: 'inline-block',
              }}
            />
            <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>
              ACTIVE ALERTS & INCIDENTS
            </span>
            {alerts?.length > 0 && (
              <span
                style={{
                  marginLeft: 'auto',
                  ...MONO,
                  fontSize: '10px',
                  letterSpacing: '0.08em',
                  color: '#F87171',
                  background: 'rgba(248,113,113,0.1)',
                  border: '1px solid rgba(248,113,113,0.2)',
                  borderRadius: '10px',
                  padding: '2px 8px',
                }}
              >
                {alerts.length}
              </span>
            )}
          </div>
          <AlertsTable alerts={alerts || []} />
        </div>

        {/* System health */}
        <div style={{ ...PANEL, padding: '22px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
            <Server size={16} color="#F59E0B" />
            <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>
              SYSTEM HEALTH
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

            {/* Overall status */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ ...UI, fontSize: '13px', color: '#A89F8C' }}>Overall Status</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    width: '7px',
                    height: '7px',
                    borderRadius: '50%',
                    background: statusColor,
                    boxShadow: `0 0 8px ${statusColor}80`,
                    display: 'inline-block',
                    animation: 'pulse 2s infinite',
                  }}
                />
                <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.08em', color: statusColor, textTransform: 'uppercase' }}>
                  {systemData.status || 'unknown'}
                </span>
              </div>
            </div>

            {/* Uptime */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ ...UI, fontSize: '13px', color: '#A89F8C', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Clock size={13} color="#6B6357" /> Uptime
                <InfoTip size={13} info="Time elapsed since the system last booted. Resets on restart or crash. Long uptimes indicate stability; short uptimes may signal recent unexpected reboots." />
              </span>
              <span style={{ ...MONO, fontSize: '12px', color: '#F59E0B', letterSpacing: '0.04em' }}>
                {systemData.uptime || systemInfo.boot_time || 'N/A'}
              </span>
            </div>

            {/* Load avg */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ ...UI, fontSize: '13px', color: '#A89F8C', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Cpu size={13} color="#6B6357" /> Load Average
                <InfoTip size={13} info="1-minute CPU load average — the average number of processes waiting for CPU time. Values above the core count indicate CPU contention." />
              </span>
              <span style={{ ...MONO, fontSize: '12px', color: '#A89F8C', letterSpacing: '0.04em' }}>
                {systemInfo.load_avg || 'N/A'}
              </span>
            </div>

            {/* Divider */}
            <div style={{ borderTop: '1px solid rgba(42,40,32,0.9)', paddingTop: '16px', marginTop: '4px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.12em', color: '#4A443D', marginBottom: '6px' }}>PLATFORM</div>
                <div style={{ ...UI, fontSize: '14px', fontWeight: 600, color: '#F5F0E8' }}>
                  {systemInfo.platform || 'N/A'}
                </div>
              </div>
              <div>
                <div style={{ ...MONO, fontSize: '10px', letterSpacing: '0.12em', color: '#4A443D', marginBottom: '6px' }}>CPU CORES</div>
                <div style={{ ...DISPLAY, fontSize: '2rem', letterSpacing: '0.04em', color: '#F5F0E8', lineHeight: 1 }}>
                  {systemInfo.cpu_cores || 'N/A'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
