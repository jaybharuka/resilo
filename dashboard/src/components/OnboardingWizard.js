import React, { useState, useEffect, useRef } from 'react';
import { agentApi } from '../services/api';
import { agentsApi } from '../services/resiloApi';
import { Monitor, Terminal, Copy, CheckCheck, Loader, CheckCircle } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };
const C = {
  surface:    'rgb(22,20,16)',
  surface2:   'rgb(31,29,24)',
  border:     'rgba(42,40,32,0.9)',
  amber:      '#F59E0B',
  amberAlpha: 'rgba(245,158,11,0.1)',
  teal:       '#2DD4BF',
  red:        '#F87171',
  text1:      '#F5F0E8',
  text2:      '#A89F8C',
  text3:      '#6B6357',
  text4:      '#4A443D',
};
const PANEL = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: '12px', boxShadow: '0 4px 24px rgba(0,0,0,0.3)' };

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard?.writeText(text).catch(() => {}); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 6, cursor: 'pointer', transition: 'all 0.2s', background: copied ? 'rgba(45,212,191,0.12)' : C.amberAlpha, border: `1px solid ${copied ? 'rgba(45,212,191,0.3)' : 'rgba(245,158,11,0.3)'}`, color: copied ? C.teal : C.amber, ...MONO, fontSize: 11 }}
    >
      {copied ? <CheckCheck size={12} /> : <Copy size={12} />}
      {copied ? 'Copied!' : 'Copy command'}
    </button>
  );
}

function StepDot({ n, current }) {
  const done = n < current;
  const active = n === current;
  const col = done ? C.teal : active ? C.amber : C.text4;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <div style={{ width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: done ? `${C.teal}20` : active ? `${C.amber}20` : C.surface2, border: `2px solid ${col}`, transition: 'all 0.3s' }}>
        {done
          ? <CheckCircle size={14} color={C.teal} />
          : <span style={{ ...MONO, fontSize: 11, color: col }}>{n}</span>}
      </div>
    </div>
  );
}

