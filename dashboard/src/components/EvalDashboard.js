import React, { useEffect, useState, useCallback } from 'react';
import { coreAxios } from '../services/api';
import { TrendingUp, TrendingDown, Minus, RefreshCw, GitCommit, Clock, Zap, Brain, FileText, Cpu } from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

const BG      = 'rgb(12,11,9)';
const CARD    = 'rgba(30,27,22,0.95)';
const BORDER  = 'rgba(245,158,11,0.12)';
const AMBER   = '#F59E0B';
const GREEN   = '#10B981';
const RED     = '#EF4444';
const MUTED   = '#4A443D';
const TEXT    = '#F5F0E8';
const SUBTEXT = '#8B7D6B';

// ── helpers ──────────────────────────────────────────────────────────────────

function pct(n) {
  if (n == null) return '—';
  return `${Math.round(n * 100)}%`;
}
function num(n, decimals = 1) {
  if (n == null) return '—';
  return typeof n === 'number' ? n.toFixed(decimals) : n;
}
function delta(v, positive_is_good = true) {
  if (v == null) return null;
  const good = positive_is_good ? v > 0 : v < 0;
  const neutral = Math.abs(v) < 0.01;
  if (neutral) return { icon: <Minus size={11} />, color: MUTED, label: '±0' };
  return {
    icon: v > 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />,
    color: good ? GREEN : RED,
    label: `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}pp`,
  };
}

// ── sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color = TEXT, icon }) {
  return (
    <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {icon && <span style={{ color: AMBER }}>{icon}</span>}
        <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.08em', color: MUTED, textTransform: 'uppercase' }}>{label}</span>
      </div>
      <span style={{ ...UI, fontSize: 26, fontWeight: 700, color, lineHeight: 1 }}>{value}</span>
      {sub && <span style={{ ...MONO, fontSize: 11, color: SUBTEXT }}>{sub}</span>}
    </div>
  );
}

