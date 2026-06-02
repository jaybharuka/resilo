# Investigation Engine — Stage-by-Stage Flow

## Entry Point

`run_investigation(alert, agent_id, org_id, call_llm_fn, db, use_evidence_planner=False)`

Called as a FastAPI background task when an alert is created. The `call_llm_fn` parameter is wrapped by `LLMCallTracker` at entry to instrument all downstream LLM calls.

---

## Stage 0 — Initialization

```python
inv_id  = uuid4()          # unique investigation ID
tracker = LLMCallTracker(call_llm_fn)   # wraps every LLM call
timeline = []              # ordered stage events for audit trail
```

A row is immediately inserted into `investigations` with `status=running` so the dashboard shows a live indicator.

---

## Stage 1 — Evidence Collection

**Sources collected in parallel (asyncio.gather, 10s timeout each):**

| Collector | Data |
|---|---|
| Log collector | Last N log lines, error extraction, top_errors list |
| Context collector | Incident-type-specific: process_tree, pg_connections, oom_history, disk_largest_dirs, net_open_ports, service_state, systemd_journal |

Context collectors are selected based on `incident_type`:
- `cpu` → process_tree, scheduler_pressure
- `memory` → memory_breakdown, oom_history
- `disk` → disk_largest_dirs, disk_inodes
- `database` → pg_connections, pg_long_queries, pg_lock_waits
- `network` → net_open_ports, net_connection_summary
- `service` → service_state, systemd_journal

Each collector is failure-isolated: a timeout or exception produces a `collection_note` but does not abort the investigation.

---

## Stage 1.5 — Evidence Planner (Optional)

Enabled via `use_evidence_planner=True`. Simulates a senior SRE's "what should I look at next?" reasoning.

```
Loop (max 4 iterations):
  LLM prompt: "Given current metrics + hypothesis + already-gathered evidence,
               are you confident enough, or what should you collect next?"
  Response: { confident_enough: bool, collector: str|null, reason: str }
  If confident_enough → break
  Else → run named collector, add to evidence
```

The planner adds 1–4 extra LLM calls but can surface evidence the static collectors missed. Its value is measured by the `--ab` benchmark flag.

---

## Stage 2 — Historical Analysis (Semantic Memory)

```python
similar = await MemoryStore.find_similar(
    org_id, incident_type, metrics_snapshot, top_k=5
)
```

- Converts current incident to an embedding vector
- Cosine similarity search via pgvector
- Returns top-5 past incidents with similarity scores
- Injects matching incidents as context into subsequent LLM prompts
- Telemetry recorded: `semantic_hits`, `avg_similarity`, `retrieval_time_ms`

---

## Stage 3 — Hypothesis Generation

**Input:** metrics, top processes, log errors, context evidence, historical matches

**LLM prompt asks for:** JSON array of `{cause, confidence, evidence[]}` sorted by confidence

**Output:** up to 5 `Hypothesis` objects

---

## Stage 4 — Root Cause Analysis

**Input:** hypotheses, all evidence, historical matches

**LLM prompt asks for:** single JSON object:
```json
{
  "root_cause": "...",
  "confidence": 0.0–1.0,
  "supporting_evidence": ["..."],
  "reasoning_steps": ["..."],
  "recommended_action": "...",
  "historical_matches": ["..."]
}
```

**Fallback:** if LLM call fails or returns unparseable JSON, a rule-based fallback fires (confidence=0.4, source=rule_fallback).

---

## Stage 5 — Action Routing

```python
routing = _route_action(confidence)
```

| Confidence | Routing |
|---|---|
| ≥ 0.85 | `auto_execute` |
| ≥ 0.60 | `manual_approval` |
| < 0.60 | `investigation_only` |

Additionally:
- `confidence < 0.75` → forced to `manual_approval` regardless of route
- Unknown actions → `investigation_only`

---

## Post-Investigation

After Stage 5, the engine:

1. **Scores evidence contribution** — heuristic, no extra LLM call
2. **Persists investigation** — all stages, cost, contribution to `investigations` table
3. **Saves incident memory** — adds to `incident_memory` for future semantic retrieval
4. **Returns `InvestigationResult`** — surfaced via API and SSE

---

## LLM Cost Tracking

`LLMCallTracker` wraps `call_llm_fn` and records per-call latency + estimates tokens as `len(prompt+response) / 4`. Summary stored in `investigations.llm_cost`:

```json
{
  "llm_calls": 4,
  "est_tokens": 3240,
  "total_llm_ms": 12840,
  "avg_llm_ms": 3210
}
```

---

## Evidence Contribution Scoring

After RCA, `_score_evidence_contribution()` heuristically determines which sources influenced the conclusion:

| Flag | Logic |
|---|---|
| `logs_helped` | 3-word log fingerprint found in RCA text; fallback: ≥3 errors AND conf ≥0.70 |
| `memory_helped` | `memories_used_in_reasoning > 0` |
| `context_helped` | context section key name in RCA text; fallback: sections present AND conf ≥0.75 |
| `planner_helped` | planner key present in context_evidence |

Aggregate rates visible in `/investigations/stats` → `evidence_contribution` and on the Evaluation Dashboard.