export default function OnboardingWizard({ onAgentConnected }) {
  const [step, setStep]       = useState(1);
  const [label, setLabel]     = useState('');
  const [token, setToken]     = useState('');
  const [platform, setPlatform] = useState('windows');
  const [creating, setCreating] = useState(false);
  const [error, setError]     = useState('');
  const [timedOut, setTimedOut] = useState(false);
  const pollRef    = useRef(null);
  const timeoutRef = useRef(null);
  const prevIds    = useRef([]);

  const backendUrl = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : `${window.location.protocol}//${window.location.hostname}`;
  const agentUrl = 'https://raw.githubusercontent.com/jaybharuka/resilo/main/desktop_agent/resilo_agent.py';

  const cmds = {
    windows: `pip install psutil -q; Invoke-WebRequest -Uri "${agentUrl}" -OutFile "$env:USERPROFILE\\resilo_agent.py"; $env:RESILO_ONBOARD_TOKEN="${token}"; $env:RESILO_BACKEND_URL="${backendUrl}"; python "$env:USERPROFILE\\resilo_agent.py"`,
    macos:   `pip install psutil -q && curl -sL "${agentUrl}" -o ~/resilo_agent.py && RESILO_ONBOARD_TOKEN=${token} RESILO_BACKEND_URL=${backendUrl} python ~/resilo_agent.py`,
    linux:   `pip install psutil -q && curl -sL "${agentUrl}" -o ~/resilo_agent.py && RESILO_ONBOARD_TOKEN=${token} RESILO_BACKEND_URL=${backendUrl} python ~/resilo_agent.py`,
  };

  const handleGenerate = async () => {
    if (!label.trim()) { setError('Enter a label for this device.'); return; }
    setCreating(true); setError('');
    try {
      const data = await agentApi.onboard(label.trim());
      setToken(data.token);
      setStep(2);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to generate token.');
    } finally { setCreating(false); }
  };

  const startWaiting = async () => {
    setStep(3);
    try {
      const cur = await agentsApi.list();
      prevIds.current = cur.map(a => a.id);
    } catch {}
    pollRef.current = setInterval(async () => {
      try {
        const agents = await agentsApi.list();
        const fresh = agents.find(a => a.status === 'live' && !prevIds.current.includes(a.id));
        if (fresh) {
          clearInterval(pollRef.current); clearTimeout(timeoutRef.current);
          onAgentConnected && onAgentConnected();
        } else { prevIds.current = agents.map(a => a.id); }
      } catch {}
    }, 3000);
    timeoutRef.current = setTimeout(() => { clearInterval(pollRef.current); setTimedOut(true); }, 300000);
  };

  useEffect(() => () => { clearInterval(pollRef.current); clearTimeout(timeoutRef.current); }, []);

  const PLATFORMS = [{ key: 'windows', label: 'Windows', icon: <Monitor size={13} /> }, { key: 'macos', label: 'macOS', icon: <Terminal size={13} /> }, { key: 'linux', label: 'Linux', icon: <Terminal size={13} /> }];

  return (
    <div style={{ maxWidth: 620, margin: '0 auto', ...PANEL, overflow: 'hidden' }}>
      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>

      {/* Header */}
      <div style={{ padding: '20px 24px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.text2 }}>ADD YOUR FIRST AGENT</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {[1, 2, 3].map(n => (
            <React.Fragment key={n}>
              <StepDot n={n} current={step} />
              {n < 3 && <div style={{ width: 24, height: 1, background: n < step ? C.teal : C.border, transition: 'background 0.3s' }} />}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div style={{ padding: '28px 28px' }}>
        {/* Step 1 — Name agent */}
        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div>
              <p style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.amber, margin: '0 0 8px' }}>STEP 1 — NAME YOUR AGENT</p>
              <p style={{ ...UI, fontSize: 13, color: C.text3, margin: 0, lineHeight: 1.6 }}>Give the machine a label so you can identify it in your dashboard.</p>
            </div>
            <div>
              <label style={{ ...MONO, fontSize: 10, letterSpacing: '0.12em', color: C.text4, display: 'block', marginBottom: 8 }}>AGENT LABEL</label>
              <input
                autoFocus
                value={label}
                onChange={e => setLabel(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleGenerate()}
                placeholder="e.g. My MacBook, Prod Server, Dev Box"
                style={{ width: '100%', boxSizing: 'border-box', background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 14px', ...UI, fontSize: 13, color: C.text1, outline: 'none' }}
              />
              {error && <p style={{ ...MONO, fontSize: 11, color: C.red, margin: '8px 0 0' }}>{error}</p>}
            </div>
            <button
              onClick={handleGenerate} disabled={creating}
              style={{ padding: '10px 0', borderRadius: 8, cursor: creating ? 'not-allowed' : 'pointer', background: creating ? C.surface2 : C.amberAlpha, border: `1px solid ${creating ? C.border : 'rgba(245,158,11,0.35)'}`, color: creating ? C.text4 : C.amber, ...MONO, fontSize: 12, letterSpacing: '0.08em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, transition: 'all 0.15s' }}
            >
              {creating ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> GENERATING…</> : 'GENERATE INSTALL TOKEN'}
            </button>
          </div>
        )}

        {/* Step 2 — Install command */}
        {step === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div>
              <p style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.amber, margin: '0 0 8px' }}>STEP 2 — INSTALL ON YOUR MACHINE</p>
              <p style={{ ...UI, fontSize: 13, color: C.text3, margin: 0, lineHeight: 1.6 }}>Run this on the machine you want to monitor.</p>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {PLATFORMS.map(p => (
                <button key={p.key} onClick={() => setPlatform(p.key)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 6, cursor: 'pointer', ...MONO, fontSize: 10, background: platform === p.key ? `${C.amber}20` : 'transparent', border: `1px solid ${platform === p.key ? C.amber : C.border}`, color: platform === p.key ? C.amber : C.text4 }}>
                  {p.icon} {p.label}
                </button>
              ))}
            </div>
            <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: '14px 16px' }}>
              <code style={{ ...MONO, fontSize: 11, color: C.teal, lineHeight: 1.7, wordBreak: 'break-all', display: 'block' }}>{cmds[platform]}</code>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <CopyBtn text={cmds[platform]} />
            </div>
            <button
              onClick={startWaiting}
              style={{ padding: '10px 0', borderRadius: 8, cursor: 'pointer', background: C.amberAlpha, border: '1px solid rgba(245,158,11,0.35)', color: C.amber, ...MONO, fontSize: 12, letterSpacing: '0.08em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
            >
              I'VE RUN THE COMMAND →
            </button>
          </div>
        )}

        {/* Step 3 — Waiting */}
        {step === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20, alignItems: 'center', padding: '12px 0' }}>
            <p style={{ ...MONO, fontSize: 11, letterSpacing: '0.12em', color: C.amber, margin: 0 }}>STEP 3 — WAITING FOR CONNECTION</p>
            {!timedOut ? (
              <>
                <div style={{ width: 48, height: 48, borderRadius: '50%', border: `3px solid ${C.border}`, borderTopColor: C.teal, animation: 'spin 1s linear infinite' }} />
                <p style={{ ...UI, fontSize: 14, color: C.text2, margin: 0, textAlign: 'center', lineHeight: 1.6 }}>
                  Waiting for <strong style={{ color: C.text1 }}>{label}</strong> to connect…
                  <br />
                  <span style={{ ...MONO, fontSize: 11, color: C.text4 }}>Checking every 3 seconds</span>
                </p>
              </>
            ) : (
              <div style={{ textAlign: 'center' }}>
                <p style={{ ...UI, fontSize: 14, color: C.amber, margin: '0 0 10px' }}>Taking longer than expected.</p>
                <p style={{ ...UI, fontSize: 13, color: C.text3, margin: '0 0 14px', lineHeight: 1.6 }}>Make sure the command ran without errors and the machine has internet access.</p>
                <a href="https://github.com/jaybharuka/resilo/blob/main/README.md" target="_blank" rel="noreferrer" style={{ ...MONO, fontSize: 11, color: C.amber, textDecoration: 'underline' }}>
                  View install guide ↗
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
