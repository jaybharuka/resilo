// Development proxy configuration for Create React App
// This file is used only when running `npm start` (development server).
// It proxies frontend requests beginning with /api, /actions, /ai, and key backend paths
// directly to the Flask backend so you can run without the Node/Express wrapper during dev.

const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  const target = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5000';
  const common = {
    target,
    changeOrigin: true,
    logLevel: 'warn',
  };

  app.use('/health', createProxyMiddleware(common));
  app.use('/system-health', createProxyMiddleware(common));
  app.use('/processes', createProxyMiddleware(common));
  app.use('/system-info', createProxyMiddleware(common));
  app.use('/performance', createProxyMiddleware(common));
  app.use('/predictive-analytics', createProxyMiddleware(common));
  app.use('/anomalies', createProxyMiddleware(common));
  app.use('/chat', createProxyMiddleware(common));
  app.use('/analyze', createProxyMiddleware(common));
  app.use('/ai', createProxyMiddleware(common));
  app.use('/actions', createProxyMiddleware(common));
  app.use('/integrations', createProxyMiddleware(common));
  app.use('/auth', createProxyMiddleware(common));
};
