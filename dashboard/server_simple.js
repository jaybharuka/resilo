const express = require('express');
const app = express();
const HOST = '127.0.0.1';
const PORT = 4000;
app.get('/ping', (req,res) => {
  res.json({ ok: true, pid: process.pid, uptime: process.uptime() });
});
app.listen(PORT, HOST, () => {
  console.log(`Simple test server listening http://${HOST}:${PORT} (pid ${process.pid})`);
});
