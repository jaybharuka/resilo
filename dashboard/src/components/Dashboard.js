import React, { useState, useEffect } from 'react';
import { apiService, systemApi } from '../services/api';
import { realTimeService } from '../services/api';
import ActionPanel from './ActionPanel';
// Socket-based realtime is optional; we use polling-based realTimeService for reliability
import { toast } from 'react-hot-toast';
import { Cpu, Brain, HardDrive, ArrowDownToLine } from 'lucide-react';

const Dashboard = () => {
  const [systemData, setSystemData] = useState({
    cpu: 0,
    memory: 0,
    disk: 0,
    network_in: 0,
    network_out: 0,
    status: 'unknown',
    temperature: null,
  });
  const [systemInfo, setSystemInfo] = useState({ uptime: 'N/A', load_avg: 'N/A' });
  const [actionLoading, setActionLoading] = useState({ restart: false, diag: false, export: false });

  useEffect(() => {
    let mounted = true;
    let pollInterval = null;
    let infoInterval = null;

    const normalizeAndSet = (data) => {
      if (!mounted) return;
      setSystemData({
        cpu: data.cpu ?? 0,
        memory: data.memory ?? 0,
        disk: data.disk ?? data.storage ?? 0,
        network_in: data.network_in ?? data.network?.received ?? 0,
        network_out: data.network_out ?? data.network?.sent ?? 0,
        status: data.status || 'unknown',
        temperature: data.temperature ?? null,
      });
    };

    // Realtime subscription
  const unsub = realTimeService.subscribe('system', normalizeAndSet);

    // Fallback polling if socket not connected within 1s
    const fetchOnce = async () => {
      try {
        const data = await apiService.getSystemData();
        normalizeAndSet(data);
      } catch {}
    };
    const fetchInfo = async () => {
      try {
        const info = await systemApi.getSystemInfo();
        if (info) setSystemInfo(info);
      } catch {}
    };

    const ensurePolling = async () => {
      // Always do an initial fetch to avoid empty UI on first load
      await Promise.all([fetchOnce(), fetchInfo()]);
      // If sockets are not connected, keep frequent polling
      // Polling service already runs; still do a lightweight interval to force faster UI ticks
      pollInterval = setInterval(fetchOnce, 4000);
      // Refresh system info less frequently
      infoInterval = setInterval(fetchInfo, 5000);
    };
    const timer = setTimeout(ensurePolling, 1000);

    return () => {
      mounted = false;
      clearTimeout(timer);
      if (pollInterval) clearInterval(pollInterval);
      if (infoInterval) clearInterval(infoInterval);
      unsub && unsub();
    };
  }, []);

  const MetricCard = ({ title, value, unit, color, icon }) => (
    <div className="bg-white border border-gray-200 rounded-xl p-6 transition-shadow duration-200 hover:shadow-md">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-gray-700 text-sm font-medium">{title}</h3>
        <span className="flex items-center">{icon}</span>
      </div>
      <div className="flex items-end space-x-2">
        <span className={`text-3xl font-bold ${color}`}>{value == null ? 'N/A' : value}</span>
        {value != null && <span className="text-gray-500 text-sm mb-1">{unit}</span>}
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2 mt-3">
        {value != null && (
          <div
            className={`h-2 rounded-full transition-all duration-500 ${color.replace('text', 'bg')}`}
            style={{ width: `${Math.min(value, 100)}%` }}
          ></div>
        )}
      </div>
    </div>
  );

  return (
    <div className="p-6">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">System Dashboard</h2>
        <p className="text-gray-600">Real-time system performance monitoring</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard
          title="CPU Usage"
          value={systemData.cpu}
          unit="%"
          color="text-blue-400"
          icon={<Cpu size={22} className="text-blue-400" />}
        />
        <MetricCard
          title="Memory Usage"
          value={systemData.memory}
          unit="%"
          color="text-green-400"
          icon={<Brain size={22} className="text-green-400" />}
        />
        <MetricCard
          title="Disk Usage"
          value={systemData.disk}
          unit="%"
          color="text-yellow-400"
          icon={<HardDrive size={22} className="text-yellow-400" />}
        />
        <MetricCard
          title="Network In"
          value={Math.round((systemData.network_in || 0) / 1024 / 1024)}
          unit="MB/s"
          color="text-purple-400"
          icon={<ArrowDownToLine size={22} className="text-purple-400" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4">System Health</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Overall Status</span>
              <div className="flex items-center space-x-2">
                <div className={`w-3 h-3 rounded-full animate-pulse ${
                  systemData.status === 'healthy' ? 'bg-green-400' : systemData.status === 'warning' ? 'bg-yellow-400' : 'bg-red-400'
                }`}></div>
                <span className={`font-medium capitalize ${
                  systemData.status === 'healthy' ? 'text-green-600' : systemData.status === 'warning' ? 'text-yellow-600' : 'text-red-600'
                }`}>
                  {systemData.status || 'unknown'}
                </span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Uptime</span>
              <span className="text-blue-600 font-medium">{systemInfo.boot_time ? new Date(systemInfo.boot_time).toLocaleString() : 'N/A'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Load Average</span>
              <span className="text-yellow-600 font-medium">{systemInfo.load_avg || 'N/A'}</span>
            </div>
          </div>
        </div>

        <ActionPanel />
      </div>
    </div>
  );
};

export default Dashboard;