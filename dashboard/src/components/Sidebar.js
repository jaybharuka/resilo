import React from 'react';
import { NavLink } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';
import { useAuth } from '../context/AuthContext';
import { LayoutDashboard, Monitor, Bot, MessageSquare, BellRing, Shield, TrendingUp, Settings } from 'lucide-react';

const Sidebar = () => {
  const { isAuthenticated, logout, role } = useAuth();
  const menuItems = [
    { to: '/dashboard', icon: <LayoutDashboard size={18} />, label: 'Dashboard' },
    { to: '/systems', icon: <Monitor size={18} />, label: 'Systems' },
    { to: '/ai-insights', icon: <Bot size={18} />, label: 'AI Insights' },
    { to: '/assistant', icon: <MessageSquare size={18} />, label: 'AI Assistant' },
  ];
  const extraItems = [
    { to: '/alerts', icon: <BellRing size={18} />, label: 'Alerts' },
    ...(role === 'admin' ? [{ to: '/security', icon: <Shield size={18} />, label: 'Security' }] : []),
    { to: '/analytics', icon: <TrendingUp size={18} />, label: 'Analytics' },
    { to: '/settings', icon: <Settings size={18} />, label: 'Settings' },
  ];

  return (
    <div className="w-64 bg-white border-r border-gray-200 p-6 min-h-screen">
      <div className="mb-8">
        <NavLink to="/dashboard" className="block">
          <h1 className="text-2xl font-bold text-gray-900">AIOps Bot</h1>
          <p className="text-gray-500 text-sm">Real-time monitoring</p>
        </NavLink>
      </div>

      {isAuthenticated ? (
      <nav className="space-y-2">
        {menuItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `w-full flex items-center space-x-3 px-4 py-3 rounded-md transition-colors duration-150 ${
                isActive
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <span className="flex items-center">{item.icon}</span>
            <span className="font-medium">{item.label}</span>
          </NavLink>
        ))}
        <div className="mt-6 mb-2 border-t border-gray-100"></div>
        {extraItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `w-full flex items-center space-x-3 px-4 py-3 rounded-md transition-colors duration-150 ${
                isActive
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <span className="flex items-center">{item.icon}</span>
            <span className="font-medium">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      ) : (
        <div className="text-sm text-gray-600">Please sign in to access the dashboard.</div>
      )}

      <div className="mt-8 pt-8 border-t border-gray-200">
        <div className="flex items-center space-x-3 text-gray-600">
          <div className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse"></div>
          <span className="text-sm">System Active</span>
        </div>

        <div className="mt-6">
          <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">Theme</div>
          <ThemeToggle className="w-full" />
          {isAuthenticated && (
            <button onClick={logout} className="mt-4 w-full text-sm text-gray-700 border border-gray-200 rounded-md px-3 py-2 hover:bg-gray-50">Logout</button>
          )}
        </div>
      </div>
    </div>
  );
};

export default Sidebar;