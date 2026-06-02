import React, { useEffect, useState, useCallback } from 'react';
import apiService from '../services/api';

// ── Routing badge ─────────────────────────────────────────────────────────────
function RoutingBadge({ routing }) {
  const map = {
    auto_execute:        { label: 'AUTO EXECUTE',       bg: '#dc2626', color: '#fff' },
    manual_approval:     { label: 'MANUAL APPROVAL',    bg: '#d97706', color: '#fff' },
    investigation_only:  { label: 'INVESTIGATE ONLY',   bg: '#6366f1', color: '#fff' },
  };
  const style = map[routing] || { label: routing || 'UNKNOWN', bg: '#4b5563', color: '#fff' };
  return (
    <span style={{
      background: style.bg, color: style.color,
      padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700,
      letterSpacing: '0.05em',
    }}>
      {style.label}
    </span>
  );
}

// ── Confidence bar ────────────────────────────────────────────────────────────
function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 95 ? '#dc2626' : pct >= 70 ? '#d97706' : '#6366f1';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, background: '#374151', borderRadius: 4, height: 8 }}>
        <div style={{ width: `${pct}%`, background: color, borderRadius: 4, height: 8,
                      transition: 'width 0.4s ease' }} />
      </div>
      <span style={{ fontSize: 13, fontWeight: 600, color, minWidth: 36 }}>{pct}%</span>
    </div>
  );
}

// ── Stage chip ────────────────────────────────────────────────────────────────
const STAGES = [
  'EVIDENCE_COLLECTION',
  'HISTORICAL_ANALYSIS',
  'HYPOTHESIS_GENERATION',
  'ROOT_CAUSE_ANALYSIS',
  'ACTION_PLANNING',
];

function StageProgress({ currentStage, status }) {
  const currentIdx = STAGES.indexOf(currentStage);
  const completed = status === 'completed';
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 12 }}>
      {STAGES.map((s, i) => {
        const done = completed || i < currentIdx;
        const active = !completed && i === currentIdx;
        return (
          <span key={s} style={{
            padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 600,
            background: done ? '#065f46' : active ? '#1e40af' : '#1f2937',
            color: done ? '#6ee7b7' : active ? '#93c5fd' : '#6b7280',
            border: active ? '1px solid #3b82f6' : '1px solid transparent',
          }}>
            {s.replace(/_/g, ' ')}
          </span>
        );
      })}
    </div>
  );
}

