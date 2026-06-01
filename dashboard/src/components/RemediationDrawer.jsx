/**
 * RemediationDrawer — slides in from the right on any AgentDetail view.
 * Runs proactive AI analysis and presents a ranked remediation action queue.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { agentsApi } from '../services/resiloApi';
import {
  X, Bot, Play, CheckCircle, XCircle, Clock,
  AlertTriangle, Cpu, HardDrive, MemoryStick, Zap,
  RotateCcw, ChevronRight, Loader,
} from 'lucide-react';

// ── Design tokens (match RemoteAgents.js) ────────────────────────────────────
const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const UI      = { fontFamily: "'Outfit', sans-serif" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const C = {
  bg:         'rgb(14,13,11)',
  surface:    'rgb(22,20,16)',
  surface2:   'rgb(31,29,24)',
  surface3:   'rgb(38,36,30)',
  border:     'rgba(42,40,32,0.9)',
  amber:      '#F59E0B',
  amberAlpha: 'rgba(245,158,11,0.08)',
  teal:       '#2DD4BF',
  tealAlpha:  'rgba(45,212,191,0.08)',
  red:        '#F87171',
  redAlpha:   'rgba(248,113,113,0.08)',
  purple:     '#A78BFA',
  purpleAlpha:'rgba(167,139,250,0.08)',
  text1:      'rgba(255,248,230,0.95)',
  text2:      'rgba(255,248,230,0.75)',
  text3:      'rgba(255,248,230,0.45)',
  text4:      'rgba(255,248,230,0.28)',
};

const PANEL = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 8,
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const SEVERITY_META = {
  critical: { color: C.red,    bg: C.redAlpha,    label: 'CRITICAL' },
  high:     { color: C.amber,  bg: C.amberAlpha,  label: 'HIGH'     },
  medium:   { color: C.purple, bg: C.purpleAlpha, label: 'MEDIUM'   },
};

const ISSUE_ICON = { cpu: Cpu, memory: MemoryStick, disk: HardDrive, service: Zap };

const RISK_META = {
  low:    { color: C.teal,   label: 'LOW RISK'  },
  medium: { color: C.amber,  label: 'MED RISK'  },
  high:   { color: C.red,    label: 'HIGH RISK' },
};

const EXEC_LABELS = {
  dry_run:          { label: 'DRY RUN',  color: C.text3  },
  manual_approval:  { label: 'MANUAL',   color: C.amber  },
  auto_safe:        { label: 'AUTO',     color: C.teal   },
};

function ConfBar({ pct }) {
  const col = pct >= 80 ? C.teal : pct >= 60 ? C.amber : C.red;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ ...MONO, fontSize: 10, color: C.text4, minWidth: 32 }}>{pct}%</span>
      <div style={{ flex: 1, height: 3, borderRadius: 2, background: C.surface3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: col, borderRadius: 2, transition: 'width 0.6s' }} />
      </div>
    </div>
  );
}

function ActionStatusBadge({ status }) {
  const meta = {
    pending:  { color: C.text3,  icon: Clock,       label: 'PENDING'  },
    approved: { color: C.teal,   icon: CheckCircle, label: 'APPROVED' },
    rejected: { color: C.red,    icon: XCircle,     label: 'REJECTED' },
    queued:   { color: C.amber,  icon: ChevronRight,label: 'QUEUED'   },
    skipped:  { color: C.text4,  icon: Clock,       label: 'SKIPPED'  },
  }[status] || { color: C.text3, icon: Clock, label: status?.toUpperCase() };
  const Icon = meta.icon;
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 4, ...MONO, fontSize: 9, color: meta.color }}>
      <Icon size={10} /> {meta.label}
    </span>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function RemediationDrawer({ agent, open, onClose }) {
  const [phase, setPhase]           = useState('idle');   // idle | scanning | complete | error
  const [plan,  setPlan]            = useState(null);
  const [actionStates, setActionStates] = useState({});   // {idx: 'pending'|'approved'|'rejected'|'queued'}
  const [typeText, setTypeText]     = useState('');
  const [history, setHistory]       = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [errMsg, setErrMsg]         = useState('');
  const typeRef = useRef(null);
  const pollRef = useRef(null);

  // Poll history every 3s while drawer is open
  useEffect(() => {
    if (!open || !agent?.id) {
      clearInterval(pollRef.current);
      return;
    }
    const fetch = () => agentsApi.remediationHistory(null, agent.id).then(setHistory).catch(() => {});
    fetch();
    pollRef.current = setInterval(fetch, 3000);
    return () => clearInterval(pollRef.current);
  }, [open, agent?.id]);

  // Typewriter effect for reasoning
  useEffect(() => {
    if (!plan?.reasoning) return;
    setTypeText('');
    let i = 0;
    typeRef.current = setInterval(() => {
      i++;
      setTypeText(plan.reasoning.slice(0, i));
      if (i >= plan.reasoning.length) clearInterval(typeRef.current);
    }, 18);
    return () => clearInterval(typeRef.current);
  }, [plan?.reasoning]);

  const runAnalysis = useCallback(async () => {
    if (!agent?.id) return;
    setPhase('scanning');
    setPlan(null);
    setTypeText('');
    setActionStates({});
    setErrMsg('');
    try {
      const result = await agentsApi.remediationAnalyze(null, agent.id);
      const states = {};
      (result.actions || []).forEach((_, i) => { states[i] = 'pending'; });
      setActionStates(states);
      setPlan(result);
      setPhase('complete');
      setHistory(h => [result, ...h].slice(0, 10));
    } catch (err) {
      console.error('[RemediationDrawer] analyze failed:', err);
      const msg = err?.response?.data?.detail || err?.message || 'Unknown error';
      setErrMsg(msg);
      setPhase('error');
    }
  }, [agent?.id]);

  const handleApprove = useCallback(async (idx, action) => {
    setActionStates(s => ({ ...s, [idx]: 'queued' }));
    try {
      await agentsApi.remediationExecute(null, agent.id, action.command, action.target);
      setActionStates(s => ({ ...s, [idx]: 'approved' }));
    } catch {
      setActionStates(s => ({ ...s, [idx]: 'pending' }));
    }
  }, [agent?.id]);

  const handleReject = useCallback((idx) => {
    setActionStates(s => ({ ...s, [idx]: 'rejected' }));
  }, []);

  const reset = () => { setPhase('idle'); setPlan(null); setTypeText(''); setActionStates({}); setErrMsg(''); };

  const execMeta  = EXEC_LABELS[plan?.exec_mode || agent?.execution_mode] || EXEC_LABELS.dry_run;
  const isDry     = (plan?.exec_mode || agent?.execution_mode) === 'dry_run';
  const isManual  = (plan?.exec_mode || agent?.execution_mode) === 'manual_approval';
  const isAuto    = (plan?.exec_mode || agent?.execution_mode) === 'auto_safe';

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
          zIndex: 200, opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
          transition: 'opacity 0.25s',
        }}
      />

      {/* Drawer panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 480,
        background: C.bg, borderLeft: `1px solid ${C.border}`,
        zIndex: 201, display: 'flex', flexDirection: 'column',
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.28s cubic-bezier(0.4,0,0.2,1)',
        overflowY: 'auto',
      }}>

        {/* ── Header ── */}
        <div style={{ padding: '18px 20px 14px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <Bot size={18} color={C.amber} />
            <span style={{ ...DISPLAY, fontSize: 20, color: C.text1, letterSpacing: '0.08em' }}>
              REMEDIATION AGENT
            </span>
            <span style={{ marginLeft: 'auto', ...MONO, fontSize: 9, color: execMeta.color,
              background: `${execMeta.color}18`, border: `1px solid ${execMeta.color}40`,
              borderRadius: 4, padding: '2px 8px' }}>
              {execMeta.label}
            </span>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.text3, padding: 4 }}>
              <X size={16} />
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%',
              background: agent?.status === 'live' ? C.teal : C.text4,
              boxShadow: agent?.status === 'live' ? `0 0 6px ${C.teal}80` : 'none',
              display: 'inline-block', flexShrink: 0 }} />
            <span style={{ ...UI, fontSize: 14, color: C.text2 }}>{agent?.label}</span>
            <span style={{ ...MONO, fontSize: 10, color: C.text4, marginLeft: 'auto' }}>
              {agent?.info?.os || agent?.platform_info?.platform || ''}
            </span>
          </div>
        </div>

        {/* ── Body ── */}
        <div style={{ flex: 1, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>

          {/* Error banner */}
          {phase === 'error' && (
            <div style={{ ...PANEL, padding: '12px 14px', borderLeft: `3px solid ${C.red}`, background: C.redAlpha }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <AlertTriangle size={13} color={C.red} />
                <span style={{ ...MONO, fontSize: 9, color: C.red }}>ANALYSIS FAILED</span>
              </div>
              <div style={{ ...UI, fontSize: 12, color: C.text2 }}>{errMsg}</div>
            </div>
          )}

          {/* Run button */}
          <button
            onClick={runAnalysis}
            disabled={phase === 'scanning'}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              width: '100%', padding: '11px 0', borderRadius: 6, cursor: phase === 'scanning' ? 'not-allowed' : 'pointer',
              background: phase === 'scanning' ? C.surface2 : C.amberAlpha,
              border: `1px solid ${phase === 'scanning' ? C.border : C.amber}60`,
              color: phase === 'scanning' ? C.text3 : C.amber,
              ...MONO, fontSize: 11, letterSpacing: '0.1em',
              transition: 'all 0.15s',
            }}
          >
            {phase === 'scanning'
              ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> SCANNING SYSTEM…</>
              : <><Play size={13} /> RUN ANALYSIS</>
            }
          </button>

          {/* ── Detected Issues ── */}
          {phase === 'complete' && plan && (
            <>
              <div>
                <div style={{ ...MONO, fontSize: 9, letterSpacing: '0.12em', color: C.text4, marginBottom: 10 }}>
                  DETECTED ISSUES ({plan.issues?.length || 0})
                </div>
                {plan.issues?.length === 0 && (
                  <div style={{ ...PANEL, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
                    <CheckCircle size={14} color={C.teal} />
                    <span style={{ ...UI, fontSize: 13, color: C.teal }}>No issues detected — system healthy</span>
                  </div>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {(plan.issues || []).map((issue, i) => {
                    const sev  = SEVERITY_META[issue.severity] || SEVERITY_META.medium;
                    const Icon = ISSUE_ICON[issue.type] || AlertTriangle;
                    const conf = Math.round((issue.confidence || 0) * 100);
                    return (
                      <div key={i} style={{ ...PANEL, padding: '12px 14px', borderLeft: `3px solid ${sev.color}` }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <Icon size={13} color={sev.color} />
                          <span style={{ ...MONO, fontSize: 9, color: sev.color,
                            background: sev.bg, border: `1px solid ${sev.color}40`,
                            borderRadius: 3, padding: '1px 6px' }}>{sev.label}</span>
                          <span style={{ ...MONO, fontSize: 9, color: C.text4, textTransform: 'uppercase' }}>{issue.type}</span>
                        </div>
                        <div style={{ ...UI, fontSize: 12, color: C.text2, marginBottom: 6 }}>{issue.description}</div>
                        <ConfBar pct={conf} />
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* ── AI Reasoning ── */}
              <div>
                <div style={{ ...MONO, fontSize: 9, letterSpacing: '0.12em', color: C.text4, marginBottom: 10 }}>
                  AI REASONING
                  {plan.decision_source === 'rule_fallback' && (
                    <span style={{ marginLeft: 8, color: C.amber }}>(RULE FALLBACK)</span>
                  )}
                </div>
                <div style={{ ...PANEL, padding: '14px 16px', background: C.surface2 }}>
                  <p style={{ ...UI, fontSize: 13, color: C.text2, lineHeight: 1.6, margin: 0, minHeight: 40 }}>
                    {typeText}
                    <span style={{ opacity: typeText.length < (plan.reasoning?.length || 0) ? 1 : 0,
                      borderRight: `2px solid ${C.amber}`, marginLeft: 2 }}>&nbsp;</span>
                  </p>
                </div>
              </div>

              {/* ── Remediation Actions ── */}
              <div>
                <div style={{ ...MONO, fontSize: 9, letterSpacing: '0.12em', color: C.text4, marginBottom: 10 }}>
                  REMEDIATION ACTIONS ({plan.actions?.length || 0})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {(plan.actions || []).map((action, i) => {
                    const risk   = RISK_META[action.risk] || RISK_META.low;
                    const state  = actionStates[i] || 'pending';
                    const isDone = state === 'approved' || state === 'rejected' || state === 'queued';
                    // Derive confidence from matching issue type
                    const matchIssue = (plan.issues || []).find(iss => iss.type === action.type);
                    const conf = matchIssue ? Math.round((matchIssue.confidence || 0) * 100) : null;
                    return (
                      <div key={i} style={{ ...PANEL, padding: '12px 14px',
                        opacity: state === 'rejected' ? 0.45 : 1, transition: 'opacity 0.2s' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <span style={{ ...MONO, fontSize: 10, color: C.text1, flex: 1 }}>{action.command}</span>
                          <span style={{ ...MONO, fontSize: 9, color: risk.color,
                            background: `${risk.color}18`, border: `1px solid ${risk.color}40`,
                            borderRadius: 3, padding: '1px 6px' }}>{risk.label}</span>
                          {action.auto_queued && (
                            <span style={{ ...MONO, fontSize: 9, color: C.teal,
                              background: `${C.teal}18`, border: `1px solid ${C.teal}50`,
                              borderRadius: 3, padding: '1px 6px' }}>AUTO QUEUED</span>
                          )}
                          {isDone && <ActionStatusBadge status={state} />}
                        </div>
                        <div style={{ ...UI, fontSize: 12, color: C.text3, marginBottom: 6 }}>
                          {action.description}
                        </div>
                        {conf !== null && <ConfBar pct={conf} />}
                        {action.target && (
                          <div style={{ ...MONO, fontSize: 10, color: C.text4, marginTop: 4 }}>target: {action.target}</div>
                        )}

                        {/* Execution controls */}
                        {!isDry && !isDone && !action.auto_queued && (
                          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                            {isManual && (
                              <>
                                <button onClick={() => handleApprove(i, action)}
                                  style={{ flex: 1, padding: '6px 0', borderRadius: 4, cursor: 'pointer',
                                    background: C.tealAlpha, border: `1px solid ${C.teal}50`,
                                    color: C.teal, ...MONO, fontSize: 10 }}>
                                  ✓ APPROVE
                                </button>
                                <button onClick={() => handleReject(i)}
                                  style={{ flex: 1, padding: '6px 0', borderRadius: 4, cursor: 'pointer',
                                    background: C.redAlpha, border: `1px solid ${C.red}50`,
                                    color: C.red, ...MONO, fontSize: 10 }}>
                                  ✗ REJECT
                                </button>
                              </>
                            )}
                            {isAuto && (
                              <div style={{ ...MONO, fontSize: 10, color: C.teal, display: 'flex', alignItems: 'center', gap: 6 }}>
                                <Zap size={11} /> AUTO-EXECUTING…
                              </div>
                            )}
                          </div>
                        )}
                        {isDry && (
                          <div style={{ ...MONO, fontSize: 10, color: C.text4, marginTop: 8 }}>
                            DRY RUN — no execution
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {/* ── History ── */}
          {history.length > 0 && (
            <div>
              <button
                onClick={() => setHistoryOpen(h => !h)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none',
                  cursor: 'pointer', color: C.text4, padding: 0, ...MONO, fontSize: 9, letterSpacing: '0.12em' }}>
                <ChevronRight size={11} style={{ transform: historyOpen ? 'rotate(90deg)' : 'none', transition: '0.15s' }} />
                PAST RUNS ({history.length})
              </button>
              {historyOpen && (
                <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {history.map((run, i) => (
                    <div key={run.id || i} style={{ ...PANEL, padding: '10px 14px', background: C.surface2 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ ...MONO, fontSize: 9, color: C.text4 }}>
                          {run.created_at ? new Date(run.created_at).toLocaleString() : '—'}
                        </span>
                        <span style={{ ...MONO, fontSize: 9, color: C.text3, marginLeft: 'auto' }}>
                          {run.issues?.length || 0} issues · {run.actions?.length || 0} actions
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div style={{ padding: '12px 20px', borderTop: `1px solid ${C.border}`,
          display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          <span style={{ ...MONO, fontSize: 10, color: phase === 'scanning' ? C.amber : phase === 'complete' ? C.teal : phase === 'error' ? C.red : C.text4 }}>
            {phase === 'scanning' ? '● SCANNING…' : phase === 'complete' ? '● COMPLETE' : phase === 'error' ? '✗ ERROR' : '○ IDLE'}
          </span>
          {phase !== 'idle' && (
            <button onClick={reset}
              style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, background: 'none',
                border: `1px solid ${C.border}`, borderRadius: 4, cursor: 'pointer',
                color: C.text3, padding: '4px 10px', ...MONO, fontSize: 10 }}>
              <RotateCcw size={10} /> RESET
            </button>
          )}
        </div>
      </div>

      {/* Spin keyframe */}
      <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
    </>
  );
}
