import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import { Link } from 'react-router-dom';

export default function Login() {
  const { login, loading } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('employee');
  const [error, setError] = useState('');
  const [health, setHealth] = useState({ status: 'checking' });
  const [openReg, setOpenReg] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [h, cfg] = await Promise.all([
          apiService.checkHealth(),
          apiService.getConfig().catch(() => ({}))
        ]);
        if (!cancelled) {
          setHealth(h || { status: 'offline' });
          setOpenReg(!!cfg?.open_registration);
        }
      } catch {
        if (!cancelled) setHealth({ status: 'offline' });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const res = await login(email, password, role);
    if (!res.ok) setError(res.error || 'Login failed');
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
        <div className="hidden md:block">
          <div className="relative overflow-hidden rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
            <div className="absolute -top-20 -left-20 w-80 h-80 bg-blue-100 rounded-full blur-3xl opacity-70" />
            <div className="absolute -bottom-20 -right-16 w-80 h-80 bg-emerald-100 rounded-full blur-3xl opacity-70" />
            <div className="relative">
              <h2 className="text-3xl font-bold text-gray-900">AIOps Bot</h2>
              <p className="mt-3 text-gray-600">Real-time system insights, AI-driven diagnostics, and proactive remediation — all in one sleek dashboard.</p>
              <ul className="mt-6 space-y-3 text-gray-700">
                <li>• Live metrics via SSE/polling</li>
                <li>• AI assistant with streaming</li>
                <li>• Alerts, Security, Analytics</li>
                <li>• Admin and Employee roles with real auth</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="relative">
          <div className="absolute inset-0 -z-10 bg-gradient-to-br from-blue-50 to-emerald-50 rounded-3xl blur-xl" />
          <div className="relative bg-white border border-gray-200 rounded-2xl shadow-sm p-8">
            <div className="mb-6">
              <h1 className="text-2xl font-semibold text-gray-900">Welcome back</h1>
              <p className="text-gray-600">Sign in to continue to your dashboard</p>
              <div className="mt-2 inline-flex items-center gap-2 text-xs">
                <span className={`inline-block w-2 h-2 rounded-full ${health.status==='ok'?'bg-green-500':health.status==='checking'?'bg-yellow-400':'bg-red-500'}`}></span>
                <span className="text-gray-600">Backend: {health.status==='ok'?'healthy':health.status}</span>
              </div>
            </div>

            {error && (
              <div className="mb-4 rounded-md border border-red-200 bg-red-50 text-red-700 px-3 py-2 text-sm">{error}</div>
            )}

            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Email</label>
                <input
                  type="email"
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Password</label>
                <input
                  type="password"
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Role</label>
                <div className="mt-1 grid grid-cols-2 gap-2">
                  {['employee', 'admin'].map((r) => (
                    <button
                      type="button"
                      key={r}
                      onClick={() => setRole(r)}
                      className={`px-3 py-2 rounded-md border text-sm ${
                        role === r
                          ? 'border-blue-600 bg-blue-50 text-blue-700'
                          : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {r === 'admin' ? 'Admin' : 'Employee'}
                    </button>
                  ))}
                </div>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-4 py-2 font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
              >
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </form>

            <div className="mt-3 text-sm text-gray-600">
              {openReg ? (
                <span>
                  Don’t have an account?{' '}
                  <Link to="/register" className="text-blue-700 hover:underline">Create one</Link>
                </span>
              ) : (
                <span>
                  Self‑registration is disabled. Ask your admin for an invite.
                </span>
              )}
            </div>

            <p className="mt-4 text-xs text-gray-500">
              Use your registered credentials. Admin access unlocks system actions; contact your admin if you need access.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
