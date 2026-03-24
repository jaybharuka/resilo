export default function AlertsTable({ alerts }) {
  const getSeverityBadge = (severity) => {
    const styles = {
      critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
      warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
      info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
    };
    return (
      <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${styles[severity] || styles.info}`}>
        {severity || 'info'}
      </span>
    );
  };

  if (!alerts || alerts.length === 0) {
    return <div className="p-4 text-center text-gray-500">No active alerts.</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm whitespace-nowrap">
        <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 dark:text-gray-400">
          <tr>
            <th className="px-6 py-3 font-medium">Severity</th>
            <th className="px-6 py-3 font-medium">System</th>
            <th className="px-6 py-3 font-medium">Message</th>
            <th className="px-6 py-3 font-medium">Time</th>
            <th className="px-6 py-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
          {alerts.map((alert) => (
            <tr key={alert.id || Math.random()} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer">
              <td className="px-6 py-4">{getSeverityBadge(alert.severity)}</td>
              <td className="px-6 py-4 font-medium text-gray-900 dark:text-gray-200">{alert.system || 'Unknown'}</td>
              <td className="px-6 py-4 text-gray-600 dark:text-gray-400">{alert.message || alert.title}</td>
              <td className="px-6 py-4 text-gray-500">{alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString() : '-'}</td>
              <td className="px-6 py-4">
                <span className="text-gray-500 capitalize">{alert.status || 'open'}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}