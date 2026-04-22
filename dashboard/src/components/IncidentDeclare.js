import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { AlertTriangle, X, CheckCircle, ChevronDown } from 'lucide-react';

const C = {
  bg: 'rgb(22,20,16)', surface: 'rgb(31,29,24)', border: 'rgba(42,40,32,0.9)',
  overlay: 'rgba(0,0,0,0.75)',
  amber: '#F59E0B', teal: '#2DD4BF', red: '#F87171', green: '#4ADE80',
  text1: 'rgb(245,240,232)', text2: 'rgb(168,159,140)', text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace", ui: "'Outfit', sans-serif",
};

const SEV = [
  { value: 'SEV1', label: 'SEV-1 — Service down', color: C.red },
  { value: 'SEV2', label: 'SEV-2 — Major degradation', color: '#FB923C' },
  { value: 'SEV3', label: 'SEV-3 — Partial impact', color: C.amber },
  { value: 'SEV4', label: 'SEV-4 — Minor / monitoring', color: C.teal },
];

const SERVICES = [
  'API Gateway', 'Auth Service', 'Metrics Pipeline', 'Alert Engine',
  'Database', 'Cache Layer', 'WebSocket Hub', 'Remediation Engine',
  'ML Platform', 'Storage', 'Other',
];

function Field({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, letterSpacing: '0.08em' }}>
        {label}
      </label>
      {children}
    </div>
  );
}

const INPUT_STYLE = {
  background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6,
  padding: '8px 12px', fontFamily: C.mono, fontSize: 12, color: C.text1,
  outline: 'none', width: '100%', boxSizing: 'border-box',
};

