import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldOff } from 'lucide-react';

export default function Forbidden() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full bg-white border border-gray-200 rounded-2xl shadow-sm p-8 text-center">
        <div className="flex justify-center mb-4"><ShieldOff size={64} className="text-red-500" /></div>
        <h1 className="text-2xl font-semibold text-gray-900">Access denied</h1>
        <p className="text-gray-600 mt-2">You don't have permission to view this page.</p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Link to="/dashboard" className="inline-flex items-center justify-center rounded-md bg-blue-600 text-white px-4 py-2 text-sm hover:bg-blue-700">Go to Dashboard</Link>
          <Link to="/assistant" className="inline-flex items-center justify-center rounded-md bg-gray-100 text-gray-800 px-4 py-2 text-sm hover:bg-gray-200 border border-gray-300">Ask Assistant</Link>
        </div>
      </div>
    </div>
  );
}
