import React from 'react';
import AlertsPanel from './AlertsPanel';

export default function Alerts() {
  return (
  <div className="p-6 space-y-4">
      <div className="mb-4">
        <h2 className="text-2xl font-bold">Alerts</h2>
        <p className="text-gray-600">View and manage system alerts and notifications.</p>
      </div>
      <AlertsPanel />
    </div>
  );
}