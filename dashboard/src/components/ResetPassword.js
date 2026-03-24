import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Activity, Eye, EyeOff } from 'lucide-react';
import { confirmPasswordReset } from 'firebase/auth';
import { auth } from '../firebase';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  // Firebase appends ?oobCode=<code> when you configure a custom action URL
  const oobCode = searchParams.get('oobCode') || '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      await confirmPasswordReset(auth, oobCode, password);
      setDone(true);
    } catch (err) {
      const code = err?.code || '';
      if (code === 'auth/expired-action-code' || code === 'auth/invalid-action-code') {
        setError('This reset link has expired or already been used. Please request a new one.');
      } else {
        setError(err?.message || 'Reset failed. The link may have expired.');
      }
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500';

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-indigo-600 rounded-xl mb-4">
            <Activity size={22} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Set new password</h1>
          <p className="text-slate-500 text-sm mt-1">
            {done ? 'Your password has been updated' : 'Choose a strong password'}
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
          {!oobCode ? (
            <div className="text-center space-y-3">
              <p className="text-sm text-red-600">
                Invalid reset link. Please request a new one.
              </p>
              <Link to="/forgot-password" className="text-sm text-indigo-600 hover:underline">
                Request new reset link
              </Link>
            </div>
          ) : done ? (
            <div className="text-center space-y-4">
              <div className="w-12 h-12 bg-green-50 rounded-full flex items-center justify-center mx-auto">
                <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-sm text-slate-700">Password updated successfully.</p>
              <Link
                to="/login"
                className="block w-full text-center rounded-lg bg-indigo-600 text-white px-4 py-2.5 text-sm font-semibold hover:bg-indigo-700 transition-colors"
              >
                Sign in
              </Link>
            </div>
          ) : (
            <>
              {error && (
                <div className="mb-4 rounded-lg border border-red-200 bg-red-50 text-red-700 px-3 py-2 text-sm">
                  {error}
                </div>
              )}
              <form onSubmit={onSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700">New password</label>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      autoFocus
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Min. 8 characters"
                      className={`${inputClass} pr-10`}
                    />
                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700">Confirm password</label>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    placeholder="Repeat your password"
                    className={inputClass}
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-indigo-600 text-white px-4 py-2.5 text-sm font-semibold hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-60 transition-colors"
                >
                  {loading ? 'Updating…' : 'Update password'}
                </button>
              </form>
            </>
          )}

          {!done && oobCode && (
            <p className="mt-6 text-xs text-slate-500 text-center">
              <Link to="/login" className="text-indigo-600 hover:underline font-medium">Back to sign in</Link>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
