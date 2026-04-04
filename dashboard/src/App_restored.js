import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [systemData, setSystemData] = useState({
    cpu: 92.2,
    memory: 97.2,
    storage: 4.6,
    network: 0.0,
    temperature: 0.0,
    systemLoad: 0.00,
    uptime: '1d 2h 38m',
    status: 'Online',
    alerts: 0
  });
  
  const [activeTab, setActiveTab] = useState('dashboard');
  const [lastUpdated, setLastUpdated] = useState(new Date().toLocaleTimeString());
  const [healthScore] = useState(98);

  useEffect(() => {
    setLastUpdated(new Date().toLocaleTimeString());
    return () => {};
  }, []);

  const menuItems = [
    { id: 'dashboard', icon: '📊', label: 'Dashboard' },
    { id: 'systems', icon: '🖥️', label: 'Systems' },
    { id: 'ai-insights', icon: '🧠', label: 'AI Insights' },
    { id: 'ai-assistant', icon: '🤖', label: 'AI Assistant' },
    { id: 'multi-role', icon: '👥', label: 'Multi-Role Portal' },
    { id: 'device-management', icon: '📱', label: 'Device Management' },
    { id: 'settings', icon: '⚙️', label: 'Settings' }
  ];

  const renderContent = () => {
    if (activeTab === 'dashboard') {
      return (
        <div className="dashboard-content">
          {/* Header Section */}
          <div className="content-header">
            <div className="header-left">
              <div className="header-icon">💻</div>
              <div className="header-info">
                <h1>System Dashboard</h1>
                <p>Real-time monitoring and management</p>
              </div>
            </div>
            <div className="header-right">
              <div className="notification-icon">🔔</div>
              <div className="user-profile">
                <div className="user-avatar">👤</div>
                <div className="user-info">
                  <div className="user-name">Admin User</div>
                  <div className="user-role">Administrator</div>
                </div>
              </div>
            </div>
          </div>

          {/* System Overview */}
          <div className="overview-section">
            <h2>System Overview</h2>
            <p>Real-time monitoring and analytics for your infrastructure</p>
            
            <div className="status-indicators">
              <div className="status-item">
                <span className="status-icon online">🟢</span>
                <span className="status-label">System Status</span>
                <span className="status-value">Online</span>
              </div>
              <div className="status-item">
                <span className="status-icon">⚡</span>
                <span className="status-label">Uptime</span>
                <span className="status-value">{systemData.uptime}</span>
              </div>
              <div className="status-item">
                <span className="status-icon">📊</span>
                <span className="status-label">Active Alerts</span>
                <span className="status-value">{systemData.alerts}</span>
              </div>
            </div>
          </div>

          {/* System Metrics */}
          <div className="metrics-section">
            <div className="metrics-header">
              <h3>📊 System Metrics</h3>
              <span className="live-indicator">LIVE</span>
            </div>
            
            <div className="metrics-grid">
              <div className="metric-card cpu">
                <div className="metric-icon">💻</div>
                <div className="metric-info">
                  <div className="metric-label">CPU USAGE</div>
                  <div className="metric-value">{systemData.cpu}%</div>
                  <div className="metric-description">Processor utilization</div>
                </div>
                <div className="metric-progress">
                  <div className="progress-bar">
                    <div className="progress-fill cpu-fill" style={{width: `${systemData.cpu}%`}}></div>
                  </div>
                </div>
              </div>

              <div className="metric-card memory">
                <div className="metric-icon">🟣</div>
                <div className="metric-info">
                  <div className="metric-label">MEMORY</div>
                  <div className="metric-value">{systemData.memory}%</div>
                  <div className="metric-description">RAM usage</div>
                </div>
                <div className="metric-progress">
                  <div className="progress-bar">
                    <div className="progress-fill memory-fill" style={{width: `${systemData.memory}%`}}></div>
                  </div>
                </div>
              </div>

              <div className="metric-card storage">
                <div className="metric-icon">💾</div>
                <div className="metric-info">
                  <div className="metric-label">STORAGE</div>
                  <div className="metric-value">{systemData.storage}%</div>
                  <div className="metric-description">Disk utilization</div>
                </div>
                <div className="metric-progress">
                  <div className="progress-bar">
                    <div className="progress-fill storage-fill" style={{width: `${systemData.storage}%`}}></div>
                  </div>
                </div>
              </div>

              <div className="metric-card network">
                <div className="metric-icon">🌐</div>
                <div className="metric-info">
                  <div className="metric-label">NETWORK</div>
                  <div className="metric-value">{systemData.network} MB/s</div>
                  <div className="metric-description">I/O throughput</div>
                </div>
                <div className="metric-progress">
                  <div className="progress-bar">
                    <div className="progress-fill network-fill" style={{width: `${Math.max(systemData.network * 10, 5)}%`}}></div>
                  </div>
                </div>
              </div>

              <div className="metric-card temperature">
                <div className="metric-icon">🔗</div>
                <div className="metric-info">
                  <div className="metric-label">TEMPERATURE</div>
                  <div className="metric-value">{systemData.temperature}°C</div>
                  <div className="metric-description">System temperature</div>
                </div>
                <div className="metric-progress">
                  <div className="progress-bar">
                    <div className="progress-fill temp-fill" style={{width: `${Math.max(systemData.temperature * 2, 5)}%`}}></div>
                  </div>
                </div>
              </div>

              <div className="metric-card system-load">
                <div className="metric-icon">⚡</div>
                <div className="metric-info">
                  <div className="metric-label">SYSTEM LOAD</div>
                  <div className="metric-value">{systemData.systemLoad}</div>
                  <div className="metric-description">Average load</div>
                </div>
                <div className="metric-progress">
                  <div className="progress-bar">
                    <div className="progress-fill load-fill" style={{width: `${Math.max(systemData.systemLoad * 20, 5)}%`}}></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* System Health */}
          <div className="health-section">
            <div className="health-header">
              <h3>📋 System Health</h3>
              <div className="health-score-display">
                <span className="health-score">{healthScore}</span>
                <span className="health-label">Health Score</span>
              </div>
            </div>
            
            <div className="performance-metrics">
              <h4>Performance Metrics</h4>
              <div className="metric-row">
                <span className="metric-name">RESPONSE TIME</span>
              </div>
            </div>
          </div>
        </div>
      );
    }
    
    return (
      <div className="tab-content">
        <h2>{menuItems.find(item => item.id === activeTab)?.label || 'Dashboard'}</h2>
        <p>Content for {activeTab} tab</p>
      </div>
    );
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <div className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <div className="brand-icon">🚀</div>
            <div className="brand-info">
              <div className="brand-name">AIOps</div>
              <div className="brand-subtitle">Dashboard</div>
            </div>
          </div>
        </div>

        <div className="system-status">
          <div className="status-indicator online"></div>
          <div className="status-info">
            <div className="status-title">System Online</div>
            <div className="status-time">Updated: {lastUpdated}</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {menuItems.map(item => (
            <button
              key={item.id}
              className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
              onClick={() => setActiveTab(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content */}
      <div className="main-content">
        {renderContent()}
      </div>
    </div>
  );
}

export default App;