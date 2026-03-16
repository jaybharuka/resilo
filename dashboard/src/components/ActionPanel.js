import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { actionsApi, jobsApi } from '../services/api';
import { toast } from 'react-hot-toast';

// Utility to safely stringify results for display
function formatPayload(obj) {
  try {
    if (!obj) return 'No response';
    return JSON.stringify(obj, null, 2).slice(0, 2000); // cap length
  } catch (e) {
    return String(obj);
  }
}

/**
 * ActionPanel
 * Provides real system & AI action buttons backed by Flask / Node proxy endpoints.
 * Shows granular feedback + last result payload for transparency.
 */
export default function ActionPanel() {
  const { role } = useAuth();
  const [loading, setLoading] = useState({});
  const [lastAction, setLastAction] = useState(null);
  const [result, setResult] = useState(null);
  const [showJSON, setShowJSON] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [options, setOptions] = useState({
    aggressive: false,
    browserCache: false,
    trimWorkingSets: false,
    dryRun: true,
  });
  const [history, setHistory] = useState([]); // keep last N action results

  const run = async (key, fn, friendlyName, meta = {}) => {
    setLoading(l => ({ ...l, [key]: true }));
    const t = toast.loading(`${friendlyName}...`);
    try {
      const res = await fn();
      setLastAction({ key, friendlyName, at: new Date().toISOString() });
      setResult(res);
      setHistory(h => [{ id: Date.now(), key, friendlyName, at: new Date().toISOString(), response: res, meta }, ...h].slice(0, 25));
      const msg = res?.message || res?.status || 'Done';
      // Special-case forbidden (403) style hint message
      if (res?.status === 'forbidden') {
        toast.error(res?.message || 'Action not permitted', { id: t });
      } else {
        toast.success(msg, { id: t });
      }
      // If a job was started, poll its status and logs until completion
      if (res?.job_id) {
        await pollJob(res.job_id, setResult);
      }
    } catch (e) {
      console.error(`${friendlyName} failed:`, e);
      toast.error(`${friendlyName} failed`, { id: t });
    } finally {
      setLoading(l => ({ ...l, [key]: false }));
    }
  };

  const pollJob = async (jobId, onUpdate) => {
    let done = false;
    let attempts = 0;
    while (!done && attempts < 120) { // up to ~2 minutes
      await new Promise(r => setTimeout(r, 1000));
      attempts++;
      try {
        const status = await jobsApi.get(jobId);
        const logs = await jobsApi.logs(jobId);
        const combined = { ...(status || {}), ...(logs || {}) };
        onUpdate && onUpdate(combined);
        if (status?.status === 'succeeded' || status?.status === 'failed') {
          done = true;
          break;
        }
      } catch (e) {
        break;
      }
    }
  };

  const confirmAndRun = (key, fn, friendlyName, confirmText) => {
    if (!window.confirm(confirmText)) return;
    run(key, fn, friendlyName);
  };

  const actions = [
    { key: 'memory', label: options.dryRun ? 'Memory Preview' : 'Memory Cleanup', color: options.dryRun ? 'gray' : 'blue', adminOnly: true, onClick: () => {
        const opts = { 
          aggressive: options.aggressive,
          includeBrowserCache: options.browserCache,
          trimWorkingSets: options.trimWorkingSets,
          dryRun: options.dryRun
        };
        run('memory', () => actionsApi.memoryCleanup(opts), options.dryRun ? 'Memory Cleanup (Preview)' : 'Memory Cleanup', opts);
      } },
    { key: 'disk', label: options.dryRun ? 'Disk Preview' : 'Disk Cleanup', color: options.dryRun ? 'gray' : 'amber', adminOnly: true, onClick: () => {
        const opts = { dryRun: options.dryRun };
        run('disk', () => actionsApi.diskCleanup(opts), options.dryRun ? 'Disk Cleanup (Preview)' : 'Disk Cleanup', opts);
      } },
    { key: 'process', label: 'Process Snapshot', color: 'indigo', adminOnly: false, onClick: () => run('process', actionsApi.processMonitor, 'Process Monitor') },
    { key: 'emergency', label: 'Emergency Stop (Top CPU)', color: 'rose', adminOnly: true, onClick: () => confirmAndRun('emergency', () => actionsApi.emergencyStop(), 'Emergency Stop', 'This will terminate a top CPU process (if allowed). Continue?') },
  ];

  const aiActions = [
    { key: 'diag', label: 'AI Diagnostics', color: 'green', adminOnly: false, onClick: () => run('diag', actionsApi.runDiagnostics, 'AI Diagnostics') },
    { key: 'retrain', label: 'Retrain Models', color: 'purple', adminOnly: true, onClick: () => run('retrain', actionsApi.retrainModels, 'Retrain Models') },
    { key: 'export', label: 'Export Insights', color: 'cyan', adminOnly: true, onClick: () => run('export', actionsApi.exportInsights, 'Export Insights') },
    { key: 'updateParams', label: 'Update Parameters', color: 'orange', adminOnly: true, onClick: () => {
        const sample = '{"learning_rate": 0.001}';
        const input = window.prompt('Enter JSON parameters to update', sample);
        if (input === null) return; // cancelled
        let payload;
        try {
          payload = JSON.parse(input || '{}');
        } catch (e) {
          toast.error('Invalid JSON');
          return;
        }
        run('updateParams', () => actionsApi.updateParameters(payload), 'Update Parameters');
      } },
  ];

  const pillClasses = (color) => `w-full px-4 py-2 rounded-md border text-sm font-medium shadow-sm disabled:opacity-60 disabled:cursor-not-allowed transition-colors
    border-${color}-300 text-${color}-700 bg-white hover:bg-${color}-50 focus:outline-none focus:ring-2 focus:ring-${color}-400/40`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-semibold text-gray-900">System & AI Actions</h3>
        {lastAction && (
          <button
            onClick={() => setShowJSON(s => !s)}
            className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-600"
          >
            {showJSON ? 'Hide Result' : 'Show Result'}
          </button>
        )}
      </div>
      <p className="text-xs text-gray-500 mb-4">Actions call live backend endpoints. System actions require backend started with ALLOW_SYSTEM_ACTIONS.</p>

      {/* Advanced options toggle */}
      <div className="mb-4">
        <button
          type="button"
          onClick={() => setAdvancedOpen(o => !o)}
          className="text-xs font-medium text-blue-700 hover:underline"
        >
          {advancedOpen ? 'Hide Advanced Options' : 'Show Advanced Options'}
        </button>
      </div>
      {advancedOpen && (
        <div className="mb-6 border rounded-lg p-4 bg-gray-50">
          <h4 className="text-sm font-semibold mb-3 text-gray-700">Memory & Disk Cleanup Options</h4>
          <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-3 mb-3 text-xs">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" className="accent-blue-600" checked={options.dryRun} onChange={e => setOptions(o => ({ ...o, dryRun: e.target.checked }))} />
              <span>Dry Run (Preview)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" className="accent-blue-600" checked={options.aggressive} onChange={e => setOptions(o => ({ ...o, aggressive: e.target.checked }))} />
              <span>Aggressive Mode</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" className="accent-blue-600" checked={options.browserCache} disabled={!options.aggressive} onChange={e => setOptions(o => ({ ...o, browserCache: e.target.checked }))} />
              <span>Include Browser Cache</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" className="accent-blue-600" checked={options.trimWorkingSets} disabled={!options.aggressive} onChange={e => setOptions(o => ({ ...o, trimWorkingSets: e.target.checked }))} />
              <span>Trim Working Sets (Win)</span>
            </label>
          </div>
          <p className="text-[10px] text-gray-500 leading-snug">
            Dry Run previews what could be cleaned without deleting. Aggressive mode adds system & browser temp paths (permission dependent).
            Working set trim attempts to reduce RAM of large non-critical processes (Windows only). Disable Dry Run to perform real cleanup.
          </p>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-3 mb-6">
        {actions.map(a => {
          const isAdmin = role === 'admin';
          const showBadge = a.adminOnly;
          return (
            <div key={a.key} className="relative">
              <button
                onClick={a.onClick}
                disabled={!!loading[a.key] || (a.adminOnly && !isAdmin)}
                className={pillClasses(a.color)}
                title={a.adminOnly ? (isAdmin ? 'Admin-only action' : 'Only admins can perform this action') : undefined}
              >
                {loading[a.key] ? 'Working…' : a.label}
              </button>
              {showBadge && (
                <span className={`absolute top-1 right-2 text-[10px] px-2 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-300 font-semibold ${isAdmin ? '' : 'opacity-60'}`}
                  title={isAdmin ? 'Admin-only action' : 'Only admins can perform this action'}>
                  Admin
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div className="grid sm:grid-cols-3 gap-3 mb-4">
        {aiActions.map(a => {
          const isAdmin = role === 'admin';
          const showBadge = a.adminOnly;
          return (
            <div key={a.key} className="relative">
              <button
                onClick={a.onClick}
                disabled={!!loading[a.key] || (a.adminOnly && !isAdmin)}
                className={pillClasses(a.color)}
                title={a.adminOnly ? (isAdmin ? 'Admin-only action' : 'Only admins can perform this action') : undefined}
              >
                {loading[a.key] ? 'Running…' : a.label}
              </button>
              {showBadge && (
                <span className={`absolute top-1 right-2 text-[10px] px-2 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-300 font-semibold ${isAdmin ? '' : 'opacity-60'}`}
                  title={isAdmin ? 'Admin-only action' : 'Only admins can perform this action'}>
                  Admin
                </span>
              )}
            </div>
          );
        })}
      </div>

      {lastAction && showJSON && (
        <div className="mt-4 border rounded-lg bg-gray-50 p-3 text-xs font-mono overflow-auto max-h-80">
          <div className="mb-2 text-gray-600 flex items-center justify-between">
            <span>Last: {lastAction.friendlyName} @ {new Date(lastAction.at).toLocaleTimeString()}</span>
            {result?.status === 'forbidden' && (
              <span className="text-amber-600 font-semibold">(Enable ALLOW_SYSTEM_ACTIONS to activate)</span>
            )}
          </div>
          <pre className="whitespace-pre-wrap break-all">{formatPayload(result)}</pre>
          {result?.artifact && (
            <div className="mt-3">
              <a
                className="text-blue-700 hover:underline"
                href={jobsApi.downloadUrl(result.id || result.job_id)}
                target="_blank"
                rel="noreferrer"
              >
                Download Export
              </a>
            </div>
          )}
          {history.length > 1 && (
            <div className="mt-4">
              <h5 className="font-semibold text-gray-700 mb-2">Recent History</h5>
              <ul className="space-y-1 max-h-40 overflow-auto pr-1">
                {history.slice(0,10).map(h => (
                  <li key={h.id} className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      className="text-left flex-1 truncate text-blue-700 hover:underline"
                      onClick={() => { setResult(h.response); setLastAction({ key: h.key, friendlyName: h.friendlyName, at: h.at }); }}
                      title="Show this result"
                    >
                      {h.friendlyName} • {new Date(h.at).toLocaleTimeString()} • {h.response?.status}
                    </button>
                    <span className="text-[10px] text-gray-500">{h.meta?.dryRun ? 'preview' : 'live'}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
