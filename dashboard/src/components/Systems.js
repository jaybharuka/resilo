import React, { useState, useEffect } from 'react';
import { systemApi, actionsApi, realTimeService } from '../services/api';
import { toast } from 'react-hot-toast';
import { Monitor, BarChart3, Wrench, Zap } from 'lucide-react';

const Systems = () => {
  const [processes, setProcesses] = useState([]);
  const [systemInfo, setSystemInfo] = useState({});
  const [actionLoading, setActionLoading] = useState({
    memory: false,
    disk: false,
    monitor: false,
    emergency: false,
  });

  useEffect(() => {
    const onProcesses = (list) => {
      setProcesses((list || []).slice(0, 10));
    };

  const unsub = realTimeService.subscribe('processes', onProcesses);

    const fetchAll = async () => {
      try {
        const [procs, info] = await Promise.all([
          systemApi.getProcesses(),
          systemApi.getSystemInfo(),
        ]);
        onProcesses(procs);
        setSystemInfo(info || {});
      } catch (e) {
        // silent
      }
    };

    fetchAll();

    return () => {
      unsub && unsub();
    };
  }, []);

  return (
    <div className="p-6">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">System Information</h2>
        <p className="text-gray-600">Detailed system and process monitoring</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Monitor size={18} className="mr-2 text-blue-600" />
            System Info
          </h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-700">Platform</span>
              <span className="text-blue-700">{systemInfo.platform || 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-700">CPU Cores</span>
              <span className="text-green-700">{systemInfo.cpu_cores || 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-700">Total Memory</span>
              <span className="text-purple-700">{systemInfo.total_memory || 'N/A'} GB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-700">Boot Time</span>
              <span className="text-yellow-700">{systemInfo.boot_time || 'N/A'}</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <BarChart3 size={18} className="mr-2 text-green-600" />
            Performance
          </h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-700">CPU Frequency</span>
              <span className="text-blue-700">{systemInfo.cpu_freq || 'N/A'} MHz</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-700">Available Memory</span>
              <span className="text-green-700">{systemInfo.available_memory || 'N/A'} GB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-700">Free Disk</span>
              <span className="text-purple-700">{systemInfo.free_disk || 'N/A'} GB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-700">Load Average</span>
              <span className="text-yellow-700">{systemInfo.load_avg || 'N/A'}</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Wrench size={18} className="mr-2 text-yellow-600" />
            Actions
          </h3>
          <div className="space-y-3">
            <button
              onClick={async () => {
                setActionLoading((s) => ({ ...s, memory: true }));
                const t = toast.loading('Running memory cleanup...');
                try {
                  const res = await actionsApi.memoryCleanup();
                  toast.success(res?.message || 'Memory cleanup triggered', { id: t });
                } catch (e) {
                  toast.error('Failed to run memory cleanup', { id: t });
                } finally {
                  setActionLoading((s) => ({ ...s, memory: false }));
                }
              }}
              disabled={actionLoading.memory}
              className="w-full bg-white text-blue-700 border border-blue-200 hover:bg-blue-50 disabled:opacity-60 px-4 py-2 rounded-md transition-colors duration-150"
            >
              {actionLoading.memory ? 'Cleaning memory…' : 'Memory Cleanup'}
            </button>
            <button
              onClick={async () => {
                setActionLoading((s) => ({ ...s, disk: true }));
                const t = toast.loading('Running disk cleanup...');
                try {
                  const res = await actionsApi.diskCleanup();
                  toast.success(res?.message || 'Disk cleanup triggered', { id: t });
                } catch (e) {
                  toast.error('Failed to run disk cleanup', { id: t });
                } finally {
                  setActionLoading((s) => ({ ...s, disk: false }));
                }
              }}
              disabled={actionLoading.disk}
              className="w-full bg-white text-green-700 border border-green-200 hover:bg-green-50 disabled:opacity-60 px-4 py-2 rounded-md transition-colors duration-150"
            >
              {actionLoading.disk ? 'Cleaning disk…' : 'Disk Cleanup'}
            </button>
            <button
              onClick={async () => {
                setActionLoading((s) => ({ ...s, monitor: true }));
                const t = toast.loading('Starting process monitor...');
                try {
                  const res = await actionsApi.processMonitor();
                  toast.success(res?.message || 'Process monitor started', { id: t });
                } catch (e) {
                  toast.error('Failed to start process monitor', { id: t });
                } finally {
                  setActionLoading((s) => ({ ...s, monitor: false }));
                }
              }}
              disabled={actionLoading.monitor}
              className="w-full bg-white text-yellow-700 border border-yellow-200 hover:bg-yellow-50 disabled:opacity-60 px-4 py-2 rounded-md transition-colors duration-150"
            >
              {actionLoading.monitor ? 'Starting…' : 'Process Monitor'}
            </button>
            <button
              onClick={async () => {
                setActionLoading((s) => ({ ...s, emergency: true }));
                const t = toast.loading('Sending emergency stop...');
                try {
                  const res = await actionsApi.emergencyStop();
                  toast.success(res?.message || 'Emergency stop signal sent', { id: t });
                } catch (e) {
                  toast.error('Failed to send emergency stop', { id: t });
                } finally {
                  setActionLoading((s) => ({ ...s, emergency: false }));
                }
              }}
              disabled={actionLoading.emergency}
              className="w-full bg-white text-red-700 border border-red-200 hover:bg-red-50 disabled:opacity-60 px-4 py-2 rounded-md transition-colors duration-150"
            >
              {actionLoading.emergency ? 'Stopping…' : 'Emergency Stop'}
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
          <Zap size={18} className="mr-2 text-purple-600" />
          Top Processes
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left text-gray-700 py-3 px-4">PID</th>
                <th className="text-left text-gray-700 py-3 px-4">Name</th>
                <th className="text-left text-gray-700 py-3 px-4">CPU %</th>
                <th className="text-left text-gray-700 py-3 px-4">Memory %</th>
                <th className="text-left text-gray-700 py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody>
              {processes.map((process, index) => (
                <tr key={index} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-3 px-4 text-blue-700 font-mono">{process.pid}</td>
                  <td className="py-3 px-4 text-gray-900">{process.name}</td>
                  <td className="py-3 px-4 text-green-700">{process.cpu_percent?.toFixed(1) || '0.0'}%</td>
                  <td className="py-3 px-4 text-purple-700">{process.memory_percent?.toFixed(1) || '0.0'}%</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-1 rounded-full text-xs ${
                      process.status === 'running' 
                        ? 'bg-green-50 text-green-700 border border-green-200' 
                        : 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                    }`}>
                      {process.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Systems;