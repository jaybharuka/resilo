import React, { useEffect, useState } from 'react';
import { authApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

export default function Invites() {
  const { role } = useAuth();
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);
  const [email, setEmail] = useState('');
  const [ttl, setTtl] = useState(7*24*3600);
  const [invRole, setInvRole] = useState('employee');

  useEffect(() => {
    if (role !== 'admin') {
      toast('Invites are admin-only');
    }
  }, [role]);

  const create = async () => {
    setBusy(true);
    try {
      const res = await authApi.createInvite({ role: invRole, email: email || undefined, ttl_seconds: ttl });
      setLast(res);
      await navigator.clipboard.writeText(res.token);
      toast.success('Invite created and token copied');
    } catch (e) {
      toast.error(e?.response?.data?.error || e.message || 'Failed to create invite');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-6">
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-xl font-semibold text-gray-900">Invites</h2>
        <p className="text-gray-600 text-sm">Generate one-time invite tokens to onboard users without enabling open registration.</p>
        <div className="grid sm:grid-cols-2 gap-4 mt-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Email (optional)</label>
            <input value={email} onChange={(e)=>setEmail(e.target.value)} type="email" className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="user@company.com" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Role</label>
            <select value={invRole} onChange={(e)=>setInvRole(e.target.value)} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none">
              <option value="employee">Employee</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">TTL (seconds)</label>
            <input value={ttl} onChange={(e)=>setTtl(Number(e.target.value)||0)} type="number" min={3600} step={3600} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none" />
          </div>
        </div>
        <div className="mt-3">
          <button onClick={create} disabled={busy || role !== 'admin'} className="inline-flex items-center justify-center rounded-md bg-indigo-600 text-white px-4 py-2 font-medium hover:bg-indigo-700 disabled:opacity-60">{busy?'Creating…':'Create Invite'}</button>
        </div>
        {last && (
          <div className="mt-4 border rounded-lg bg-gray-50 p-3 text-xs">
            <div><strong>Token:</strong> <code className="break-all">{last.token}</code></div>
            <div className="mt-1">Role: {last.role} • Expires: {new Date(last.expires_at).toLocaleString()}</div>
          </div>
        )}
      </div>
    </div>
  );
}
