# Benchmarking & Evaluation

## Purpose

The benchmark suite answers the question: **"Is the investigation engine getting better or worse over time?"**

It runs offline, against pre-built scenario fixtures, using real LLM API calls against known ground-truth answers.

---

## Quick Start

```bash
# Static mode — 7 scenarios, ~2 min
python scripts/benchmark_engine.py

# A/B mode — each scenario run twice (static + planner), ~5 min
python scripts/benchmark_engine.py --ab

# Single scenario
python scripts/benchmark_engine.py --scenario db_pool_exhaustion

# Custom output path
python scripts/benchmark_engine.py --ab --out benchmark_results/my_run.json
```

Requires: `GEMINI_API_KEY` set in `.env`

---

## Scenarios

Seven fixtures in `test_scenarios/`:

| File | Incident Type | Key Challenge |
|---|---|---|
| `cpu_spike.json` | cpu | Single runaway process vs noisy neighbours |
| `memory_leak.json` | memory | Slow leak vs sudden OOM |
| `db_pool_exhaustion.json` | database | Pool exhaustion vs slow queries |
| `disk_full.json` | disk | Log accumulation vs database growth |
| `network_timeout.json` | network | DNS failure vs connection pool starvation |
| `nginx_crash.json` | service | SSL expiry vs config error |
| `oom_kill.json` | memory | OOM kill vs memory pressure |

Each fixture contains: `metrics`, `logs`, `context`, `alert`, `expected_root_cause` (keywords), `expected_action`, `acceptable_actions`.

---

## Metrics Measured

### Accuracy
- **Top-1 Accuracy** — correct root cause keyword appears in position-0 hypothesis or RCA text
- **Top-3 Accuracy** — correct keyword appears anywhere in top-3 hypotheses
- **Action Accuracy** — recommended action is in `acceptable_actions` set
- **Action Exact** — recommended action exactly matches `expected_action`

### Calibration
- **Avg Confidence** — mean confidence across all scenarios
- **Conf When Correct** — mean confidence on scenarios where Top-1 is correct
- **Conf When Incorrect** — mean confidence on scenarios where Top-1 is wrong
- **Calibration Gap** — `conf_correct - conf_incorrect` (positive = well-calibrated)

### Cost
- **Avg LLM Calls** — mean calls per investigation (static: typically 2, planner: 4–6)
- **Avg Est. Tokens** — estimated tokens consumed (chars/4)
- **Avg Investigation Time** — wall-clock seconds per scenario

---

## A/B Mode — Static vs Planner

`--ab` runs each scenario twice:

1. **Static mode** — evidence collection only (Stages 1, 2, 3, 4, 5)
2. **Planner mode** — adds Stage 1.5 (up to 4 adaptive collection LLM calls)

Output comparison table:
```
  Scenario                     Static Top1     Planner Top1    ΔCalls   ΔTime
  cpu_spike                    ✓ (0.91)        ✓ (0.94)        +3       +11.2s
  db_pool_exhaustion           ✓ (0.88)        ✓ (0.94)        +2       +8.1s
  network_timeout              ✗ (0.61)        ✓ (0.82)        +4       +14.7s
```

Use this to justify or reject the planner: if delta accuracy < 5pp with 3+ extra calls, static mode is more cost-efficient.

---

## Leaderboard

Every run (static or A/B) appends to `benchmark_results/leaderboard.json`:

```json
[
  {
    "commit": "744424f",
    "timestamp": 1748866000,
    "run_date": "2026-06-02 09:00 UTC",
    "top1_accuracy": 0.714,
    "action_accuracy": 0.857,
    "calibration_gap": 0.183,
    "avg_llm_calls": 2.0,
    "avg_time_s": 8.2,
    "planner_top1_accuracy": 0.857,
    "planner_delta": 0.143,
    "planner_extra_calls": 3.4
  }
]
```

Accessible live via: `GET /investigations/benchmark/trends`

Visualised on the Evaluation Dashboard at `/eval`.

---

## Confusion Matrix

Run with `--confusion` to generate a confusion matrix across all scenarios:

```bash
python scripts/benchmark_engine.py --confusion
```

Output:
```
  CONFUSION MATRIX (Actual → Predicted)
  ══════════════════════════════════════════
  cpu           → cpu:         3   memory: 0   disk: 0
  memory        → memory:      2   oom_kill: 1
  db_pool       → db_pool:     3
  disk          → disk:        2   database: 1
  network       → network:     2   service: 1
  nginx_crash   → service:     3
  oom_kill      → oom_kill:    2   memory: 1
```

Tells you exactly where the model confuses incident types — highest-value areas for prompt engineering improvements.

---

## Demo Runs

Pre-computed investigation results in `demo_runs/`:

| File | Scenario | Confidence | All 4 sources used |
|---|---|---|---|
| `cpu_spike_success.json` | CPU runaway | 91% | Logs + Context |
| `db_pool_exhaustion_success.json` | Postgres pool exhaustion | 94% | All 4 |
| `nginx_crash_success.json` | SSL cert expiry | 96% | Logs + Context |

Served via `GET /api/demo-runs` — used by the Evaluation Dashboard for reproducible demos without live API calls.
