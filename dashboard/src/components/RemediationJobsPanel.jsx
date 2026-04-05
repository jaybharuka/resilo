import React, { useCallback, useEffect, useState } from 'react';
import { Activity, Bot, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiService } from '../services/api';

const C = {
  surface: 'rgb(22,20,16)',
  surface2: 'rgb(31,29,24)',
  border: 'rgba(42,40,32,1)',
  amber: '#F59E0B',
  amberAlpha: 'rgba(245,158,11,0.1)',
  teal: '#2DD4BF',
  red: '#F87171',
  text1: 'rgb(245,240,232)',
  text2: 'rgb(168,159,140)',
  text3: 'rgb(107,99,87)',
  mono: "'IBM Plex Mono', monospace",
};

function fmt(ts) {
  if (!ts) return '?';
  const d = new Date(ts);
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function statusStyle(status) {
  switch (status) {
    case 'running': return { fg: C.teal, bg: 'rgba(45,212,191,0.1)' };
    case 'success': return { fg: '#4ADE80', bg: 'rgba(74,222,128,0.1)' };
    case 'failed': return { fg: C.red, bg: 'rgba(248,113,113,0.12)' };
    case 'cancelled': return { fg: C.text3, bg: 'rgba(107,99,87,0.12)' };
    default: return { fg: C.amber, bg: C.amberAlpha };
  }
}

function StatusPill({ status }) {
  const s = statusStyle(status);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 8px', borderRadius: 999,
      color: s.fg, background: s.bg,
      fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', fontFamily: C.mono,
    }}>
      {String(status || 'pending').toUpperCase()}
    </span>
  );
}

function LogRow({ log, isLast }) {
  const color = log.level === 'error' ? C.red : log.level === 'warning' ? C.amber : C.teal;
  return (
    <div style={{ display: 'flex', gap: 10, padding: '10px 12px', borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
      <div style={{ width: 8, height: 8, borderRadius: '50%', marginTop: 5, background: color, flexShrink: 0 }} />
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: C.text3, fontFamily: C.mono }}>{fmt(log.timestamp)}</span>
          <span style={{ fontSize: 9, color: C.text3, fontFamily: C.mono, letterSpacing: '0.08em' }}>{log.event}</span>
          <span style={{ fontSize: 9, color: C.text3, fontFamily: C.mono }}>{log.source}</span>
        </div>
        <p style={{ margin: '4px 0 0', fontSize: 12, color: C.text1, lineHeight: 1.45 }}>{log.message}</p>
      </div>
    </div>
  );
}

