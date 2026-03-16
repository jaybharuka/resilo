# AIOps Dashboard

Realtime multi-page monitoring dashboard with streaming AI assistant.

## Prerequisites
- Node.js 18+
- Flask backend running at http://localhost:5000 with endpoints:
  - POST /chat (JSON) and optionally POST /chat/stream (SSE)
  - GET /system-health, /processes, /system-info, /anomalies, /predictive-analytics
  - Optional actions: /actions/* and /ai/*

## Setup
1. Install deps
```powershell
Set-Location -LiteralPath 'd:\AIOps Bot\dashboard'
npm install
```

2. Environment
- Copy `.env.example` to `.env.local` and tweak values as needed.
- Defaults assume Flask on port 5000 and Node socket server on 3001.

3. Run
- Start Node realtime server (sockets + REST proxy):
```powershell
npm run dev
```
- Start React app (in another terminal):
```powershell
npm start
```

4. Build
```powershell
npm run build
```

## Notes
- Streaming chat prefers SSE via `/chat/stream`; falls back to `/chat` with simulated streaming.
- Action buttons hit Flask first and fall back to Node proxy under `/api/actions/*` and `/api/ai/*`.
- Socket URL can be overridden with `REACT_APP_SOCKET_URL`.