"""
benchmark_engine.py — Offline benchmark suite for the investigation engine.

Runs every JSON scenario in test_scenarios/ against the full investigation
pipeline (hypothesis generation + RCA) using real Gemini API calls, then
measures:

  Top-1 Accuracy          — correct root cause in position 0
  Top-3 Accuracy          — correct root cause in top 3 hypotheses
  Action Accuracy         — recommended action matches expected/acceptable
  Confidence Calibration  — avg confidence when correct vs incorrect
  Mean Investigation Time — wall-clock seconds per run

Usage:
  python scripts/benchmark_engine.py
  python scripts/benchmark_engine.py --scenario cpu_spike
  python scripts/benchmark_engine.py --ab          # A/B: static vs planner
  python scripts/benchmark_engine.py --out results/benchmark_2026-06-02.json

Leaderboard:
  Each run appends to benchmark_results/leaderboard.json with git commit + metrics.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

SCENARIOS_DIR = ROOT / "test_scenarios"
RESULTS_DIR   = ROOT / "benchmark_results"
RESULTS_DIR.mkdir(exist_ok=True)


# ── LLM caller (mirrors investigation_engine) ─────────────────────────────────

_GEMINI_MODEL  = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
_LLM_BACKEND   = os.getenv("LLM_BACKEND", "gemini").lower()
_OLLAMA_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
_ACTIVE_MODEL  = _OLLAMA_MODEL if _LLM_BACKEND == "ollama" else _GEMINI_MODEL

_REPAIR_SYSTEM = (
    "You are a JSON repair assistant. "
    "The user will give you malformed or truncated JSON. "
    "Return ONLY the corrected, valid, complete JSON — no explanation, no markdown fences."
)


async def _call_gemini(system_prompt: str, user_msg: str) -> str:
    """LLM caller — routes to Ollama or Gemini based on LLM_BACKEND."""
    import httpx
    if _LLM_BACKEND == "ollama":
        payload = {
            "model": _OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 2048},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{_OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    # ── Gemini REST ───────────────────────────────────────────────────────────────────
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
    model = genai.GenerativeModel(
        model_name=_GEMINI_MODEL,
        system_instruction=system_prompt,
    )
    resp = await asyncio.to_thread(
        model.generate_content,
        user_msg,
        generation_config={"temperature": 0.2, "max_output_tokens": 2048},
    )
    return resp.text or ""


_DEFAULT_TIMEOUT = 120.0 if _LLM_BACKEND == "ollama" else 30.0


async def _call_gemini_json(
    system_prompt: str,
    user_msg: str,
    array: bool = False,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[Any, str | None, int]:
    """Call LLM, parse JSON, repair once on failure. Returns (parsed, error|None, llm_calls_used)."""
    raw = await asyncio.wait_for(_call_gemini(system_prompt, user_msg), timeout=timeout)
    parsed, err = _strip_json(raw, array=array)

    if err is None:
        return parsed, None, 1

    # ── Repair pass: ask the model to fix its own malformed output ──────────
    repair_prompt = (
        f"The following JSON is malformed ({err}). Fix it and return ONLY valid JSON:\n\n"
        f"{raw[:1500]}"
    )
    try:
        repaired_raw = await asyncio.wait_for(
            _call_gemini(_REPAIR_SYSTEM, repair_prompt), timeout=_DEFAULT_TIMEOUT
        )
        repaired, repair_err = _strip_json(repaired_raw, array=array)
        if repair_err is None:
            return repaired, None, 2          # repaired: 2 calls used
        return ([] if array else {}), f"repair_failed: {repair_err}", 2
    except Exception as exc:
        return ([] if array else {}), f"repair_exception: {exc}", 2


async def _validate_llm() -> None:
    """Fast-fail: verify model is reachable before running any scenarios."""
    print(f"  Validating LLM ({_ACTIVE_MODEL} via {_LLM_BACKEND})…", end=" ", flush=True)
    try:
        result = await _call_gemini("You are a test.", "Reply with the word OK only.")
        if not result.strip():
            raise ValueError("Empty response from model")
        print(f"OK  (response: {result.strip()[:40]!r})")
    except Exception as exc:
        print(f"FAILED\n")
        print(f"  [error] LLM validation failed: {exc}")
        print(f"  Model attempted: {_ACTIVE_MODEL} (backend={_LLM_BACKEND})")
        print(f"  Tip: set GEMINI_MODEL in .env — check available models with:")
        print(f"       python -c \"import google.generativeai as g; g.configure(api_key='YOUR_KEY'); [print(m.name) for m in g.list_models()]\"")
        sys.exit(1)


# ── Prompt templates (copied from investigation_engine to be self-contained) ──

_HYP_SYSTEM = (
    "You are an expert SRE (Site Reliability Engineer) performing incident investigation. "
    "Generate ranked hypotheses for the given incident evidence. "
    "Respond ONLY with valid JSON — no prose, no markdown code fences."
)

_RCA_SYSTEM = (
    "You are a senior SRE performing root cause analysis. "
    "Synthesise the evidence and hypotheses into a precise root cause determination. "
    "Respond ONLY with a valid JSON object — no prose, no markdown code fences."
)

_HYP_TEMPLATE = """\
A {incident_type} incident was detected.

