// Development proxy — routes ALL backend traffic through the Node/Express server (port 3002).
// Uses pathRewrite to restore the path prefix that Express strips when using app.use('/prefix', ...).
// Node internally proxies Flask-bound paths (/auth, /chat, etc.) to Flask:5000 or FastAPI:5001.

const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  const NODE_TARGET = process.env.REACT_APP_NODE_URL || 'http://localhost:3002';

  // Restores the path prefix Express strips, then proxies to Node.
  // e.g. app.use('/api', ...) → Express gives proxy '/system', rewrite adds '/api' → '/api/system'
  const p = (prefix, extra) => createProxyMiddleware({
    target: NODE_TARGET,
    changeOrigin: true,
    pathRewrite: { '^': prefix },
    logLevel: 'warn',
    ...extra,
  });

  // Node-native API endpoints
  app.use('/api',           p('/api'));
  app.use('/metrics',       p('/metrics'));
  app.use('/events',        p('/events'));
  app.use('/connect.ps1',   p('/connect.ps1'));

  // Socket.IO — ws:true required for WebSocket upgrade handshake
  app.use('/socket.io',     p('/socket.io', { ws: true }));

  // Auth (FastAPI :5001 via Node)
  app.use('/auth',          p('/auth'));

  // Flask-bound paths (proxied Node → Flask:5000)
  app.use('/chat',                  p('/chat'));
  app.use('/analyze',               p('/analyze'));
  app.use('/anomalies',             p('/anomalies'));
  app.use('/ai-health',             p('/ai-health'));
  app.use('/health',                p('/health'));
  app.use('/system-health',         p('/system-health'));
  app.use('/performance',           p('/performance'));
  app.use('/predictive-analytics',  p('/predictive-analytics'));
  app.use('/ai',                    p('/ai'));
  app.use('/actions',               p('/actions'));
  app.use('/integrations',          p('/integrations'));
  app.use('/agents',                p('/agents'));
  app.use('/devices',               p('/devices'));
  app.use('/company-stats',         p('/company-stats'));
  app.use('/jobs',                  p('/jobs'));
  app.use('/users',                 p('/users'));
  app.use('/security',              p('/security'));
  app.use('/dashboard-snapshot',    p('/dashboard-snapshot'));
};

