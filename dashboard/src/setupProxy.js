// Development proxy — CRA dev server routes directly to FastAPI services.
// No Node/Express layer. All backend calls go through this proxy.

const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  const authTarget = 'http://localhost:5001';
  const coreTarget = 'http://localhost:8000';

  // Auth routes → FastAPI Auth :5001
  app.use(createProxyMiddleware({
    pathFilter: ['/auth', '/users', '/stream'],
    target: authTarget, changeOrigin: true, logLevel: 'warn',
  }));

  // Core API routes → FastAPI Core :8000
  app.use(createProxyMiddleware({
    pathFilter: [
      '/api/v1', '/api/orgs', '/orgs', '/agents', '/alerts',
      '/remediation', '/ingest', '/agent', '/health',
    ],
    target: coreTarget, changeOrigin: true, logLevel: 'warn',
  }));
};
