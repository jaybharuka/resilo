import React, { useEffect, useState } from 'react';
import { integrationsApi, authApi, apiService, realTimeService } from '../services/api';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';

export default function Settings() {
  const { role, logout } = useAuth();
  const [slackWebhook, setSlackWebhook] = useState('');
  const [discordWebhook, setDiscordWebhook] = useState('');
  const [busy, setBusy] = useState({ slack: false, discord: false });
  const [result, setResult] = useState({ slack: null, discord: null });
  const [pollMs, setPollMs] = useState(5000);
  const [health, setHealth] = useState(null);
  const [sse, setSse] = useState(realTimeService.getSSEStatus());
  const [openReg, setOpenReg] = useState(false);
  const [apiBase, setApiBase] = useState(() => {
    try { return localStorage.getItem('aiops:apiBase') || ''; } catch { return ''; }
  });

  const testSlack = async () => {
    setBusy((b) => ({ ...b, slack: true }));
    setResult((r) => ({ ...r, slack: null }));
    try {
      const res = await integrationsApi.testSlack({ webhook_url: slackWebhook || undefined, title: 'AIOps Test', status: 'OK', details: { env: 'local' } });
      setResult((r) => ({ ...r, slack: res }));
    } catch (e) {
      setResult((r) => ({ ...r, slack: { ok: false, error: e.message } }));
    } finally {
      setBusy((b) => ({ ...b, slack: false }));
    }
  };

  const testDiscord = async () => {
    setBusy((b) => ({ ...b, discord: true }));
    setResult((r) => ({ ...r, discord: null }));
    try {
      const res = await integrationsApi.testDiscord({ webhook_url: discordWebhook || undefined, content: 'Ping from AIOps', title: 'AIOps Test', fields: { env: 'local' } });
      setResult((r) => ({ ...r, discord: res }));
    } catch (e) {
      setResult((r) => ({ ...r, discord: { ok: false, error: e.message } }));
    } finally {
      setBusy((b) => ({ ...b, discord: false }));
    }
  };

  const refreshSession = async () => {
    try {
      const t = toast.loading('Refreshing session...');
      const res = await authApi.refresh();
      localStorage.setItem('aiops:token', res.token);
      toast.success('Session refreshed', { id: t });
    } catch (e) {
      toast.error('Session refresh failed');
    }
  };

  const runHealthCheck = async () => {
    try {
      const t = toast.loading('Checking backend health...');
      const res = await apiService.checkHealth();
      setHealth(res);
      if (res?.status === 'ok') toast.success('Backend healthy', { id: t }); else toast('Health checked', { id: t });
    } catch (e) {
      toast.error('Health check failed');
    }
  };

  useEffect(() => {
    // Prime health on load
    runHealthCheck();
    (async () => {
      const cfg = await apiService.getConfig();
      setOpenReg(!!cfg?.open_registration);
    })();
    const unsub = realTimeService.subscribe('sse-status', (st) => setSse(st));
    setSse(realTimeService.getSSEStatus());
    return () => { try { unsub && unsub(); } catch {} };
  }, []);

  return (
    <div className="p-6 space-y-6">
      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-lg font-semibold text-gray-900">Realtime & Session</h3>
        <div className="grid md:grid-cols-2 gap-4 mt-2">
          <div>
            <label className="block text-sm font-medium text-gray-700">Polling Interval</label>
            <div className="mt-1 flex gap-2 items-center">
              <input
                type="number"
                min={1000}
                step={500}
                value={pollMs}
                onChange={(e) => setPollMs(Number(e.target.value) || 5000)}
                className="w-40 rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="text-sm text-gray-500">ms</span>
              <button
                onClick={() => { realTimeService.setIntervalMs(pollMs); toast.success('Polling updated'); }}
                className="ml-2 inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-3 py-2 text-sm hover:bg-blue-700"
              >Apply</button>
            </div>
            <p className="text-xs text-gray-500 mt-1">Controls the background refresh cadence for system, insights, alerts, and processes.</p>
          </div>
          <div>
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700">Server-Sent Events (SSE)</label>
              <div className="mt-1 flex items-center gap-2 text-sm">
                <span className="px-2 py-0.5 rounded border border-gray-300">{sse.enabled ? 'Enabled' : 'Disabled'}</span>
                <span className="text-gray-500">Status: {sse.enabled ? (sse.connected ? 'connected' : 'pending') : 'off'}</span>
                <button
                  onClick={() => { realTimeService.setSSEnabled(!sse.enabled); toast.success(`SSE ${sse.enabled ? 'disabled' : 'enabled'}`); }}
                  className="ml-2 inline-flex items-center justify-center rounded-md bg-gray-100 text-gray-800 px-3 py-2 text-sm hover:bg-gray-200 border border-gray-300"
                >Toggle</button>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={refreshSession}
                className="inline-flex items-center justify-center rounded-md bg-emerald-600 text-white px-3 py-2 text-sm hover:bg-emerald-700"
              >Refresh Session</button>
              <button
                onClick={logout}
                className="inline-flex items-center justify-center rounded-md bg-gray-100 text-gray-800 px-3 py-2 text-sm hover:bg-gray-200 border border-gray-300"
              >Logout</button>
            </div>
            <div className="mt-3">
              <button
                onClick={runHealthCheck}
                className="inline-flex items-center justify-center rounded-md bg-indigo-600 text-white px-3 py-2 text-sm hover:bg-indigo-700"
              >Check Backend Health</button>
              {health && (
                <div className="mt-2 text-xs text-gray-600">Status: {health.status} • {health.timestamp}</div>
              )}
            </div>
          </div>
        </div>
      </section>
      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-lg font-semibold text-gray-900">Advanced Networking</h3>
        <p className="text-sm text-gray-600">Override API Base URL if your frontend and backend are on different hosts or ports.</p>
        <div className="mt-2 grid sm:grid-cols-[1fr_auto] gap-2">
          <input
            type="url"
            placeholder="http://127.0.0.1:5000"
            value={apiBase}
            onChange={(e)=>setApiBase(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => { try { if (apiBase) localStorage.setItem('aiops:apiBase', apiBase); else localStorage.removeItem('aiops:apiBase'); toast.success('API base updated. Reloading...'); setTimeout(()=>window.location.reload(), 600); } catch { toast.error('Failed to save'); } }}
            className="inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-4 py-2 font-medium hover:bg-blue-700"
          >Apply & Reload</button>
        </div>
        <p className="text-xs text-gray-500 mt-1">Leave blank to auto-detect from your current browser location.</p>
      </section>
      {openReg && (
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-lg font-semibold text-gray-900">Registration</h3>
          <p className="text-sm text-gray-600">Open registration is enabled. New users can register using the Register page.</p>
          <Link to="/register" className="inline-flex items-center justify-center mt-2 rounded-md bg-indigo-600 text-white px-3 py-2 text-sm hover:bg-indigo-700">Go to Register</Link>
        </section>
      )}
      <div>
        <h2 className="text-2xl font-bold mb-1">Settings</h2>
        <p className="text-gray-600">Configure integrations and preferences. Admin-only sections are marked.</p>
      </div>

      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-lg font-semibold text-gray-900">Slack Integration</h3>
        <p className="text-sm text-gray-600 mb-3">Provide a Slack Incoming Webhook URL or set SLACK_ALERTS_WEBHOOK in backend environment.</p>
        <div className="grid sm:grid-cols-[1fr_auto] gap-2">
          <input
            type="url"
            placeholder="https://hooks.slack.com/services/..."
            value={slackWebhook}
            onChange={(e) => setSlackWebhook(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={testSlack}
            disabled={busy.slack}
            className="inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-4 py-2 font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            {busy.slack ? 'Testing…' : 'Send Test'}
          </button>
        </div>
        {result.slack && (
          <div className={`mt-3 text-sm rounded-md px-3 py-2 border ${result.slack.ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
            {result.slack.ok ? 'Test sent successfully' : `Failed: ${result.slack.error || result.slack.response_text || 'Unknown error'}`}
          </div>
        )}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-lg font-semibold text-gray-900">Discord Integration</h3>
        <p className="text-sm text-gray-600 mb-3">Provide a Discord Webhook URL or set DISCORD_WEBHOOK_URL in backend environment.</p>
        <div className="grid sm:grid-cols-[1fr_auto] gap-2">
          <input
            type="url"
            placeholder="https://discord.com/api/webhooks/..."
            value={discordWebhook}
            onChange={(e) => setDiscordWebhook(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={testDiscord}
            disabled={busy.discord}
            className="inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-4 py-2 font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            {busy.discord ? 'Testing…' : 'Send Test'}
          </button>
        </div>
        {result.discord && (
          <div className={`mt-3 text-sm rounded-md px-3 py-2 border ${result.discord.ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
            {result.discord.ok ? 'Test sent successfully' : `Failed: ${result.discord.error || result.discord.response_text || 'Unknown error'}`}
          </div>
        )}
      </section>

      {role === 'admin' && (
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-lg font-semibold text-gray-900">Admin Settings</h3>
          <p className="text-sm text-gray-600">Reserved for administrative configurations.</p>
          <div className="mt-2 text-sm text-gray-500">Use the Invites page to onboard users securely with one-time tokens.</div>
        </section>
      )}
    </div>
  );
}