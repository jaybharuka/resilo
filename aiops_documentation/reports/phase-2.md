# 🚀 RESILO — Phase 2: Core Journey (Weeks 4–5)

## 🎯 Goal

Make the product work **end-to-end reliably**:

> User logs in → sees live metrics → asks AI → gets response

This loop must work **100% consistently** before moving forward.

---

## 🧠 Tech Context (IMPORTANT for Copilot)

Project stack:

* FastAPI (backend)
* React (frontend)
* PostgreSQL + TimescaleDB
* Docker Compose
* Auth: JWT + bcrypt + Alembic
* AI: Gemini API

---

## ⚠️ Critical Rule

Do NOT start Phase 3 until:

* Real-time pipeline works
* AI fallback works
* Only FastAPI remains (no Flask / legacy APIs)

---

# 🧩 PHASE 2 ISSUES (ALL INCLUDED)

---

## 🔴 REAL-TIME PIPELINE (DO FIRST — STRICT ORDER)

### #9 — WebSocket Backend

**Problem**
Frontend already has Socket.IO client, backend missing.

**Task**

* Add WebSocket endpoint in FastAPI
* Stream metrics in real-time

**Why**
Current system is fake real-time (10s polling)

---

### #12 — Fix Socket.IO Import (2-line win)

**Task**

* Add missing import in `Dashboard.js`

**Impact**
Instant perceived upgrade to real-time UX

---

### #13 — SSE Streaming Endpoints

**Task**

* Add:

  * `GET /stream/metrics`
  * `GET /stream/alerts`
* Add 30s heartbeat

---

### #14 — Remove Polling

**Task**

* Remove `setInterval`
* Replace with WebSocket listeners

**Why**
Polling + WebSocket = duplicate data + bugs

---

### #15 — WebSocket Backpressure

**Task**

* Add per-client queue
* Limit size (bounded queue)
* Drop oldest messages
* 5s send timeout

---

## 🤖 AI RESILIENCE (DO BEFORE DEMO)

### #33 — Gemini Fallback + Timeout

**Task**

* Wrap all AI calls:

  * try/except
  * 10s timeout
* Return fallback response

**Expected behavior**
UI shows:

> “AI unavailable” instead of freezing

---

### #34 — AI Caching

**Task**

* Cache responses (TTL = 60s)

**Why**

* Reduce API cost
* Avoid rate limits
* Improve latency

---

## 🧱 CODEBASE STABILIZATION

### #39 — Consolidate APIs (CRITICAL)

**Problem**
3 parallel APIs:

* Flask
* FastAPI
* api_server.py

**Task**

* Move everything → FastAPI
* Delete Flask + legacy server

---

### #40 — Remove Global State

**Problem**
Globals used for request state → race conditions

**Task**

* Replace with FastAPI Dependency Injection

---

### #41 — Remove Dead Code

**Task**

* Delete ~400 lines unused code in `api_server.py`

---

### #43 — Standardize Patterns

**Fix inconsistencies**

* Error handling → 1 pattern
* Logging → 1 format
* Response structure → 1 schema

---

### #35 — Graceful Shutdown

**Task**

* Handle SIGTERM
* Stop new requests
* Finish in-flight requests
* Then shutdown

---

### #44 — React Error Boundaries

**Task**

* Wrap major components
* Show fallback UI on crash

---

# 🔁 EXECUTION ORDER (VERY IMPORTANT)

## Step 1 — Real-time pipeline

1. #9 WebSocket backend
2. #12 Socket import
3. #13 SSE endpoints
4. #14 Remove polling
5. #15 Backpressure

---

## Step 2 — AI stability

6. #33 Gemini fallback
7. #34 Caching

---

## Step 3 — Code cleanup

8. #39 API consolidation
9. #40 Remove globals
10. #41 Dead code removal
11. #43 Standardization
12. #35 Graceful shutdown
13. #44 Error boundaries

---

# ✅ DEFINITION OF DONE

Phase 2 is COMPLETE only if:

* WebSocket connects in browser DevTools
* Metrics update without refresh
* No polling anywhere
* Killing Gemini shows fallback message
* No Flask code exists
* No global mutable state
* Only FastAPI routes exist
* pytest coverage ≥ 70%

---

# 🤖 HOW TO USE WITH COPILOT

For EACH issue, paste:

---

## Prompt Template

```
Context:
This is a FastAPI + React + PostgreSQL + Docker project.
We are in Phase 2 (Core Journey).

Task:
[PASTE ISSUE HERE]

Instructions:
1. First: Architect (explain approach, no code)
2. Second: Developer (exact file changes)
3. Third: Reviewer (commands to verify)
```

---

# ⚡ QUICK WINS (DO EARLY)

* #12 → 2 minutes → huge UX improvement
* #33 → prevents demo failure
* #39 → removes future confusion

---

# 🚨 COMMON PITFALLS

* ❌ Mixing polling + WebSockets
* ❌ Keeping Flask “temporarily”
* ❌ Ignoring backpressure (will crash later)
* ❌ No AI timeout → UI freeze

---

# 🧠 FINAL NOTE

Phase 2 = **first real product moment**

If this phase is done right:
👉 You can demo confidently
👉 You can onboard first users
👉 You stop being “just a project”

---
