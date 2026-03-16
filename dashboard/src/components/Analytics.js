import React, { useEffect, useState } from 'react';
import { apiService, systemApi } from '../services/api';

export default function Analytics() {
  const [perf, setPerf] = useState([]);
  const [pred, setPred] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [range, setRange] = useState('1hour');

  const load = async (tf = range) => {
    setLoading(true);
    setError('');
    try {
      const [series, preds] = await Promise.all([
        apiService.getPerformanceData(),
        systemApi.getPredictive(tf)
      ]);
      setPerf(series || []);
      setPred(preds || []);
    } catch (e) {
      setError('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    (async () => { if (mounted) await load(range); })();
    const onGlobal = () => load(range);
    try { window.addEventListener('aiops:refresh', onGlobal); } catch {}
    return () => { mounted = false; };
  }, [range]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Analytics</h2>
        <div className="text-sm">
          <label className="mr-2 text-gray-600">Timeframe</label>
          <select value={range} onChange={(e) => setRange(e.target.value)} className="border border-gray-300 rounded-md px-2 py-1">
            <option value="1hour">Last hour</option>
            <option value="6hours">Last 6 hours</option>
            <option value="24hours">Last 24 hours</option>
          </select>
        </div>
      </div>
      {loading && <div className="text-gray-600">Loading…</div>}
      {error && <div className="text-red-600">{error}</div>}
      {!loading && !error && (
        <>
          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="text-lg font-semibold mb-3">Predictive Insights</h3>
            <div className="grid sm:grid-cols-3 gap-3">
              {pred.map((p, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-3">
                  <div className="text-sm text-gray-500 uppercase">{p.metric}</div>
                  <div className="font-medium">{p.prediction}</div>
                  <div className="text-xs text-gray-500">Confidence: {p.confidence}%</div>
                </div>
              ))}
            </div>
          </section>
          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="text-lg font-semibold mb-3">Recent Performance (24 points)</h3>
            <div className="grid sm:grid-cols-3 gap-3 text-sm text-gray-700">
              <div>Avg CPU: {Math.round(perf.reduce((s,x)=>s+(x.cpu||0),0)/Math.max(1,perf.length))}%</div>
              <div>Avg Memory: {Math.round(perf.reduce((s,x)=>s+(x.memory||0),0)/Math.max(1,perf.length))}%</div>
              <div>Avg Disk: {Math.round(perf.reduce((s,x)=>s+(x.disk||0),0)/Math.max(1,perf.length))}%</div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}