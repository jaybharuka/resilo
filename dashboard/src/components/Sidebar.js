import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import {
  LayoutDashboard, Lightbulb, MessageSquare, BellRing,
  Shield, Settings, Wrench, Activity, Palette, LogOut,
  BarChart2, Bell, Layers
} from 'lucide-react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

const Sidebar = () => {
  const { isAuthenticated, logout, role } = useAuth();
  const { cycleTheme, theme } = useTheme();

  const primary = [
    { to: '/dashboard',   icon: <LayoutDashboard size={15} />, label: 'Dashboard' },
    { to: '/insights',    icon: <Lightbulb size={15} />,       label: 'Insights' },
    { to: '/assistant',   icon: <MessageSquare size={15} />,   label: 'AI Assistant' },
    { to: '/analytics',   icon: <BarChart2 size={15} />,       label: 'Analytics' },
    { to: '/infra', icon: <Layers size={15} />, label: role === 'admin' ? 'Infra Hub' : 'Devices' },
  ];
  const secondary = [
    { to: '/alerts',        icon: <BellRing size={15} />,  label: 'Alerts' },
    { to: '/remediation',   icon: <Wrench size={15} />,    label: 'Remediation' },
    { to: '/notifications', icon: <Bell size={15} />,      label: 'Notifications' },
    ...(role === 'admin' ? [
      { to: '/security', icon: <Shield size={15} />,  label: 'Security' },
    ] : []),
    { to: '/settings',      icon: <Settings size={15} />,  label: 'Settings' },
  ];

  const themeLabel = theme === 'dark' ? 'Ops Dark' : theme === 'high-contrast' ? 'High Contrast' : 'Light';

  const linkClass = ({ isActive }) =>
    isActive
      ? 'nav-item nav-active flex items-center gap-3 px-3 py-2 rounded-r-md text-sm font-medium'
      : 'nav-item flex items-center gap-3 px-3 py-2 rounded-r-md text-sm font-medium';

  const mutedText = { color: '#6B6357', ...UI };
  const dimText   = { color: '#4A443D', ...MONO, fontSize: '10px', letterSpacing: '0.12em' };

  return (
    <div className="sidebar-bg w-56 min-h-screen flex flex-col shrink-0">

      {/* Logo */}
      <div className="px-5 pt-6 pb-5" style={{ borderBottom: '1px solid rgba(245,158,11,0.1)' }}>
        <NavLink to="/dashboard" className="block">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
              style={{
                background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                boxShadow: '0 0 16px rgba(245,158,11,0.35)',
              }}
            >
              <Activity size={15} color="#0C0B09" />
            </div>
            <div>
              <p style={{ ...UI, fontSize: '14px', fontWeight: 600, color: '#F5F0E8', lineHeight: 1 }}>
                Resilo
              </p>
              <p style={{ ...MONO, fontSize: '9px', letterSpacing: '0.12em', color: '#4A443D', marginTop: '4px' }}>
                MONITORING
              </p>
            </div>
          </div>
        </NavLink>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto" style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
        {isAuthenticated ? (
          <>
            <p className="px-3 mb-2" style={dimText}>MAIN</p>
            {primary.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={linkClass}
                style={({ isActive }) => ({
                  color: isActive ? '#F59E0B' : '#6B6357',
                  ...UI,
                })}
              >
                <span className="shrink-0">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}

            <p className="px-3 mt-4 mb-2" style={dimText}>OPERATIONS</p>
            {secondary.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={linkClass}
                style={({ isActive }) => ({
                  color: isActive ? '#F59E0B' : '#6B6357',
                  ...UI,
                })}
              >
                <span className="shrink-0">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </>
        ) : (
          <p className="px-3 text-sm" style={mutedText}>Please sign in.</p>
        )}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 space-y-0.5" style={{ borderTop: '1px solid rgba(245,158,11,0.1)' }}>
        <div className="flex items-center gap-2 px-3 py-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse dot-healthy"
          />
          <span style={{ ...MONO, fontSize: '10px', letterSpacing: '0.1em', color: '#4A443D' }}>
            SYSTEM ACTIVE
          </span>
        </div>

        <button
          onClick={cycleTheme}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm nav-item"
          style={mutedText}
        >
          <Palette size={14} />
          <span style={UI}>{themeLabel}</span>
        </button>

        {isAuthenticated && (
          <button
            onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm nav-item"
            style={mutedText}
            onMouseEnter={e => { e.currentTarget.style.color = '#F87171'; }}
            onMouseLeave={e => { e.currentTarget.style.color = '#6B6357'; }}
          >
            <LogOut size={14} />
            <span style={UI}>Logout</span>
          </button>
        )}
      </div>

    </div>
  );
};

export default Sidebar;