// ── Hypothesis list ───────────────────────────────────────────────────────────
function HypothesisList({ hypotheses }) {
  if (!hypotheses || hypotheses.length === 0) return <p style={{ color: '#6b7280', fontSize: 13 }}>No hypotheses generated.</p>;
  return (
    <ol style={{ paddingLeft: 16, margin: 0 }}>
      {hypotheses.map((h, i) => (
        <li key={i} style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
            <span style={{ fontSize: 13, color: '#e5e7eb', flex: 1 }}>{h.cause}</span>
            <span style={{ fontSize: 12, color: '#d97706', fontWeight: 600 }}>
              {Math.round((h.confidence || 0) * 100)}%
            </span>
          </div>
          {h.evidence && h.evidence.length > 0 && (
            <ul style={{ margin: '2px 0 0 12px', padding: 0, listStyle: 'disc', color: '#9ca3af', fontSize: 12 }}>
              {h.evidence.slice(0, 3).map((e, j) => <li key={j}>{e}</li>)}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

// ── Timeline ──────────────────────────────────────────────────────────────────
function Timeline({ events }) {
  if (!events || events.length === 0) return <p style={{ color: '#6b7280', fontSize: 13 }}>No timeline events.</p>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {events.map((e, i) => {
        const ts = e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '';
        return (
          <div key={i} style={{ display: 'flex', gap: 10, fontSize: 12 }}>
            <span style={{ color: '#6b7280', minWidth: 65, flexShrink: 0 }}>{ts}</span>
            <span style={{ color: '#6b7280', minWidth: 60, flexShrink: 0, fontSize: 10, paddingTop: 2 }}>
              {(e.stage || '').replace(/_/g, ' ')}
            </span>
            <span style={{ color: '#d1d5db' }}>{e.event || e.note || ''}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Similar incident card ─────────────────────────────────────────────────────
function SimilarCard({ match }) {
  const score = Math.round((match.similarity_score || 0) * 100);
  const outcome = match.success === true ? '✓ Resolved' : match.success === false ? '✗ Failed' : '? Unknown';
  const outcomeColor = match.success === true ? '#10b981' : match.success === false ? '#ef4444' : '#6b7280';
  return (
    <div style={{ background: '#1f2937', borderRadius: 8, padding: '10px 14px', marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: '#e5e7eb' }}>{match.title}</span>
        <span style={{ fontSize: 12, color: '#6b7280' }}>similarity {score}%</span>
      </div>
      <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 4 }}>{match.root_cause}</div>
      <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
        <span>Action: <b style={{ color: '#93c5fd' }}>{match.executed_action || match.recommended_action}</b></span>
        <span style={{ color: outcomeColor }}>{outcome}</span>
        {match.resolution_time && (
          <span style={{ color: '#6b7280' }}>Resolved in {Math.round(match.resolution_time)}s</span>
        )}
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────
export default function InvestigationPanel() {
  const [investigations, setInvestigations] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('evidence');
  const [statusFilter, setStatusFilter] = useState('');

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiService.listInvestigations(30, statusFilter || null);
      setInvestigations(res.items || []);
    } catch (err) {
      setError(err.message || 'Failed to load investigations');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const openDetail = async (inv) => {
    setSelected(inv.id);
    setDetailLoading(true);
    setActiveTab('evidence');
    try {
      const res = await apiService.getInvestigation(inv.id);
      setDetail(res.investigation);
    } catch {
      setDetail(inv);
    } finally {
      setDetailLoading(false);
    }
  };

  // ── Styles ──────────────────────────────────────────────────────────────────
  const panelStyle = { background: '#111827', borderRadius: 12, padding: 24, color: '#e5e7eb' };
  const cardStyle = (active) => ({
    background: active ? '#1e3a5f' : '#1f2937',
    border: active ? '1px solid #3b82f6' : '1px solid #374151',
    borderRadius: 8, padding: '12px 16px', marginBottom: 8, cursor: 'pointer',
    transition: 'all 0.15s',
  });
  const tabStyle = (active) => ({
    padding: '6px 16px', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer',
    background: active ? '#1e40af' : 'transparent',
    color: active ? '#fff' : '#6b7280',
    border: 'none',
  });
  const sectionStyle = { marginBottom: 20 };
  const labelStyle = { fontSize: 11, color: '#6b7280', textTransform: 'uppercase',
                       letterSpacing: '0.08em', marginBottom: 6, display: 'block' };

  const TABS = ['evidence', 'history', 'hypotheses', 'root_cause', 'timeline'];

  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>AI Investigations</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            style={{ background: '#1f2937', color: '#e5e7eb', border: '1px solid #374151',
                     borderRadius: 6, padding: '4px 8px', fontSize: 13 }}
          >
            <option value="">All statuses</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          <button
            onClick={fetchList}
            style={{ background: '#1e40af', color: '#fff', border: 'none', borderRadius: 6,
                     padding: '6px 14px', fontSize: 13, cursor: 'pointer' }}
          >
            Refresh
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 20 }}>
        {/* ── Left: Investigation list ── */}
        <div>
          {loading && <p style={{ color: '#6b7280' }}>Loading…</p>}
          {error && <p style={{ color: '#ef4444' }}>{error}</p>}
          {!loading && investigations.length === 0 && (
            <p style={{ color: '#6b7280', fontSize: 13 }}>
              No investigations yet. Investigations are created automatically when an alert fires.
            </p>
          )}
          {investigations.map(inv => (
            <div key={inv.id} style={cardStyle(selected === inv.id)} onClick={() => openDetail(inv)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 12, color: '#6b7280', fontFamily: 'monospace' }}>{inv.id}</span>
                <RoutingBadge routing={inv.action_routing} />
              </div>
              <div style={{ fontSize: 13, color: '#d1d5db', marginBottom: 4 }}>
                Agent: <b style={{ color: '#93c5fd' }}>{inv.agent_id?.slice(0, 8)}…</b>
              </div>
              <ConfidenceBar value={inv.confidence} />
              <div style={{ marginTop: 6, display: 'flex', gap: 8, fontSize: 12 }}>
                <span style={{
                  color: inv.status === 'completed' ? '#10b981' : inv.status === 'failed' ? '#ef4444' : '#d97706',
                  fontWeight: 600,
                }}>{inv.status}</span>
                <span style={{ color: '#6b7280' }}>
                  {inv.created_at ? new Date(inv.created_at).toLocaleTimeString() : ''}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* ── Right: Detail view ── */}
        <div style={{ background: '#1a2332', borderRadius: 10, padding: 20, minHeight: 400 }}>
          {!selected && (
            <div style={{ color: '#6b7280', fontSize: 14, marginTop: 60, textAlign: 'center' }}>
              Select an investigation to view details
            </div>
          )}

          {selected && detailLoading && (
            <p style={{ color: '#6b7280' }}>Loading investigation…</p>
          )}

          {selected && !detailLoading && detail && (
            <>
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <h3 style={{ margin: 0, fontSize: 14, fontFamily: 'monospace', color: '#93c5fd' }}>{detail.id}</h3>
                  <RoutingBadge routing={detail.action_routing} />
                </div>
                <StageProgress currentStage={detail.stage} status={detail.status} />
                <div style={{ marginBottom: 8 }}>
                  <span style={labelStyle}>Confidence</span>
                  <ConfidenceBar value={detail.confidence} />
                </div>
                {detail.recommended_action && (
                  <div>
                    <span style={labelStyle}>Recommended Action</span>
                    <code style={{ background: '#111827', padding: '2px 8px', borderRadius: 4,
                                   color: '#fbbf24', fontSize: 13 }}>
                      {detail.recommended_action}
                    </code>
                  </div>
                )}
              </div>

              {/* Tab bar */}
              <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: '1px solid #374151', paddingBottom: 8 }}>
                {TABS.map(t => (
                  <button key={t} style={tabStyle(activeTab === t)} onClick={() => setActiveTab(t)}>
                    {t.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>

              {/* Evidence */}
              {activeTab === 'evidence' && (
                <div>
                  {detail.evidence ? (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                      {[
                        ['Incident Type', detail.evidence.incident_type],
                        ['CPU', `${(detail.evidence.cpu || 0).toFixed(1)}%`],
                        ['Memory', `${(detail.evidence.memory || 0).toFixed(1)}%`],
                        ['Disk', `${(detail.evidence.disk || 0).toFixed(1)}%`],
                        ['Load Avg 1m', detail.evidence.load_avg_1m ?? 'N/A'],
                        ['Swap', detail.evidence.swap_percent != null ? `${detail.evidence.swap_percent.toFixed(1)}%` : 'N/A'],
                        ['Active Connections', detail.evidence.net_established ?? 'N/A'],
                        ['Recent Actions', detail.evidence.recent_action_count ?? 0],
                      ].map(([k, v]) => (
                        <div key={k} style={{ background: '#111827', borderRadius: 6, padding: '8px 12px' }}>
                          <div style={labelStyle}>{k}</div>
                          <div style={{ fontWeight: 600, color: '#e5e7eb' }}>{String(v)}</div>
                        </div>
                      ))}
                    </div>
                  ) : <p style={{ color: '#6b7280' }}>No evidence collected.</p>}

                  {detail.evidence?.top_cpu_processes?.length > 0 && (
                    <div style={{ marginTop: 16, ...sectionStyle }}>
                      <span style={labelStyle}>Top CPU Processes</span>
                      {detail.evidence.top_cpu_processes.slice(0, 3).map((p, i) => (
                        <div key={i} style={{ fontSize: 12, color: '#9ca3af', marginBottom: 2 }}>
                          {p.name} — {(p.cpu_percent || 0).toFixed(1)}% cpu
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Historical Matches */}
              {activeTab === 'history' && (
                <div>
                  {(detail.similar_incidents || []).length === 0
                    ? <p style={{ color: '#6b7280', fontSize: 13 }}>No similar incidents in memory yet.</p>
                    : (detail.similar_incidents || []).map((m, i) => <SimilarCard key={i} match={m} />)
                  }
                </div>
              )}

              {/* Hypotheses */}
              {activeTab === 'hypotheses' && (
                <HypothesisList hypotheses={detail.hypotheses} />
              )}

              {/* Root Cause */}
              {activeTab === 'root_cause' && (
                <div>
                  {detail.root_cause ? (
                    <>
                      <div style={sectionStyle}>
                        <span style={labelStyle}>Root Cause</span>
                        <p style={{ margin: 0, color: '#e5e7eb', fontSize: 14, lineHeight: 1.5 }}>
                          {detail.root_cause.root_cause}
                        </p>
                      </div>
                      {detail.root_cause.reasoning_steps?.length > 0 && (
                        <div style={sectionStyle}>
                          <span style={labelStyle}>Reasoning Steps</span>
                          <ol style={{ paddingLeft: 16, margin: 0 }}>
                            {detail.root_cause.reasoning_steps.map((s, i) => (
                              <li key={i} style={{ fontSize: 13, color: '#d1d5db', marginBottom: 4 }}>{s}</li>
                            ))}
                          </ol>
                        </div>
                      )}
                      {detail.root_cause.supporting_evidence?.length > 0 && (
                        <div style={sectionStyle}>
                          <span style={labelStyle}>Supporting Evidence</span>
                          <ul style={{ paddingLeft: 16, margin: 0 }}>
                            {detail.root_cause.supporting_evidence.map((e, i) => (
                              <li key={i} style={{ fontSize: 13, color: '#9ca3af', marginBottom: 2 }}>{e}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {detail.root_cause.historical_matches?.length > 0 && (
                        <div style={sectionStyle}>
                          <span style={labelStyle}>Historical References</span>
                          <ul style={{ paddingLeft: 16, margin: 0 }}>
                            {detail.root_cause.historical_matches.map((h, i) => (
                              <li key={i} style={{ fontSize: 13, color: '#6ee7b7', marginBottom: 2 }}>{h}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  ) : <p style={{ color: '#6b7280' }}>Root cause analysis not available.</p>}
                </div>
              )}

              {/* Timeline */}
              {activeTab === 'timeline' && (
                <Timeline events={detail.timeline} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