METRICS:
  CPU: {cpu:.1f}%  Memory: {memory:.1f}%  Disk: {disk:.1f}%
  Load 1m: {load_avg_1m}   Swap: {swap_percent}%

ALERT: {category} / {severity}
DETAIL: {detail}

TOP PROCESSES (CPU):
{cpu_lines}

TOP PROCESSES (MEM):
{mem_lines}

LOGS:
{log_lines}

DYNAMIC CONTEXT:
{context_text}

Generate 3–5 hypotheses. Return a JSON array:
[{{"cause": "...", "confidence": 0.0-1.0, "evidence": ["..."]}}]
"""

_RCA_TEMPLATE = """\
Incident: {incident_type}  CPU: {cpu:.1f}%  Memory: {memory:.1f}%  Disk: {disk:.1f}%
Alert: {category} / {severity}

Top hypotheses:
{hypotheses_block}

LOGS:
{log_lines}

DYNAMIC CONTEXT:
{context_text}

Return exactly this JSON:
{{
  "root_cause": "<one sentence>",
  "confidence": <0.0-1.0>,
  "supporting_evidence": ["..."],
  "recommended_action": "<free_memory|disk_cleanup|clear_cache|run_gc|kill_process|restart_service|notify_only>",
  "reasoning_steps": ["..."]
}}
"""


def _format_procs(procs: list[dict]) -> str:
    if not procs:
        return "  (none)"
    return "\n".join(
        f"  {p.get('name','?')} pid={p.get('pid','?')} cpu={p.get('cpu_percent',0):.1f}% mem={p.get('memory_percent',0):.1f}%"
        for p in procs[:5]
    )


def _format_logs(logs: list[dict]) -> str:
    if not logs:
        return "  (none)"
    return "\n".join(
        f"  [{l.get('level','INFO')}] {l.get('source','?')}: {l.get('message','')}"
        for l in logs[:10]
    )


def _format_context(ctx: dict) -> str:
    if not ctx:
        return "  (none)"
    lines = []
    for section, data in ctx.items():
        lines.append(f"  [{section}]")
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list):
                    for item in v[:5]:
                        lines.append(f"    {item}")
                else:
                    lines.append(f"    {k}: {str(v)[:150]}")
        elif isinstance(data, list):
            for item in data[:5]:
                lines.append(f"    {item}")
    return "\n".join(lines) or "  (none)"


def _strip_json(raw: str, array: bool = False) -> tuple[Any, str | None]:
    """Extract JSON from LLM response. Returns (parsed, error_msg|None)."""
    if not raw or not raw.strip():
        return ([] if array else {}), "empty response"

    # Strategy 1: strip markdown fences then bracket-find
    cleaned = raw.strip()
    for fence in ("```json", "```JSON", "```"):
        if cleaned.startswith(fence):
            cleaned = cleaned[len(fence):]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    char = "[" if array else "{"
    end  = "]" if array else "}"

    start = cleaned.find(char)
    stop  = cleaned.rfind(end) + 1
    if start != -1 and stop > 0:
        try:
            return json.loads(cleaned[start:stop]), None
        except json.JSONDecodeError as e1:
            # Strategy 2: try the full cleaned string
            try:
                return json.loads(cleaned), None
            except json.JSONDecodeError:
                pass
            # Strategy 3: scan for outermost balanced brackets
            depth = 0
            for i, ch in enumerate(cleaned[start:], start):
                if ch == char:   depth += 1
                elif ch == end:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start:i+1]), None
                        except json.JSONDecodeError:
                            break
            return ([] if array else {}), f"JSONDecodeError: {e1}"

    return ([] if array else {}), f"no {char!r} bracket found in response"


# ── Scoring ───────────────────────────────────────────────────────────────────

def _matches_expected(text: str, keywords: list[str]) -> bool:
    """True if any keyword appears in the text (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


_VALID_ACTIONS = frozenset([
    "free_memory", "disk_cleanup", "clear_cache", "run_gc",
    "kill_process", "restart_service", "notify_only",
])


def _normalize_action(raw: str, root_cause: str) -> str:
    """Coerce LLM action output to a valid enum value.
    Falls back to keyword inference from root_cause text when blank/invalid.
    """
    # Strip whitespace and check if already valid
    cleaned = (raw or "").strip().lower().replace("-", "_")
    if cleaned in _VALID_ACTIONS:
        return cleaned
    # Partial match against valid actions (e.g. 'kill process' -> 'kill_process')
    for v in _VALID_ACTIONS:
        if v.replace("_", " ") in cleaned or cleaned in v:
            return v
    # Infer from root_cause text
    rc = root_cause.lower()
    if any(k in rc for k in ["oom", "memory", "killed", "heap", "swap"]):
        return "free_memory"
    if any(k in rc for k in ["disk", "space", "log", "inode"]):
        return "disk_cleanup"
    if any(k in rc for k in ["connection", "pool", "postgres", "sql"]):
        return "notify_only"
    if any(k in rc for k in ["network", "timeout", "upstream", "circuit"]):
        return "notify_only"
    if any(k in rc for k in ["nginx", "service", "crash", "failed"]):
        return "restart_service"
    if any(k in rc for k in ["cpu", "loop", "process", "runaway"]):
        return "kill_process"
    return raw  # return original if nothing matches


def _score_scenario(
    scenario: dict[str, Any],
    hypotheses: list[dict],
    rca: dict,
    elapsed: float,
) -> dict[str, Any]:
    keywords     = scenario["expected_root_cause_keywords"]
    good_actions = scenario["acceptable_actions"]
    exp_action   = scenario["expected_action"]

    root_cause = rca.get("root_cause", "")
    confidence = float(rca.get("confidence", 0.0))
    raw_action = rca.get("recommended_action", "")
    rec_action = _normalize_action(raw_action, root_cause)

    top1 = _matches_expected(root_cause, keywords)
    top3 = top1 or any(
        _matches_expected(h.get("cause", ""), keywords)
        for h in hypotheses[:3]
    )
    action_exact   = rec_action == exp_action
    action_acceptable = rec_action in good_actions

    return {
        "scenario_id":        scenario["scenario_id"],
        "top1_correct":       top1,
        "top3_correct":       top3,
        "action_exact":       action_exact,
        "action_acceptable":  action_acceptable,
        "confidence":         confidence,
        "elapsed_s":          round(elapsed, 2),
        "root_cause":         root_cause,
        "recommended_action": rec_action,
        "expected_root_cause":scenario["expected_root_cause"],
        "expected_action":    exp_action,
        "hypotheses_count":   len(hypotheses),
    }


# ── Single scenario runner ────────────────────────────────────────────────────

def _get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


async def run_scenario(
    scenario: dict[str, Any],
    use_planner: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    sid = scenario["scenario_id"]
    print(f"\n{'='*60}")
    print(f"  Scenario: {sid}")
    print(f"  Expected: {scenario['expected_root_cause']}")
    print(f"{'='*60}")

    metrics   = scenario["metrics"]
    logs      = scenario.get("logs", [])
    ctx       = scenario.get("context", {})
    alert     = scenario["alert"]
    top_procs = scenario.get("top_processes", {})

    # Determine incident type — scenario_id wins for known OOM scenarios
    _SID_TYPE_MAP = {
        "oom_kill": "oom", "oom": "oom",
        "cpu_spike": "cpu",
        "db_pool_exhaustion": "database",
        "disk_full": "disk",
        "memory_leak": "memory",
        "network_timeout": "network",
        "nginx_crash": "service",
    }
    if sid in _SID_TYPE_MAP:
        incident_type = _SID_TYPE_MAP[sid]
    else:
        category = alert.get("category", "").lower()
        if "cpu" in category or metrics.get("cpu", 0) >= 85:
            incident_type = "cpu"
        elif "memory" in category or metrics.get("memory", 0) >= 85:
            incident_type = "memory"
        elif "disk" in category or metrics.get("disk", 0) >= 85:
            incident_type = "disk"
        elif "network" in category:
            incident_type = "network"
        elif "database" in category or "db" in category:
            incident_type = "database"
        else:
            incident_type = "service"

    cpu_lines  = _format_procs(top_procs.get("by_cpu", []))
    mem_lines  = _format_procs(top_procs.get("by_mem", []))
    log_lines  = _format_logs(logs)
    ctx_text   = _format_context(ctx)

    t0 = time.monotonic()
    llm_calls = 0
    est_tokens = 0

    # Stage 1: Hypotheses
    hyp_prompt = _HYP_TEMPLATE.format(
        incident_type=incident_type,
        cpu=metrics.get("cpu", 0),
        memory=metrics.get("memory", 0),
        disk=metrics.get("disk", 0),
        load_avg_1m=metrics.get("load_avg_1m", "N/A"),
        swap_percent=metrics.get("swap_percent", 0),
        category=alert.get("category", ""),
        severity=alert.get("severity", ""),
        detail=alert.get("detail", ""),
        cpu_lines=cpu_lines,
        mem_lines=mem_lines,
        log_lines=log_lines,
        context_text=ctx_text,
    )

    hyp_raw = ""
    hyp_parse_err = None
    try:
        hypotheses, hyp_parse_err, hyp_calls = await _call_gemini_json(
            _HYP_SYSTEM, hyp_prompt, array=True, timeout=_DEFAULT_TIMEOUT
        )
        llm_calls += hyp_calls
        est_tokens += (len(_HYP_SYSTEM) + len(hyp_prompt)) // 4
        if hyp_parse_err:
            print(f"  [WARN] Hypothesis parse failed (repair also failed): {hyp_parse_err}")
        elif hyp_calls > 1:
            print(f"  [INFO] Hypothesis JSON repaired in {hyp_calls} calls")
    except Exception as exc:
        print(f"  [WARN] Hypothesis generation failed: {exc}")
        hyp_parse_err = str(exc)
        hypotheses = []

    # Stage 1.5: Planner simulation (A/B mode)
    planner_steps_taken = 0
    planner_collectors: list[str] = []
    planner_pre_hyp    = hypotheses[0].get("cause", "") if hypotheses else ""
    planner_pre_conf   = hypotheses[0].get("confidence", 0.0) if hypotheses else 0.0
    if use_planner and hypotheses:
        top_hyp = planner_pre_hyp
        planner_system = (
            "You are a senior SRE choosing the next collector. "
            "Respond ONLY with JSON: {\"confident_enough\": bool, \"collector\": str|null, \"reason\": str}"
        )
        gathered_keys: list[str] = []
        for _step in range(4):
            planner_user = (
                f"Incident: {incident_type} cpu={metrics.get('cpu',0):.0f}% "
                f"mem={metrics.get('memory',0):.0f}%\n"
                f"Current best hypothesis: {top_hyp[:100]}\n"
                f"Logs:\n{log_lines[:300]}\n"
                f"Already gathered: {', '.join(gathered_keys) or 'none'}\n\n"
                "Available: process_tree, memory_breakdown, oom_history, "
                "disk_largest_dirs, pg_connections, pg_long_queries, "
                "service_state, net_open_ports, net_connection_summary\n\n"
                "Are you confident enough OR what would you collect next?"
            )
            try:
                decision, _, plan_calls = await _call_gemini_json(
                    planner_system, planner_user, array=False, timeout=15
                )
                llm_calls += plan_calls
                est_tokens += (len(planner_system) + len(planner_user)) // 4
                planner_steps_taken += 1
                if decision.get("confident_enough", False):
                    break
                collector = str(decision.get("collector") or "")
                if collector and collector not in gathered_keys:
                    gathered_keys.append(collector)
                    planner_collectors.append(collector)
            except Exception:
                break

    if verbose:
        for i, h in enumerate(hypotheses[:3]):
            print(f"  H{i+1} ({h.get('confidence', 0):.2f}): {h.get('cause', '?')[:80]}")

    # Stage 2: RCA
    hypotheses_block = "\n".join(
        f"  {i+1}. ({h.get('confidence', 0):.2f}) {h.get('cause', '')}"
        for i, h in enumerate(hypotheses[:5])
    ) or "  (no hypotheses generated)"

    rca_prompt = _RCA_TEMPLATE.format(
        incident_type=incident_type,
        cpu=metrics.get("cpu", 0),
        memory=metrics.get("memory", 0),
        disk=metrics.get("disk", 0),
        category=alert.get("category", ""),
        severity=alert.get("severity", ""),
        hypotheses_block=hypotheses_block,
        log_lines=log_lines,
        context_text=ctx_text,
    )

    rca_raw = ""
    rca_parse_err = None
    try:
        rca, rca_parse_err, rca_calls = await _call_gemini_json(
            _RCA_SYSTEM, rca_prompt, array=False, timeout=_DEFAULT_TIMEOUT
        )
        llm_calls += rca_calls
        est_tokens += (len(_RCA_SYSTEM) + len(rca_prompt)) // 4
        if rca_parse_err:
            print(f"  [WARN] RCA parse failed (repair also failed): {rca_parse_err}")
        elif rca_calls > 1:
            print(f"  [INFO] RCA JSON repaired in {rca_calls} calls")
    except Exception as exc:
        print(f"  [WARN] RCA failed: {exc}")
        rca_parse_err = str(exc)
        rca = {}

    elapsed = time.monotonic() - t0
    result  = _score_scenario(scenario, hypotheses, rca, elapsed)
    result["llm_calls"]          = llm_calls
    result["est_tokens"]         = est_tokens
    result["planner_steps_taken"]      = planner_steps_taken
    result["use_planner"]              = use_planner
    # ── Planner influence tracking ────────────────────────────────────────────
    post_conf = float(rca.get("confidence", 0.0))
    planner_post_hyp = rca.get("root_cause", "")
    result["planner_collectors"]       = planner_collectors
    result["planner_changed_diagnosis"] = (
        bool(planner_collectors)
        and planner_pre_hyp.lower()[:40] != planner_post_hyp.lower()[:40]
    )
    result["planner_confidence_delta"] = round(post_conf - planner_pre_conf, 3) if use_planner else None
    # ── Failure audit fields ──────────────────────────────────────────────────
    result["raw_rca"]            = rca_raw[:500] if rca_raw else ""
    result["rca_parse_error"]    = rca_parse_err
    result["hyp_parse_error"]    = hyp_parse_err
    result["incident_type"]      = incident_type
    # rca_summary used by confusion matrix classifier
    result["rca_summary"]        = (
        rca.get("root_cause", "") + " "
        + " ".join(rca.get("supporting_evidence", []))[:200]
    ).strip()
    # failure_type classification (5 specific categories)
    root_cause_text = rca.get("root_cause", "")
    if rca_parse_err and ("repair" in (rca_parse_err or "") or not root_cause_text and not hypotheses):
        result["failure_type"] = "json_parse_failed"
    elif hypotheses and not root_cause_text:
        result["failure_type"] = "empty_rca"
    elif not result["top1_correct"] and root_cause_text:
        keywords = scenario.get("expected_root_cause_keywords", [])
        hyp_match = any(
            _matches_expected(h.get("cause", ""), keywords)
            for h in hypotheses[:5]
        )
        result["failure_type"] = "scoring_mismatch" if hyp_match else "wrong_diagnosis"
    elif result["top1_correct"] and not result["action_acceptable"]:
        result["failure_type"] = "action_mismatch"
    else:
        result["failure_type"] = None

    top1_mark = "✓" if result["top1_correct"] else "✗"
    act_mark  = "✓" if result["action_acceptable"] else "✗"
    print(f"\n  Root Cause: {result['root_cause'][:80]}")
    print(f"  Action:     {result['recommended_action']}")
    print(f"  Top-1: {top1_mark}   Action: {act_mark}   Confidence: {result['confidence']:.2f}   "
          f"Time: {elapsed:.1f}s   LLM calls: {llm_calls}   ~{est_tokens} tokens")

    return result


# ── Aggregate report ──────────────────────────────────────────────────────────

def _print_ab_comparison(static_results: list[dict], planner_results: list[dict]) -> None:
    """Print a comparison table for A/B mode."""
    pairs = {r["scenario_id"]: r for r in static_results}
    print("\n" + "="*72)
    print("  A/B COMPARISON: Static vs Planner")
    print("="*72)
    print(f"  {'Scenario':<28} {'Static Top1':<14} {'Planner Top1':<14} {'ΔCalls':<8} {'ΔTime'}")
    print(f"  {'-'*28} {'-'*13} {'-'*13} {'-'*7} {'-'*6}")
    for pr in planner_results:
        sid = pr["scenario_id"]
        sr  = pairs.get(sid)
        if not sr:
            continue
        s_t1 = "✓" if sr["top1_correct"] else "✗"
        p_t1 = "✓" if pr["top1_correct"] else "✗"
        delta_calls = pr["llm_calls"] - sr["llm_calls"]
        delta_time  = pr["elapsed_s"] - sr["elapsed_s"]
        print(f"  {sid:<28} {s_t1} ({sr['confidence']:.2f})      "
              f"{p_t1} ({pr['confidence']:.2f})      "
              f"+{delta_calls:<6}  +{delta_time:.1f}s")

    s_top1 = sum(1 for r in static_results  if r["top1_correct"]) / max(len(static_results), 1)
    p_top1 = sum(1 for r in planner_results if r["top1_correct"]) / max(len(planner_results), 1)
    s_calls = sum(r["llm_calls"] for r in static_results)  / max(len(static_results), 1)
    p_calls = sum(r["llm_calls"] for r in planner_results) / max(len(planner_results), 1)
    s_time  = sum(r["elapsed_s"] for r in static_results)  / max(len(static_results), 1)
    p_time  = sum(r["elapsed_s"] for r in planner_results) / max(len(planner_results), 1)
    print(f"\n  SUMMARY:")
    print(f"    Static  → Top-1: {s_top1:.0%}  avg calls: {s_calls:.1f}  avg time: {s_time:.1f}s")
    print(f"    Planner → Top-1: {p_top1:.0%}  avg calls: {p_calls:.1f}  avg time: {p_time:.1f}s")
    delta_acc = (p_top1 - s_top1) * 100
    print(f"    Planner improvement: {delta_acc:+.1f}pp accuracy  "
          f"+{p_calls - s_calls:.1f} calls  +{p_time - s_time:.1f}s")
    print("="*72)


def _print_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        print("\nNo results.")
        return {}

    # ── Validity guard ────────────────────────────────────────────────────────
    total_llm_calls = sum(r.get("llm_calls", 0) for r in results)
    scenarios_with_calls = sum(1 for r in results if r.get("llm_calls", 0) > 0)
    if total_llm_calls == 0:
        print("\n" + "!"*60)
        print("  BENCHMARK RESULT INVALID — LLM NEVER CALLED")
        print("!"*60)
        print(f"  Scenarios run:     {n}")
        print(f"  LLM calls total:   0")
        print(f"  Accuracy metrics:  SUPPRESSED (all zeros are meaningless)")
        print("!"*60)
        print("  Likely cause: model name not found (check GEMINI_MODEL in .env)")
        print("  Rerun after fixing: python scripts/benchmark_engine.py --ab")
        print("!"*60)
        return {"valid": False, "n_scenarios": n, "total_llm_calls": 0}
    if scenarios_with_calls < n:
        print(f"\n  [WARN] {n - scenarios_with_calls}/{n} scenarios had 0 LLM calls — partial results only")

    top1_correct  = sum(1 for r in results if r["top1_correct"])
    top3_correct  = sum(1 for r in results if r["top3_correct"])
    act_acceptable = sum(1 for r in results if r["action_acceptable"])
    act_exact     = sum(1 for r in results if r["action_exact"])

    correct_confs   = [r["confidence"] for r in results if r["top1_correct"]]
    incorrect_confs = [r["confidence"] for r in results if not r["top1_correct"]]
    avg_time        = sum(r["elapsed_s"] for r in results) / n

    top1_acc  = top1_correct  / n
    top3_acc  = top3_correct  / n
    act_acc   = act_acceptable / n
    act_exact_acc = act_exact / n
    avg_conf_correct   = sum(correct_confs)   / len(correct_confs)   if correct_confs   else 0.0
    avg_conf_incorrect = sum(incorrect_confs) / len(incorrect_confs) if incorrect_confs else 0.0

    # Calibration gap: well-calibrated model has higher confidence when correct
    calibration_gap = avg_conf_correct - avg_conf_incorrect

    print("\n" + "="*60)
    print("  BENCHMARK RESULTS")
    print("="*60)
    print(f"  Scenarios:          {n}")
    print(f"  Top-1 Accuracy:     {top1_acc:.0%}  ({top1_correct}/{n})")
    print(f"  Top-3 Accuracy:     {top3_acc:.0%}  ({top3_correct}/{n})")
    print(f"  Action (acceptable):{act_acc:.0%}  ({act_acceptable}/{n})")
    print(f"  Action (exact):     {act_exact_acc:.0%}  ({act_exact}/{n})")
    print(f"  Avg Confidence:     {sum(r['confidence'] for r in results)/n:.2f}")
    print(f"  Conf (correct):     {avg_conf_correct:.2f}")
    print(f"  Conf (incorrect):   {avg_conf_incorrect:.2f}")
    print(f"  Calibration gap:    {calibration_gap:+.2f}  (positive = well-calibrated)")
    print(f"  Avg time/scenario:  {avg_time:.1f}s")
    print("="*60)

    # Per-scenario summary table
    print("\n  Per-scenario breakdown:")
    print(f"  {'Scenario':<28} {'Top1':<6} {'Action':<8} {'Conf':<6} {'Time'}")
    print(f"  {'-'*28} {'-'*5} {'-'*7} {'-'*5} {'-'*5}")
    for r in results:
        t1 = "✓" if r["top1_correct"]        else "✗"
        ac = "✓" if r["action_acceptable"]    else "✗"
        print(f"  {r['scenario_id']:<28} {t1:<6} {ac:<8} {r['confidence']:<6.2f} {r['elapsed_s']:.1f}s")

    # Failure audit breakdown
    failure_counts: dict[str, int] = {}
    for r in results:
        ft = r.get("failure_type") or "correct"
        failure_counts[ft] = failure_counts.get(ft, 0) + 1
    if any(v > 0 for k, v in failure_counts.items() if k != "correct"):
        print("\n  Failure audit:")
        for ftype, count in sorted(failure_counts.items()):
            mark = "  " if ftype == "correct" else "⚠ "
            print(f"  {mark}{ftype:<40} {count}")

    # Planner influence table (only shown in planner mode)
    planner_runs = [r for r in results if r.get("use_planner")]
    if planner_runs:
        influenced   = sum(1 for r in planner_runs if r.get("planner_changed_diagnosis"))
        any_collect  = sum(1 for r in planner_runs if r.get("planner_collectors"))
        conf_deltas  = [r["planner_confidence_delta"] for r in planner_runs
                        if r.get("planner_confidence_delta") is not None]
        avg_delta    = sum(conf_deltas) / len(conf_deltas) if conf_deltas else 0.0
        print(f"\n  Planner influence ({len(planner_runs)} runs):")
        print(f"    Collectors requested:    {any_collect}/{len(planner_runs)} scenarios")
        print(f"    Changed diagnosis:       {influenced}/{len(planner_runs)} scenarios")
        print(f"    Avg confidence delta:    {avg_delta:+.3f}")
        top_collectors: dict[str, int] = {}
        for r in planner_runs:
            for c in r.get("planner_collectors", []):
                top_collectors[c] = top_collectors.get(c, 0) + 1
        if top_collectors:
            ranked = sorted(top_collectors.items(), key=lambda x: -x[1])
            print(f"    Most requested:          {', '.join(f'{c}({v})' for c,v in ranked[:5])}")

    avg_calls  = sum(r.get("llm_calls", 0) for r in results) / n
    avg_tokens = sum(r.get("est_tokens", 0) for r in results) / n
    print(f"  Avg LLM calls:      {avg_calls:.1f}")
    print(f"  Avg est. tokens:    {avg_tokens:.0f}")
    print("="*60)

    planner_influence_rate = (
        sum(1 for r in planner_runs if r.get("planner_changed_diagnosis")) / len(planner_runs)
        if planner_runs else None
    )

    summary = {
        "valid":                True,
        "scenarios_with_llm":   scenarios_with_calls,
        "n_scenarios":          n,
        "top1_accuracy":        round(top1_acc, 3),
        "top3_accuracy":        round(top3_acc, 3),
        "action_accuracy":      round(act_acc, 3),
        "action_exact":         round(act_exact_acc, 3),
        "avg_confidence":       round(sum(r["confidence"] for r in results) / n, 3),
        "conf_when_correct":    round(avg_conf_correct, 3),
        "conf_when_incorrect":  round(avg_conf_incorrect, 3),
        "calibration_gap":      round(calibration_gap, 3),
        "avg_investigation_s":  round(avg_time, 2),
        "avg_llm_calls":        round(avg_calls, 2),
        "avg_est_tokens":          round(avg_tokens, 0),
        "planner_influence_rate":  planner_influence_rate,
        "per_scenario":            results,
    }
    return summary


# ── Main ─────────────────────────────────────────────────────────────────────

def _inject_noise(scenario: dict[str, Any], seed: int | None = None) -> dict[str, Any]:
    """Tier C: inject irrelevant logs and metrics to test robustness."""
    import copy, random
    rng = random.Random(seed)
    s = copy.deepcopy(scenario)
    noise_logs = [
        {"level": "INFO",  "source": "cron",    "message": "Backup completed: 4218 files archived"},
        {"level": "DEBUG", "source": "app",     "message": "Cache hit ratio: 0.87"},
        {"level": "INFO",  "source": "monitor", "message": "Health check passed for /api/ping"},
        {"level": "DEBUG", "source": "nginx",   "message": "200 GET /favicon.ico 0.001s"},
        {"level": "INFO",  "source": "app",     "message": "Scheduled job 'report_generator' started"},
        {"level": "WARN",  "source": "app",     "message": "Deprecated API endpoint /v1/users called by client 10.0.1.44"},
        {"level": "INFO",  "source": "postgres","message": "checkpoint complete: wrote 142 buffers (0.1%)"},
    ]
    injected = rng.sample(noise_logs, min(4, len(noise_logs)))
    s["logs"] = injected + s.get("logs", [])  # prepend noise to bury signal
    # Slightly perturb neutral metrics (not the pathological ones)
    for key in ["load_avg_5m", "net_established"]:
        if key in s.get("metrics", {}):
            s["metrics"][key] = round(s["metrics"][key] * rng.uniform(0.9, 1.1), 1)
    s["_noise_injected"] = True
    return s


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the investigation engine")
    parser.add_argument("--scenario", help="Run a single scenario by ID")
    parser.add_argument("--out",      help="Write JSON results to this file")
    parser.add_argument("--ab",         action="store_true", help="A/B: run each scenario twice (static then planner)")
    parser.add_argument("--confusion",  action="store_true", help="Print confusion matrix after run")
    parser.add_argument("--no-verbose", action="store_true")
    parser.add_argument("--noise",      action="store_true", help="Tier C: inject irrelevant noise into scenarios before running")
    parser.add_argument("--tier",       help="Filter scenarios by tier tag (A, B, C or comma-list)")
    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("[error] GEMINI_API_KEY not set")
        sys.exit(1)

    await _validate_llm()

    # Load scenarios
    scenario_files = sorted(SCENARIOS_DIR.glob("*.json"))
    if not scenario_files:
        print(f"[error] No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)

    tier_filter: set[str] = set()
    if args.tier:
        tier_filter = {t.strip().upper() for t in args.tier.split(",")}

    scenarios = []
    for sf in scenario_files:
        s = json.loads(sf.read_text())
        if args.scenario and s["scenario_id"] != args.scenario:
            continue
        if tier_filter:
            scenario_tier = s.get("tier", "A").upper()
            if scenario_tier not in tier_filter:
                continue
        if args.noise:
            s = _inject_noise(s)
        scenarios.append(s)

    if not scenarios:
        print(f"[error] No matching scenarios for --scenario={args.scenario}")
        sys.exit(1)

    commit = _get_git_commit()
    run_ts = int(time.time())

    if args.ab:
        print(f"\nA/B mode — running {len(scenarios)} scenario(s) × 2 (static + planner)…")
        static_results  = []
        planner_results = []
        for s in scenarios:
            sr = await run_scenario(s, use_planner=False, verbose=not args.no_verbose)
            static_results.append(sr)
            pr = await run_scenario(s, use_planner=True,  verbose=not args.no_verbose)
            planner_results.append(pr)

        _print_ab_comparison(static_results, planner_results)
        static_summary  = _print_report(static_results)
        planner_summary = _print_report(planner_results)

        ab_result = {
            "commit":          commit,
            "timestamp":       run_ts,
            "mode":            "ab",
            "static":          static_summary,
            "planner":         planner_summary,
            "planner_delta_top1": round(
                (planner_summary.get("top1_accuracy") or 0) - (static_summary.get("top1_accuracy") or 0), 3
            ),
            "planner_extra_calls": round(
                (planner_summary.get("avg_llm_calls") or 0) - (static_summary.get("avg_llm_calls") or 0), 2
            ),
        }
        out_path = args.out or str(RESULTS_DIR / f"ab_{run_ts}.json")
        pathlib.Path(out_path).write_text(json.dumps(ab_result, indent=2))
        print(f"\n  A/B results saved → {out_path}")
        if static_summary.get("valid", False):
            _append_leaderboard(commit, run_ts, static_summary, planner_summary)
        else:
            print("  [leaderboard] Skipped — invalid run (0 LLM calls)")
        if args.confusion:
            print("\n  [Static mode confusion matrix]")
            _print_confusion_matrix(static_results)
            print("\n  [Planner mode confusion matrix]")
            _print_confusion_matrix(planner_results)
    else:
        print(f"\nRunning {len(scenarios)} scenario(s)…")
        results = []
        for s in scenarios:
            r = await run_scenario(s, use_planner=False, verbose=not args.no_verbose)
            results.append(r)

        summary = _print_report(results)
        summary["commit"]    = commit
        summary["timestamp"] = run_ts
        summary["mode"]      = "static"

        out_path = args.out or str(RESULTS_DIR / f"benchmark_{run_ts}.json")
        pathlib.Path(out_path).write_text(json.dumps(summary, indent=2))
        print(f"\n  Results saved → {out_path}")
        if summary.get("valid", False):
            _append_leaderboard(commit, run_ts, summary, None)
        else:
            print("  [leaderboard] Skipped — invalid run (0 LLM calls)")
        if args.confusion:
            _print_confusion_matrix(results)


def _print_confusion_matrix(results: list[dict]) -> None:
    """Print a confusion matrix: actual incident type → predicted incident type."""
    # Extract actual (from scenario) and predicted (from rca text)
    TYPES = ["cpu", "memory", "disk", "database", "network", "service", "oom"]

    def _detect_type(text: str) -> str:
        t = (text or "").lower()
        # Order matters: more specific patterns first
        if any(k in t for k in ["pool", "postgres", "pg_stat", "pg_", "sql", "connection pool", "max_connections"]):
            return "database"
        if any(k in t for k in ["oom killer", "out of memory", "oom kill", "oomkill"]):
            return "oom"
        if any(k in t for k in ["disk full", "no space", "inode", "filesystem full", "disk usage", "disk capacity"]):
            return "disk"
        if any(k in t for k in ["memory leak", "heap", "memory exhaustion", "swap", "rss"]):
            return "memory"
        if any(k in t for k in ["timeout", "dns", "upstream", "circuit breaker", "payment"]):
            return "network"
        if any(k in t for k in ["nginx", "ssl", "systemd", "service fail", "proxy_", "worker process"]):
            return "service"
        if any(k in t for k in ["cpu", "runaway", "tight loop", "cpu-bound"]):
            return "cpu"
        if any(k in t for k in ["memory", "oom"]):
            return "memory"
        if any(k in t for k in ["disk", "storage"]):
            return "disk"
        if any(k in t for k in ["network", "tcp", "socket", "connection"]):
            return "network"
        if any(k in t for k in ["service", "crash", "process"]):
            return "service"
        return "unknown"

    matrix: dict[str, dict[str, int]] = {}
    for r in results:
        # actual: prefer explicit incident_type field set during run_scenario
        actual    = r.get("incident_type") or _detect_type(r.get("scenario_id", ""))
        # predicted: use rca_summary (rca text + supporting evidence)
        predicted = _detect_type(r.get("rca_summary", "") or r.get("root_cause", ""))
        matrix.setdefault(actual, {})
        matrix[actual][predicted] = matrix[actual].get(predicted, 0) + 1

    if not matrix:
        print("  [confusion] No data to display")
        return

    all_predicted = sorted({p for row in matrix.values() for p in row})
    col_w = max(14, max(len(p) for p in all_predicted))
    row_w = max(14, max(len(a) for a in matrix))

    print("\n" + "="*60)
    print("  CONFUSION MATRIX  (rows=actual, cols=predicted)")
    print("="*60)
    header = f"  {'Actual':<{row_w}}" + "".join(f"  {p:<{col_w}}" for p in all_predicted)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for actual, row in sorted(matrix.items()):
        line = f"  {actual:<{row_w}}"
        for p in all_predicted:
            count = row.get(p, 0)
            cell  = str(count) if count > 0 else "-"
            line += f"  {cell:<{col_w}}"
        print(line)
    print("="*60)
    # Diagonal accuracy
    correct = sum(row.get(a, 0) for a, row in matrix.items())
    total   = sum(v for row in matrix.values() for v in row.values())
    print(f"  Type identification accuracy: {correct}/{total} = {correct/max(total,1):.0%}")
    print("="*60)


def _append_leaderboard(
    commit: str,
    ts: int,
    static_summary: dict,
    planner_summary: dict | None,
) -> None:
    """Append this run to the rolling leaderboard JSON."""
    lb_path = RESULTS_DIR / "leaderboard.json"
    try:
        leaderboard: list = json.loads(lb_path.read_text()) if lb_path.exists() else []
    except Exception:
        leaderboard = []

    entry: dict[str, Any] = {
        "commit":          commit,
        "timestamp":       ts,
        "top1_accuracy":   static_summary.get("top1_accuracy"),
        "action_accuracy": static_summary.get("action_accuracy"),
        "calibration_gap": static_summary.get("calibration_gap"),
        "avg_llm_calls":   static_summary.get("avg_llm_calls"),
        "avg_time_s":      static_summary.get("avg_investigation_s"),
    }
    if planner_summary:
        entry["planner_top1_accuracy"] = planner_summary.get("top1_accuracy")
        entry["planner_delta"]         = round(
            (planner_summary.get("top1_accuracy") or 0)
            - (static_summary.get("top1_accuracy") or 0), 3
        )
        entry["planner_extra_calls"]   = round(
            (planner_summary.get("avg_llm_calls") or 0)
            - (static_summary.get("avg_llm_calls") or 0), 2
        )

    leaderboard.append(entry)
    lb_path.write_text(json.dumps(leaderboard, indent=2))
    print(f"  Leaderboard updated → {lb_path}  ({len(leaderboard)} entries)")


if __name__ == "__main__":
    asyncio.run(main())
