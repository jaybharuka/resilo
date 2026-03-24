import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { actionsApi, jobsApi } from '../services/api';
import { toast } from 'react-hot-toast';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

function formatPayload(obj) {
  try {
    if (!obj) return 'No response';
    return JSON.stringify(obj, null, 2).slice(0, 2000);
  } catch (e) {
    return String(obj);
  }
}

export default function ActionPanel() {
  const { role } = useAuth();
  const [loading, setLoading]       = useState({});
  const [lastAction, setLastAction] = useState(null);
  const [result, setResult]         = useState(null);
  const [showResult, setShowResult] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [options, setOptions] = useState({
    aggressive: false,
    browserCache: false,
    trimWorkingSets: false,
    dryRun: true,
  });
  const [history, setHistory] = useState([]);

  const run = async (key, fn, friendlyName, meta = {}) => {
    setLoading(l => ({ ...l, [key]: true }));
    const t = toast.loading(`${friendlyName}…`);
    try {
      const res = await fn();
      setLastAction({ key, friendlyName, at: new Date().toISOString() });
      setResult(res);
      setShowResult(true);
      setHistory(h => [{ id: Date.now(), key, friendlyName, at: new Date().toISOString(), response: res, meta }, ...h].slice(0, 25));
      const msg = res?.message || res?.status || 'Done';
      if (res?.status === 'forbidden') {
        toast.error(res?.message || 'Action not permitted', { id: t });
      } else {
        toast.success(msg, { id: t });
      }
      if (res?.job_id) await pollJob(res.job_id, setResult);
    } catch (e) {
      console.error(`${friendlyName} failed:`, e);
      toast.error(`${friendlyName} failed`, { id: t });
    } finally {
      setLoading(l => ({ ...l, [key]: false }));
    }
  };

  const pollJob = async (jobId, onUpdate) => {
    let attempts = 0;
    while (attempts < 120) {
      await new Promise(r => setTimeout(r, 1000));
      attempts++;
      try {
        const status = await jobsApi.get(jobId);
        const logs   = await jobsApi.logs(jobId);
        onUpdate?.({ ...(status || {}), ...(logs || {}) });
        if (status?.status === 'succeeded' || status?.status === 'failed') break;
      } catch { break; }
    }
  };

  const confirmAndRun = (key, fn, friendlyName, confirmText) => {
    if (!window.confirm(confirmText)) return;
    run(key, fn, friendlyName);
  };

  const isAdmin = role === 'admin';

  const systemActions = [
    {
      key: 'memory', danger: false, adminOnly: true,
      label: options.dryRun ? 'Memory Preview' : 'Memory Cleanup',
      onClick: () => {
        const opts = { aggressive: options.aggressive, includeBrowserCache: options.browserCache, trimWorkingSets: options.trimWorkingSets, dryRun: options.dryRun };
        run('memory', () => actionsApi.memoryCleanup(opts), options.dryRun ? 'Memory Cleanup (Preview)' : 'Memory Cleanup', opts);
      },
    },
    {
      key: 'disk', danger: false, adminOnly: true,
      label: options.dryRun ? 'Disk Preview' : 'Disk Cleanup',
      onClick: () => run('disk', () => actionsApi.diskCleanup({ dryRun: options.dryRun }), options.dryRun ? 'Disk Cleanup (Preview)' : 'Disk Cleanup'),
    },
    {
      key: 'process', danger: false, adminOnly: false,
      label: 'Process Snapshot',
      onClick: () => run('process', actionsApi.processMonitor, 'Process Monitor'),
    },
    {
      key: 'emergency', danger: true, adminOnly: true,
      label: 'Emergency Stop',
      onClick: () => confirmAndRun('emergency', () => actionsApi.emergencyStop(), 'Emergency Stop', 'This will terminate a top CPU process (if allowed). Continue?'),
    },
  ];

  const aiActions = [
    { key: 'diag',         danger: false, adminOnly: false, label: 'AI Diagnostics',    onClick: () => run('diag',    actionsApi.runDiagnostics,  'AI Diagnostics') },
    { key: 'retrain',      danger: false, adminOnly: true,  label: 'Retrain Models',    onClick: () => run('retrain', actionsApi.retrainModels,   'Retrain Models') },
    { key: 'export',       danger: false, adminOnly: true,  label: 'Export Insights',   onClick: () => run('export',  actionsApi.exportInsights,  'Export Insights') },
    {
      key: 'updateParams', danger: false, adminOnly: true, label: 'Update Parameters',
      onClick: () => {
        const input = window.prompt('Enter JSON parameters to update', '{"learning_rate": 0.001}');
        if (input === null) return;
        let payload;
        try { payload = JSON.parse(input || '{}'); } catch { toast.error('Invalid JSON'); return; }
        run('updateParams', () => actionsApi.updateParameters(payload), 'Update Parameters');
      },
    },
  ];

  const ActionRow = ({ action, isLast }) => {
    const busy     = !!loading[action.key];
    const locked   = action.adminOnly && !isAdmin;
    const disabled = busy || locked;

    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '9px 0',
          borderBottom: isLast ? 'none' : '1px solid rgba(42,40,32,0.6)',
          opacity: locked ? 0.35 : 1,
        }}
      >
        {/* Label */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              width: '5px',
              height: '5px',
              borderRadius: '50%',
              flexShrink: 0,
              background: action.danger ? '#F87171'
                : locked ? '#4A443D'
                : '#F59E0B',
              boxShadow: action.danger ? '0 0 6px rgba(248,113,113,0.4)'
                : locked ? 'none'
                : '0 0 6px rgba(245,158,11,0.35)',
            }}
          />
          <span style={{ ...UI, fontSize: '13px', color: action.danger ? '#F87171' : '#A89F8C' }}>
            {action.label}
          </span>
          {action.adminOnly && (
            <span style={{ ...MONO, fontSize: '9px', letterSpacing: '0.1em', color: '#F59E0B', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.18)', borderRadius: '4px', padding: '1px 5px' }}>
              ADMIN
            </span>
          )}
        </div>

        {/* Run button */}
        <button
          onClick={action.onClick}
          disabled={disabled}
          style={{
            ...MONO,
            fontSize: '10px',
            letterSpacing: '0.1em',
            padding: '4px 10px',
            borderRadius: '5px',
            background: 'transparent',
            border: action.danger
              ? '1px solid rgba(248,113,113,0.25)'
              : '1px solid rgba(42,40,32,0.9)',
            color: busy
              ? '#F59E0B'
              : action.danger
                ? '#F87171'
                : '#6B6357',
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'all 0.15s',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={e => {
            if (!disabled) {
              e.currentTarget.style.borderColor = action.danger ? 'rgba(248,113,113,0.5)' : 'rgba(245,158,11,0.4)';
              e.currentTarget.style.color = action.danger ? '#F87171' : '#F59E0B';
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = action.danger ? 'rgba(248,113,113,0.25)' : 'rgba(42,40,32,0.9)';
            e.currentTarget.style.color = busy ? '#F59E0B' : action.danger ? '#F87171' : '#6B6357';
          }}
        >
          {busy ? 'RUNNING…' : 'RUN'}
        </button>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>

      {/* ── System section ── */}
      <SectionLabel>SYSTEM</SectionLabel>
      <div style={{ marginBottom: '16px' }}>
        {systemActions.map((a, i) => (
          <ActionRow key={a.key} action={a} isLast={i === systemActions.length - 1} />
        ))}
      </div>

      {/* ── AI section ── */}
      <SectionLabel>AI / ML</SectionLabel>
      <div style={{ marginBottom: '16px' }}>
        {aiActions.map((a, i) => (
          <ActionRow key={a.key} action={a} isLast={i === aiActions.length - 1} />
        ))}
      </div>

      {/* ── Advanced options toggle ── */}
      <button
        type="button"
        onClick={() => setAdvancedOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '5px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: '4px 0',
          marginBottom: advancedOpen ? '10px' : '0',
          color: '#4A443D',
          ...MONO,
          fontSize: '10px',
          letterSpacing: '0.1em',
          transition: 'color 0.15s',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = '#F59E0B'; }}
        onMouseLeave={e => { e.currentTarget.style.color = '#4A443D'; }}
      >
        {advancedOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        CLEANUP OPTIONS
      </button>

      {advancedOpen && (
        <div
          style={{
            marginBottom: '16px',
            padding: '14px',
            borderRadius: '8px',
            border: '1px solid rgba(42,40,32,0.9)',
            background: 'rgba(255,255,255,0.02)',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '10px',
          }}
        >
          {[
            { key: 'dryRun',          label: 'Dry Run',           disabled: false },
            { key: 'aggressive',      label: 'Aggressive',        disabled: false },
            { key: 'browserCache',    label: 'Browser Cache',     disabled: !options.aggressive },
            { key: 'trimWorkingSets', label: 'Working Sets',      disabled: !options.aggressive },
          ].map(({ key, label, disabled }) => (
            <label
              key={key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '7px',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.3 : 1,
                userSelect: 'none',
              }}
            >
              <input
                type="checkbox"
                checked={options[key]}
                disabled={disabled}
                onChange={e => setOptions(o => ({ ...o, [key]: e.target.checked }))}
                style={{ accentColor: '#F59E0B', width: '12px', height: '12px' }}
              />
              <span style={{ ...UI, fontSize: '12px', color: '#6B6357' }}>{label}</span>
            </label>
          ))}
        </div>
      )}

      {/* ── Result panel ── */}
      {lastAction && (
        <div>
          <button
            onClick={() => setShowResult(s => !s)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 0',
              marginBottom: showResult ? '10px' : '0',
              color: '#4A443D',
              ...MONO,
              fontSize: '10px',
              letterSpacing: '0.1em',
              transition: 'color 0.15s',
              width: '100%',
              textAlign: 'left',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = '#F59E0B'; }}
            onMouseLeave={e => { e.currentTarget.style.color = '#4A443D'; }}
          >
            {showResult ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            LAST RESULT
            <span style={{ marginLeft: '6px', color: '#3A342D' }}>·</span>
            <span style={{ color: '#3A342D', marginLeft: '2px' }}>{lastAction.friendlyName}</span>
          </button>

          {showResult && (
            <div
              style={{
                borderRadius: '8px',
                border: '1px solid rgba(42,40,32,0.9)',
                background: 'rgba(14,13,11,0.8)',
                padding: '14px',
                ...MONO,
                fontSize: '11px',
                color: '#6B6357',
                overflow: 'auto',
                maxHeight: '200px',
              }}
            >
              {/* Header row */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <span style={{ color: '#F59E0B', letterSpacing: '0.06em', fontSize: '10px' }}>
                  {lastAction.friendlyName}
                </span>
                <span style={{ color: '#3A342D', fontSize: '10px' }}>
                  {new Date(lastAction.at).toLocaleTimeString()}
                </span>
              </div>

              {result?.status === 'forbidden' && (
                <div style={{ color: '#F87171', marginBottom: '8px', fontSize: '10px', letterSpacing: '0.06em' }}>
                  ⚠ Enable ALLOW_SYSTEM_ACTIONS
                </div>
              )}

              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: '#A89F8C', margin: 0 }}>
                {formatPayload(result)}
              </pre>

              {result?.artifact && (
                <a
                  href={jobsApi.downloadUrl(result.id || result.job_id)}
                  target="_blank"
                  rel="noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', marginTop: '10px', color: '#F59E0B', textDecoration: 'none', fontSize: '10px' }}
                >
                  <ExternalLink size={10} /> Download Export
                </a>
              )}

              {/* History */}
              {history.length > 1 && (
                <div style={{ marginTop: '12px', borderTop: '1px solid rgba(42,40,32,0.6)', paddingTop: '10px' }}>
                  <div style={{ color: '#4A443D', fontSize: '10px', letterSpacing: '0.1em', marginBottom: '6px' }}>HISTORY</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '100px', overflowY: 'auto' }}>
                    {history.slice(0, 10).map(h => (
                      <button
                        key={h.id}
                        type="button"
                        onClick={() => { setResult(h.response); setLastAction({ key: h.key, friendlyName: h.friendlyName, at: h.at }); }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          textAlign: 'left',
                          padding: '2px 0',
                          ...MONO,
                          fontSize: '10px',
                          color: '#4A443D',
                          transition: 'color 0.1s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.color = '#F59E0B'; }}
                        onMouseLeave={e => { e.currentTarget.style.color = '#4A443D'; }}
                      >
                        <span style={{ color: '#3A342D' }}>›</span>
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {h.friendlyName}
                        </span>
                        <span style={{ color: '#3A342D', flexShrink: 0 }}>
                          {new Date(h.at).toLocaleTimeString()}
                        </span>
                        <span style={{ color: '#3A342D', flexShrink: 0 }}>
                          {h.meta?.dryRun ? 'preview' : 'live'}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '10px', letterSpacing: '0.14em', color: '#3A342D', marginBottom: '4px' }}>
      {children}
    </div>
  );
}