function ContribBar({ label, rate, count, color = AMBER }) {
  const w = Math.round((rate || 0) * 100);
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ ...UI, fontSize: 13, color: TEXT }}>{label}</span>
        <span style={{ ...MONO, fontSize: 12, color: AMBER }}>{pct(rate)} <span style={{ color: MUTED }}>({count} invs)</span></span>
      </div>
      <div style={{ background: 'rgba(245,158,11,0.08)', borderRadius: 4, height: 6, overflow: 'hidden' }}>
        <div style={{ width: `${w}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.6s ease' }} />
      </div>
    </div>
  );
}

function LeaderboardRow({ entry, isLatest }) {
  const d = delta(entry.planner_delta);
  return (
    <tr style={{ borderBottom: `1px solid ${BORDER}`, background: isLatest ? 'rgba(245,158,11,0.04)' : 'transparent' }}>
      <td style={{ padding: '8px 12px', ...MONO, fontSize: 12, color: AMBER }}>{entry.commit}</td>
      <td style={{ padding: '8px 12px', ...MONO, fontSize: 11, color: MUTED }}>{entry.run_date || '—'}</td>
      <td style={{ padding: '8px 12px', ...UI, fontSize: 13, color: TEXT, textAlign: 'center' }}>
        {pct(entry.top1_accuracy)}
      </td>
      <td style={{ padding: '8px 12px', ...UI, fontSize: 13, color: entry.planner_top1_accuracy ? GREEN : MUTED, textAlign: 'center' }}>
        {entry.planner_top1_accuracy ? pct(entry.planner_top1_accuracy) : '—'}
      </td>
      <td style={{ padding: '8px 12px', textAlign: 'center' }}>
        {d ? (
          <span style={{ ...MONO, fontSize: 11, color: d.color, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
            {d.icon} {d.label}
          </span>
        ) : <span style={{ color: MUTED }}>—</span>}
      </td>
      <td style={{ padding: '8px 12px', ...MONO, fontSize: 12, color: MUTED, textAlign: 'center' }}>
        {num(entry.avg_llm_calls)}
      </td>
      <td style={{ padding: '8px 12px', ...MONO, fontSize: 12, color: MUTED, textAlign: 'center' }}>
        {entry.avg_time_s != null ? `${num(entry.avg_time_s)}s` : '—'}
      </td>
      {isLatest && (
        <td style={{ padding: '8px 12px' }}>
          <span style={{ ...MONO, fontSize: 10, color: AMBER, border: `1px solid ${AMBER}`, borderRadius: 4, padding: '2px 6px' }}>LATEST</span>
        </td>
      )}
      {!isLatest && <td />}
    </tr>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function EvalDashboard() {
  const [trends,   setTrends]   = useState(null);
  const [stats,    setStats]    = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [lastFetch, setLastFetch] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tRes, sRes] = await Promise.all([
        coreAxios.get('/investigations/benchmark/trends'),
        coreAxios.get('/investigations/stats?window_hours=168'),
      ]);
      setTrends(tRes.data);
      setStats(sRes.data);
      setLastFetch(new Date());
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Failed to load evaluation data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const latest    = trends?.latest || {};
  const entries   = trends?.entries || [];
  const contrib   = stats?.evidence_contribution || {};
  const memory    = stats?.memory_usefulness || {};
  const accuracy  = stats?.accuracy || {};
  const semRet    = stats?.semantic_retrieval || {};

  const noData = !loading && entries.length === 0;

  return (
    <div style={{ background: BG, minHeight: '100vh', padding: '0 0 40px 0', ...UI }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ ...UI, fontSize: 22, fontWeight: 700, color: TEXT, margin: 0 }}>Evaluation Dashboard</h1>
          <p style={{ ...MONO, fontSize: 11, color: MUTED, marginTop: 4, letterSpacing: '0.06em' }}>
            BENCHMARK TRENDS · EVIDENCE QUALITY · COST TRACKING
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {lastFetch && (
            <span style={{ ...MONO, fontSize: 10, color: MUTED }}>
              fetched {lastFetch.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            style={{ background: 'rgba(245,158,11,0.1)', border: `1px solid ${AMBER}`, borderRadius: 7, padding: '6px 14px', color: AMBER, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, ...MONO, fontSize: 12 }}
          >
            <RefreshCw size={12} style={{ animation: loading ? 'spin 0.7s linear infinite' : 'none' }} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '12px 16px', color: RED, ...MONO, fontSize: 12, marginBottom: 24 }}>
          {error}
        </div>
      )}

      {noData && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '32px 24px', textAlign: 'center', marginBottom: 24 }}>
          <p style={{ color: MUTED, ...MONO, fontSize: 13 }}>No benchmark runs yet.</p>
          <p style={{ color: SUBTEXT, ...MONO, fontSize: 12, marginTop: 8 }}>
            Run: <span style={{ color: AMBER }}>python scripts/benchmark_engine.py --ab</span>
          </p>
        </div>
      )}

      {/* Latest run KPIs */}
      {entries.length > 0 && (
        <>
          <div style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: MUTED, marginBottom: 12, textTransform: 'uppercase' }}>
            Latest benchmark · commit {latest.commit}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 14, marginBottom: 32 }}>
            <StatCard label="Static Accuracy"  value={pct(latest.top1_accuracy)}          icon={<Cpu size={14} />} color={AMBER} />
            <StatCard label="Planner Accuracy" value={pct(latest.planner_top1_accuracy)}  icon={<Brain size={14} />} color={latest.planner_top1_accuracy ? GREEN : MUTED} />
            <StatCard label="Planner Delta"
              value={latest.planner_delta != null ? `${latest.planner_delta > 0 ? '+' : ''}${(latest.planner_delta * 100).toFixed(1)}pp` : '—'}
              color={latest.planner_delta > 0 ? GREEN : latest.planner_delta < 0 ? RED : MUTED}
              icon={<TrendingUp size={14} />}
              sub="vs static mode"
            />
            <StatCard label="Avg LLM Calls"   value={num(latest.avg_llm_calls)}          icon={<Zap size={14} />} sub="static mode" />
            <StatCard label="Avg Latency"      value={latest.avg_time_s != null ? `${num(latest.avg_time_s)}s` : '—'} icon={<Clock size={14} />} sub="per investigation" />
            <StatCard label="Calibration Gap"  value={num(latest.calibration_gap, 3)}     icon={<TrendingUp size={14} />}
              sub="positive = well-calibrated"
              color={latest.calibration_gap > 0 ? GREEN : RED}
            />
          </div>
        </>
      )}

      {/* Evidence contribution */}
      {contrib.investigations_scored > 0 && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '20px 24px', marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
            <FileText size={14} color={AMBER} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.08em', color: MUTED, textTransform: 'uppercase' }}>Evidence Contribution</span>
            <span style={{ ...MONO, fontSize: 10, color: MUTED, marginLeft: 'auto' }}>{contrib.investigations_scored} investigations scored</span>
          </div>
          <ContribBar label="Logs helped RCA"             rate={contrib.logs_helped_rate}    count={contrib.logs_helped_count}    color={AMBER} />
          <ContribBar label="Semantic memory helped RCA"  rate={contrib.memory_helped_rate}  count={contrib.memory_helped_count}  color='#8B5CF6' />
          <ContribBar label="Dynamic context helped RCA"  rate={contrib.context_helped_rate} count={contrib.context_helped_count} color='#06B6D4' />
          <ContribBar label="Evidence planner helped RCA" rate={contrib.planner_helped_rate} count={contrib.planner_helped_count} color={GREEN} />
          <p style={{ ...MONO, fontSize: 10, color: MUTED, marginTop: 10 }}>
            Contribution is scored heuristically — logs/context must appear in RCA text; memory must be referenced in historical_matches.
          </p>
        </div>
      )}

      {/* Live investigation stats */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 14, marginBottom: 32 }}>
          <StatCard label="Total Investigations" value={stats.total_investigations ?? '—'}     icon={<Brain size={14} />} />
          <StatCard label="Overall Accuracy"     value={pct(accuracy.overall)}                 icon={<TrendingUp size={14} />} color={accuracy.overall > 0.7 ? GREEN : AMBER} sub={`${accuracy.total_feedback} feedback rows`} />
          <StatCard label="Memory Entries"       value={stats.memory_entries ?? '—'}           icon={<FileText size={14} />} sub={`${pct(stats.embedding_coverage)} embedded`} />
          <StatCard label="Memory Usefulness"    value={pct(memory.usefulness_rate)}           icon={<Brain size={14} />} color='#8B5CF6' sub={`${memory.used_in_reasoning || 0} used in reasoning`} />
          <StatCard label="Avg Semantic Hits"    value={num(semRet.avg_hits)}                  icon={<Zap size={14} />} sub={`sim ${num(semRet.avg_similarity, 3)}`} />
          <StatCard label="Fix Success Rate"     value={pct(stats.successful_fix_rate)}        icon={<TrendingUp size={14} />} color={stats.successful_fix_rate > 0.6 ? GREEN : AMBER} />
        </div>
      )}

      {/* Leaderboard table */}
      {entries.length > 0 && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, overflow: 'hidden', marginBottom: 24 }}>
          <div style={{ padding: '16px 20px', borderBottom: `1px solid ${BORDER}`, display: 'flex', alignItems: 'center', gap: 8 }}>
            <GitCommit size={14} color={AMBER} />
            <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.08em', color: MUTED, textTransform: 'uppercase' }}>Benchmark Leaderboard</span>
            <span style={{ ...MONO, fontSize: 10, color: MUTED, marginLeft: 'auto' }}>{entries.length} run{entries.length !== 1 ? 's' : ''}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${BORDER}` }}>
                  {['Commit', 'Date', 'Static Top-1', 'Planner Top-1', 'Planner Δ', 'Avg Calls', 'Avg Time', ''].map(h => (
                    <th key={h} style={{ padding: '8px 12px', ...MONO, fontSize: 10, color: MUTED, textAlign: h === 'Commit' || h === 'Date' ? 'left' : 'center', letterSpacing: '0.06em', textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...entries].reverse().map((e, i) => (
                  <LeaderboardRow key={e.commit + e.timestamp} entry={e} isLatest={i === 0} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* How to run note */}
      <div style={{ background: 'rgba(245,158,11,0.04)', border: `1px solid ${BORDER}`, borderRadius: 8, padding: '14px 18px' }}>
        <p style={{ ...MONO, fontSize: 11, color: MUTED, margin: 0 }}>
          To add a benchmark run: <span style={{ color: AMBER }}>python scripts/benchmark_engine.py --ab</span>
          &nbsp;&nbsp;·&nbsp;&nbsp;
          Single scenario: <span style={{ color: AMBER }}>--scenario db_pool_exhaustion</span>
          &nbsp;&nbsp;·&nbsp;&nbsp;
          Requires: <span style={{ color: AMBER }}>GEMINI_API_KEY</span>
        </p>
      </div>

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