export default function RemediationJobsPanel() {
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [selectedLogs, setSelectedLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);

  const refreshJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiService.getRemediationJobs();
      setJobs(Array.isArray(data) ? data : []);
      setSelectedJob(prev => {
        if (!prev) return prev;
        return (Array.isArray(data) ? data : []).find(job => job.id === prev.id) || prev;
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadJob = useCallback(async (jobId) => {
    if (jobId == null) return;
    setSelectedJobId(jobId);
    setDetailLoading(true);
    try {
      const detail = await apiService.getRemediationJob(jobId);
      setSelectedJob(detail?.job || null);
      setSelectedLogs(Array.isArray(detail?.logs) ? detail.logs : []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to load remediation job');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshJobs();
    const timer = setInterval(refreshJobs, 15000);
    return () => clearInterval(timer);
  }, [refreshJobs]);

  async function retryJob(jobId) {
    setActionLoading(`retry:${jobId}`);
    try {
      const res = await apiService.retryRemediationJob(jobId);
      toast.success(res?.message || 'Job re-queued');
      await refreshJobs();
      await loadJob(jobId);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to retry job');
    } finally {
      setActionLoading(null);
    }
  }

  async function cancelJob(jobId) {
    setActionLoading(`cancel:${jobId}`);
    try {
      const res = await apiService.cancelRemediationJob(jobId);
      toast.success(res?.message || 'Job cancelled');
      await refreshJobs();
      await loadJob(jobId);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to cancel job');
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <section style={{ background: C.surface, border: `1px solid rgba(245,158,11,0.18)`, borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '13px 18px', borderBottom: `1px solid ${C.border}` }}>
        <span style={{ color: C.amber }}><Activity size={14} /></span>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text1 }}>Remediation Jobs</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: C.text3, fontFamily: C.mono }}>{loading ? 'LOADING' : `${jobs.length}`}</span>
      </div>

      {jobs.length === 0 ? (
        <div style={{ padding: '40px 24px', textAlign: 'center' }}>
          <Bot size={26} style={{ color: C.amber, margin: '0 auto 10px', opacity: 0.5 }} />
          <p style={{ fontSize: 13, color: C.text1, fontWeight: 600, margin: '0 0 4px' }}>No remediation jobs queued</p>
          <p style={{ fontSize: 11, color: C.text3, margin: 0 }}>Triggered remediation jobs will appear here with retry and cancel controls.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(300px, 0.85fr)' }}>
          <div style={{ overflowX: 'auto', borderRight: `1px solid ${C.border}` }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                  {['ID', 'Playbook', 'Status', 'Attempts', 'Updated', ''].map((label) => (
                    <th key={label} style={{ padding: '10px 14px', fontSize: 9, fontWeight: 700, letterSpacing: '0.09em', color: C.text3, textAlign: 'left', fontFamily: C.mono, whiteSpace: 'nowrap' }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map((job, index) => {
                  const isSelected = selectedJobId === job.id;
                  const isLast = index === jobs.length - 1;
                  return (
                    <tr
                      key={job.id}
                      onClick={() => loadJob(job.id)}
                      style={{ cursor: 'pointer', background: isSelected ? 'rgba(245,158,11,0.05)' : 'transparent' }}
                      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = C.surface2; }}
                      onMouseLeave={e => { e.currentTarget.style.background = isSelected ? 'rgba(245,158,11,0.05)' : 'transparent'; }}
                    >
                      <td style={{ padding: '10px 14px', borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
                        <span style={{ fontSize: 11, color: C.text1, fontFamily: C.mono }}>{job.id}</span>
                      </td>
                      <td style={{ padding: '10px 14px', borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
                        <div style={{ fontSize: 12, color: C.text1 }}>{job.playbook_type}</div>
                        <div style={{ fontSize: 10, color: C.text3, fontFamily: C.mono, marginTop: 3 }}>{job.alert_title || job.alert_id || 'No alert link'}</div>
                      </td>
                      <td style={{ padding: '10px 14px', borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}><StatusPill status={job.status} /></td>
                      <td style={{ padding: '10px 14px', borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
                        <span style={{ fontSize: 11, color: C.text2, fontFamily: C.mono }}>{job.attempts}/{job.max_retries}</span>
                      </td>
                      <td style={{ padding: '10px 14px', borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
                        <span style={{ fontSize: 11, color: C.text3, fontFamily: C.mono }}>{fmt(job.updated_at)}</span>
                      </td>
                      <td style={{ padding: '10px 14px', borderBottom: isLast ? 'none' : `1px solid ${C.border}` }}>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); loadJob(job.id); }}
                          style={{
                            fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
                            padding: '5px 9px', borderRadius: 6,
                            border: `1px solid ${C.border}`, background: C.surface,
                            color: C.text1, cursor: 'pointer',
                          }}
                        >
                          VIEW
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div style={{ padding: 16, minHeight: 260 }}>
            {!selectedJob ? (
              <div style={{ padding: '28px 0', textAlign: 'center' }}>
                <ShieldCheck size={26} style={{ color: C.teal, margin: '0 auto 10px', opacity: 0.6 }} />
                <p style={{ fontSize: 13, color: C.text1, fontWeight: 600, margin: '0 0 4px' }}>Select a job to inspect</p>
                <p style={{ fontSize: 11, color: C.text3, margin: 0 }}>View synthetic logs, retry, and cancel actions for each remediation job.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 14, fontWeight: 700, color: C.text1 }}>Job #{selectedJob.id}</span>
                      <StatusPill status={selectedJob.status} />
                    </div>
                    <p style={{ fontSize: 11, color: C.text3, margin: '6px 0 0', fontFamily: C.mono }}>
                      {selectedJob.playbook_type} {selectedJob.alert_title || selectedJob.alert_id ? `? ${selectedJob.alert_title || selectedJob.alert_id}` : ''}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      onClick={() => retryJob(selectedJob.id)}
                      disabled={actionLoading === `retry:${selectedJob.id}` || selectedJob.status === 'running'}
                      style={{
                        padding: '7px 10px', borderRadius: 7, border: `1px solid ${C.border}`,
                        background: 'transparent', color: C.text1,
                        cursor: actionLoading === `retry:${selectedJob.id}` || selectedJob.status === 'running' ? 'not-allowed' : 'pointer',
                        opacity: actionLoading === `retry:${selectedJob.id}` || selectedJob.status === 'running' ? 0.5 : 1,
                      }}
                    >
                      {actionLoading === `retry:${selectedJob.id}` ? 'Retrying?' : 'Retry'}
                    </button>
                    <button
                      type="button"
                      onClick={() => cancelJob(selectedJob.id)}
                      disabled={actionLoading === `cancel:${selectedJob.id}` || selectedJob.status === 'running'}
                      style={{
                        padding: '7px 10px', borderRadius: 7, border: `1px solid rgba(248,113,113,0.25)`,
                        background: 'rgba(248,113,113,0.08)', color: C.red,
                        cursor: actionLoading === `cancel:${selectedJob.id}` || selectedJob.status === 'running' ? 'not-allowed' : 'pointer',
                        opacity: actionLoading === `cancel:${selectedJob.id}` || selectedJob.status === 'running' ? 0.5 : 1,
                      }}
                    >
                      {actionLoading === `cancel:${selectedJob.id}` ? 'Cancelling?' : 'Cancel'}
                    </button>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                  <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 10, padding: '14px 18px' }}>
                    <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.09em', color: C.text3, fontFamily: C.mono, margin: '0 0 6px' }}>ATTEMPTS</p>
                    <p style={{ fontSize: 20, fontWeight: 700, color: C.text1, margin: 0 }}>{selectedJob.attempts}/{selectedJob.max_retries}</p>
                  </div>
                  <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 10, padding: '14px 18px' }}>
                    <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.09em', color: C.text3, fontFamily: C.mono, margin: '0 0 6px' }}>UPDATED</p>
                    <p style={{ fontSize: 20, fontWeight: 700, color: C.text1, margin: 0 }}>{fmt(selectedJob.updated_at)}</p>
                  </div>
                </div>

                <div style={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderBottom: `1px solid ${C.border}` }}>
                    <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: C.text3, fontFamily: C.mono }}>JOB LOGS</span>
                    {detailLoading && <span style={{ fontSize: 10, color: C.text3, fontFamily: C.mono }}>Loading?</span>}
                  </div>
                  <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                    {selectedLogs.length === 0 ? (
                      <div style={{ padding: '24px 12px', textAlign: 'center' }}>
                        <p style={{ fontSize: 12, color: C.text3, margin: 0 }}>No logs available for this job yet.</p>
                      </div>
                    ) : (
                      selectedLogs.map((log, index) => (
                        <LogRow key={`${log.timestamp}-${index}`} log={log} isLast={index === selectedLogs.length - 1} />
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
