# Resilo — Design Document

## Visual Identity
- **Theme**: Dark, terminal-inspired. Black/charcoal backgrounds, amber (#F59E0B) as primary accent, teal for live/healthy states, red for critical.
- **Typography**: Monospace for metrics and labels (`MONO`), clean sans-serif for body (`UI`), bold display font for headings (`DISPLAY`).
- **Tone**: Dense, data-forward. No whitespace padding. Every pixel earns its place.

---

## Color Palette
```
Background:  #0A0A0A  (bg)
Surface 1:   #111111  (cards)
Surface 2:   #1A1A1A  (inner panels)
Border:      #2A2A2A
Amber:       #F59E0B  (primary CTA, AI highlights)
Teal:        #2DD4BF  (live/healthy)
Red:         #EF4444  (critical/offline)
Text 1:      #F5F5F5  (primary)
Text 3:      #6B7280  (secondary labels)
Text 4:      #374151  (muted)
```

---

## Layout

### Global Shell
```
┌─────────────────────────────────────────────────┐
│  Topbar: Logo | ConnectionStatus | User | Role   │
├──────────┬──────────────────────────────────────┤
│          │  HealthRibbon (backend / SSE status)  │
│ Sidebar  ├──────────────────────────────────────┤
│  Nav     │                                      │
│  Links   │         Page Content                 │
│          │                                      │
└──────────┴──────────────────────────────────────┘
```

### Sidebar Navigation
```
MAIN
  Dashboard
  Insights
  AI Assistant
  Analytics
  Infra Hub

OPERATIONS
  Alerts
  Remediation
  Notifications
  Remote Agents   ← primary feature
  Security
  Settings
```

---

## Key Screens

### Remote Agents List
- Status filter pills (LIVE / OFFLINE / PENDING / TOTAL) — clickable
- Agent cards in a responsive grid (1 → 2 → 3 cols)
- Each card: status dot + pulse animation, label, last-seen, CPU/MEM/DISK mini bars
- Click card → AgentDetail full-page view

### Agent Detail View
- Back button → returns to list
- **Metrics Panel**: live CPU, Memory, Disk gauges
- **AI DECISIONS Panel**: table of LangChain decisions — timestamp, action, confidence, status badge (`queued` / `dry_run` / `needs_review`)
- **Activity Timeline**: chronological log — alert created → AI analyzed → command queued → executed → resolved
- **Learning Feedback**: success/failure rate per action type
- **Execution Mode Selector**: DRY RUN / MANUAL APPROVAL / AUTO SAFE toggle

### Dashboard (Home)
- Org-wide health summary
- Recent alert feed
- Top agents by CPU/memory
- AI action history across all agents

### AI Assistant
- Chat interface
- Aware of current org's alerts and agents
- Can answer "why is agent X offline" style questions

---

## Component Architecture
```
App.js
├── AppShell
│   ├── Topbar (ConnectionStatus, IncidentDeclare)
│   ├── HealthRibbon
│   ├── Sidebar
│   └── <Routes>
│       ├── Dashboard
│       ├── RemoteAgents
│       │   ├── AgentCard
│       │   └── AgentDetail
│       │       ├── MetricsPanel
│       │       ├── AiDecisionsPanel
│       │       ├── ActivityTimeline
│       │       └── LearningFeedback
│       ├── Alerts
│       ├── AIAssistant
│       └── Settings
```

---

## UX Principles
1. **Zero clicks to understand** — agent status is obvious at a glance
2. **AI is transparent** — every decision shows reasoning + confidence score
3. **Never block the user** — all AI actions are async background tasks
4. **Dense but not cluttered** — monospace labels, tight padding, no decorative elements
5. **Feedback on everything** — spinners on refresh, pulse on LIVE agents, animated status dots