export default function IncidentDeclare() {
  const [open, setOpen]               = useState(false);
  const [form, setForm]               = useState({ severity: 'SEV2', service: '', description: '', commander: '' });
  const [submitting, setSubmitting]   = useState(false);
  const [error, setError]             = useState(null);
  const [activeIncident, setActive]   = useState(null);
  const [resolving, setResolving]     = useState(false);
  const [apiAvailable, setApiAvail]   = useState(true);
  const mountedRef = useRef(true);

  const checkActive = useCallback(async () => {
    try {
      const inc = await apiService.getActiveIncident();
      if (!mountedRef.current) return;
      setActive(inc);
      setApiAvail(true);
    } catch (e) {
      if (!mountedRef.current) return;
      if (e?.response?.status === 404 || e?.response?.status === 501) setApiAvail(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    checkActive();
    const t = setInterval(checkActive, 30000);
    return () => { mountedRef.current = false; clearInterval(t); };
  }, [checkActive]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleDeclare = async () => {
    if (!form.service || !form.description.trim()) {
      setError('Service and description are required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const inc = await apiService.createIncident({
        severity:    form.severity,
        service:     form.service,
        description: form.description,
        commander:   form.commander || undefined,
      });
      setActive(inc);
      setOpen(false);
      setForm({ severity: 'SEV2', service: '', description: '', commander: '' });
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404 || status === 501) {
        setError('Incident API not yet implemented. See MISSING_ENDPOINTS.md.');
      } else {
        setError(e?.response?.data?.detail || e?.message || 'Failed to declare incident.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleResolve = async () => {
    if (!activeIncident?.id) return;
    setResolving(true);
    try {
      await apiService.resolveIncident(activeIncident.id);
      setActive(null);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Resolve failed.');
    } finally {
      setResolving(false);
    }
  };

  const sevMeta = SEV.find(s => s.value === form.severity) || SEV[1];
  const activeSevMeta = activeIncident ? SEV.find(s => s.value === activeIncident.severity) || SEV[1] : null;

  if (!apiAvailable && !activeIncident) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Incident API not yet implemented"
        style={{
          padding: '5px 12px', borderRadius: 6, cursor: 'not-allowed',
          background: 'rgba(107,99,87,0.15)', border: `1px solid rgba(107,99,87,0.3)`,
          fontFamily: C.mono, fontSize: 11, color: C.text3,
          display: 'flex', alignItems: 'center', gap: 6, letterSpacing: '0.06em',
        }}>
        <AlertTriangle size={13} />
        DECLARE INCIDENT
      </button>
    );
  }

  return (
    <>
      {/* Trigger button */}
      {activeIncident ? (
        <button
          onClick={() => setOpen(true)}
          style={{
            padding: '5px 12px', borderRadius: 6, cursor: 'pointer',
            background: `${activeSevMeta?.color || C.red}18`,
            border: `1px solid ${activeSevMeta?.color || C.red}40`,
            fontFamily: C.mono, fontSize: 11, color: activeSevMeta?.color || C.red,
            display: 'flex', alignItems: 'center', gap: 6, letterSpacing: '0.06em',
            animation: 'pulse 2s infinite',
          }}>
          <AlertTriangle size={13} />
          {activeIncident.severity} ACTIVE
        </button>
      ) : (
        <button
          onClick={() => setOpen(true)}
          style={{
            padding: '5px 12px', borderRadius: 6, cursor: 'pointer',
            background: 'rgba(248,113,113,0.1)', border: `1px solid ${C.red}30`,
            fontFamily: C.mono, fontSize: 11, color: C.red,
            display: 'flex', alignItems: 'center', gap: 6, letterSpacing: '0.06em',
          }}>
          <AlertTriangle size={13} />
          DECLARE INCIDENT
        </button>
      )}

      {/* Modal overlay */}
      {open && (
        <div
          onClick={e => { if (e.target === e.currentTarget) setOpen(false); }}
          style={{ position: 'fixed', inset: 0, background: C.overlay, zIndex: 10000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 14,
            padding: 28, width: '100%', maxWidth: 480, boxShadow: '0 24px 64px rgba(0,0,0,0.8)' }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <AlertTriangle size={18} color={C.red} />
                <span style={{ fontFamily: C.mono, fontSize: 13, letterSpacing: '0.1em', color: C.text1 }}>
                  {activeIncident ? 'ACTIVE INCIDENT' : 'DECLARE INCIDENT'}
                </span>
              </div>
              <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none',
                cursor: 'pointer', color: C.text3 }}>
                <X size={18} />
              </button>
            </div>

            {/* Active incident view */}
            {activeIncident ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ padding: 14, borderRadius: 8, background: `${activeSevMeta?.color || C.red}12`,
                  border: `1px solid ${activeSevMeta?.color || C.red}30` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontFamily: C.mono, fontSize: 12, color: activeSevMeta?.color || C.red }}>
                      {activeIncident.severity}
                    </span>
                    <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
                      #{activeIncident.id}
                    </span>
                  </div>
                  <div style={{ fontFamily: C.ui, fontSize: 13, color: C.text1, marginBottom: 4 }}>
                    {activeIncident.service}
                  </div>
                  <div style={{ fontFamily: C.ui, fontSize: 12, color: C.text2 }}>
                    {activeIncident.description}
                  </div>
                  {activeIncident.commander && (
                    <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 6 }}>
                      IC: {activeIncident.commander}
                    </div>
                  )}
                </div>
                {error && <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red }}>{error}</div>}
                <button
                  onClick={handleResolve}
                  disabled={resolving}
                  style={{ padding: '10px 0', borderRadius: 8, cursor: resolving ? 'not-allowed' : 'pointer',
                    background: resolving ? 'rgba(42,40,32,0.4)' : 'rgba(74,222,128,0.12)',
                    border: `1px solid ${C.green}40`, color: resolving ? C.text3 : C.green,
                    fontFamily: C.mono, fontSize: 12, letterSpacing: '0.08em',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <CheckCircle size={14} />
                  {resolving ? 'RESOLVING…' : 'MARK RESOLVED'}
                </button>
              </div>
            ) : (
              /* Declare form */
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <Field label="SEVERITY">
                  <div style={{ position: 'relative' }}>
                    <select
                      value={form.severity}
                      onChange={e => set('severity', e.target.value)}
                      style={{ ...INPUT_STYLE, appearance: 'none', paddingRight: 30,
                        color: sevMeta.color, borderColor: `${sevMeta.color}40` }}>
                      {SEV.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </select>
                    <ChevronDown size={12} style={{ position: 'absolute', right: 10, top: '50%',
                      transform: 'translateY(-50%)', color: C.text3, pointerEvents: 'none' }} />
                  </div>
                </Field>

                <Field label="AFFECTED SERVICE *">
                  <div style={{ position: 'relative' }}>
                    <select value={form.service} onChange={e => set('service', e.target.value)} style={{ ...INPUT_STYLE, appearance: 'none', paddingRight: 30 }}>
                      <option value="">Select service…</option>
                      {SERVICES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <ChevronDown size={12} style={{ position: 'absolute', right: 10, top: '50%',
                      transform: 'translateY(-50%)', color: C.text3, pointerEvents: 'none' }} />
                  </div>
                </Field>

                <Field label="DESCRIPTION *">
                  <textarea
                    value={form.description}
                    onChange={e => set('description', e.target.value)}
                    rows={3}
                    placeholder="Describe the impact, symptoms, and initial findings…"
                    style={{ ...INPUT_STYLE, resize: 'vertical', fontFamily: C.ui, lineHeight: 1.5 }}
                  />
                </Field>

                <Field label="INCIDENT COMMANDER (optional)">
                  <input
                    value={form.commander}
                    onChange={e => set('commander', e.target.value)}
                    placeholder="e.g. Jane Smith"
                    style={INPUT_STYLE}
                  />
                </Field>

                {error && (
                  <div style={{ fontFamily: C.mono, fontSize: 11, color: C.red,
                    padding: '8px 12px', borderRadius: 6, background: 'rgba(248,113,113,0.08)',
                    border: `1px solid ${C.red}30` }}>
                    {error}
                  </div>
                )}

                <button
                  onClick={handleDeclare}
                  disabled={submitting}
                  style={{ padding: '12px 0', borderRadius: 8, marginTop: 4,
                    cursor: submitting ? 'not-allowed' : 'pointer',
                    background: submitting ? 'rgba(42,40,32,0.4)' : 'rgba(248,113,113,0.15)',
                    border: `1px solid ${C.red}50`, color: submitting ? C.text3 : C.red,
                    fontFamily: C.mono, fontSize: 12, letterSpacing: '0.1em' }}>
                  {submitting ? 'DECLARING…' : 'DECLARE INCIDENT'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
