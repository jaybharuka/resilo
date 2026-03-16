import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api';

export default function Security() {
  const [anomalies, setAnomalies] = useState([]);
  const [aiHealth, setAiHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [anom, health] = await Promise.all([
          apiService.getAlerts(),
          apiService.getAiInsights()
        ]);
        if (!mounted) return;
        setAnomalies(anom || []);
        setAiHealth(health || null);
      } catch (e) {
        setError('Failed to load security data');
      } finally {
        setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold">Security</h2>
      {loading && <div className="text-gray-600">Loading…</div>}
      {error && <div className="text-red-600">{error}</div>}
      {!loading && !error && (
        <>
          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="text-lg font-semibold mb-3">AI Health</h3>
            {aiHealth ? (
              <div className="flex gap-6 text-sm">
                <div>Status: <span className="font-medium capitalize">{aiHealth.status}</span></div>
                <div>Accuracy: <span className="font-medium">{aiHealth.accuracy}%</span></div>
                <div>Response: <span className="font-medium">{aiHealth.response_time}ms</span></div>
              </div>
            ) : (
              <div className="text-gray-600">No AI health data.</div>
            )}
          </section>
          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="text-lg font-semibold mb-3">Recent Anomalies</h3>
            <div className="space-y-2">
              {anomalies.length === 0 && <div className="text-gray-600">No anomalies detected.</div>}
              {anomalies.map((a) => (
                <div key={a.id} className="border border-gray-200 rounded-lg p-3 flex items-center justify-between">
                  <div>
                    <div className="text-sm text-gray-500 uppercase">{a.type}</div>
                    <div className="font-medium">{a.description}</div>
                    <div className="text-xs text-gray-500">{new Date(a.timestamp).toLocaleString()}</div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full border ${a.severity === 'error' ? 'border-red-300 text-red-700 bg-red-50' : a.severity === 'warning' ? 'border-yellow-300 text-yellow-700 bg-yellow-50' : 'border-gray-300 text-gray-700 bg-gray-50'}`}>
                    {a.severity}
                  </span>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}