import React, { useEffect, useState } from 'react';
import { authApi, apiService } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

export default function Register() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: '', password: '', name: '', role: 'employee' });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const cfg = await apiService.getConfig();
      if (!mounted) return;
      setOpen(!!cfg?.open_registration);
    })();
    if (isAuthenticated) navigate('/dashboard', { replace: true });
    return () => { mounted = false; };
  }, [isAuthenticated, navigate]);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!open) return;
    setBusy(true);
    try {
      await authApi.register(form);
      toast.success('Registered. You can now sign in.');
      navigate('/login', { replace: true });
    } catch (e) {
      const msg = e?.response?.data?.error || e.message;
      toast.error(msg || 'Registration failed');
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <div className="p-6">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-xl font-semibold text-gray-900">Registration Closed</h2>
          <p className="text-gray-600 mt-2">Self-registration is disabled. Please contact your administrator for an invite.</p>
          <Link to="/login" className="inline-block mt-3 text-blue-700 hover:underline">Back to login</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full bg-white border border-gray-200 rounded-2xl shadow-sm p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">Create your account</h1>
        <p className="text-gray-600 mb-4">Open registration is enabled on this server.</p>
        <form onSubmit={onSubmit} className="space-y-4">
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
          <button type="submit" disabled={busy} className="w-full inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-4 py-2 font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60">{busy?'Creating…':'Create account'}</button>
        </form>
        <div className="mt-3 text-sm text-gray-600">Already have an account? <Link to="/login" className="text-blue-700 hover:underline">Sign in</Link></div>
      </div>
    </div>
  );
}
