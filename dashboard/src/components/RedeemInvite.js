import React, { useState } from 'react';
import { authApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

export default function RedeemInvite() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ token: '', email: '', password: '', name: '' });
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await authApi.redeemInvite(form);
      toast.success('Welcome! Your account is ready.');
      // If you want to auto-login after redeem, we already receive token; store and redirect
      if (res?.token && res?.user) {
        localStorage.setItem('aiops:token', res.token);
        localStorage.setItem('aiops:user', JSON.stringify(res.user));
        if (res.refresh_token) localStorage.setItem('aiops:refresh', res.refresh_token);
        navigate('/dashboard', { replace: true });
        return;
      }
      navigate('/login', { replace: true });
    } catch (e2) {
      toast.error(e2?.response?.data?.error || e2.message || 'Redeem failed');
    } finally {
      setBusy(false);
    }
  };

  if (isAuthenticated) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full bg-white border border-gray-200 rounded-2xl shadow-sm p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">Redeem Invite</h1>
        <p className="text-gray-600 mb-4">Paste the invite token you received from your admin and set your account credentials.</p>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Invite Token</label>
            <input type="text" className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" required value={form.token} onChange={(e)=>setForm(f=>({...f,token:e.target.value}))} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Email</label>
            <input type="email" className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" required value={form.email} onChange={(e)=>setForm(f=>({...f,email:e.target.value}))} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Password</label>
            <input type="password" className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" required value={form.password} onChange={(e)=>setForm(f=>({...f,password:e.target.value}))} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input type="text" className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.name} onChange={(e)=>setForm(f=>({...f,name:e.target.value}))} />
          </div>
          <button type="submit" disabled={busy} className="w-full inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-4 py-2 font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60">{busy?'Redeeming…':'Redeem'}</button>
        </form>
      </div>
    </div>
  );
}
