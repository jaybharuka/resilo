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
  python scripts/benchmark_engine.py --out results/benchmark_2026-06-02.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
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

async def _call_gemini(system_prompt: str, user_msg: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=system_prompt,
    )
    resp = await asyncio.to_thread(
        model.generate_content,
        user_msg,
        generation_config={"temperature": 0.2, "max_output_tokens": 2048},
    )
    return resp.text or ""


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


def _strip_json(raw: str, array: bool = False) -> Any:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    char = "[" if array else "{"
    end  = "]" if array else "}"
    start = raw.find(char)
    stop  = raw.rfind(end) + 1
    if start == -1 or stop == 0:
        return [] if array else {}
    try:
        return json.loads(raw[start:stop])
    except json.JSONDecodeError:
        return [] if array else {}


# ── Scoring ───────────────────────────────────────────────────────────────────

def _matches_expected(text: str, keywords: list[str]) -> bool:
    """True if any keyword appears in the text (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


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
    rec_action = rca.get("recommended_action", "")

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

async def run_scenario(scenario: dict[str, Any], verbose: bool = True) -> dict[str, Any]:
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

    # Determine incident type
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
        incident_type = "db"
    else:
        incident_type = "service"

    cpu_lines  = _format_procs(top_procs.get("by_cpu", []))
    mem_lines  = _format_procs(top_procs.get("by_mem", []))
    log_lines  = _format_logs(logs)
    ctx_text   = _format_context(ctx)

    t0 = time.monotonic()

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

    try:
        hyp_raw = await asyncio.wait_for(_call_gemini(_HYP_SYSTEM, hyp_prompt), timeout=30)
        hypotheses = _strip_json(hyp_raw, array=True)
    except Exception as exc:
        print(f"  [WARN] Hypothesis generation failed: {exc}")
        hypotheses = []

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

    try:
        rca_raw = await asyncio.wait_for(_call_gemini(_RCA_SYSTEM, rca_prompt), timeout=30)
        rca = _strip_json(rca_raw, array=False)
    except Exception as exc:
        print(f"  [WARN] RCA failed: {exc}")
        rca = {}

    elapsed = time.monotonic() - t0
    result  = _score_scenario(scenario, hypotheses, rca, elapsed)

    top1_mark = "✓" if result["top1_correct"] else "✗"
    act_mark  = "✓" if result["action_acceptable"] else "✗"
    print(f"\n  Root Cause: {result['root_cause'][:80]}")
    print(f"  Action:     {result['recommended_action']}")
    print(f"  Top-1: {top1_mark}   Action: {act_mark}   Confidence: {result['confidence']:.2f}   Time: {elapsed:.1f}s")

    return result


# ── Aggregate report ──────────────────────────────────────────────────────────

def _print_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        print("\nNo results.")
        return {}

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

    summary = {
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
        "per_scenario":         results,
    }
    return summary


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the investigation engine")
    parser.add_argument("--scenario", help="Run a single scenario by ID")
    parser.add_argument("--out",      help="Write JSON results to this file")
    parser.add_argument("--no-verbose", action="store_true")
    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("[error] GEMINI_API_KEY not set")
        sys.exit(1)

    # Load scenarios
    scenario_files = sorted(SCENARIOS_DIR.glob("*.json"))
    if not scenario_files:
        print(f"[error] No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)

    scenarios = []
    for sf in scenario_files:
        s = json.loads(sf.read_text())
        if args.scenario and s["scenario_id"] != args.scenario:
            continue
        scenarios.append(s)

    if not scenarios:
        print(f"[error] No matching scenarios for --scenario={args.scenario}")
        sys.exit(1)

    print(f"\nRunning {len(scenarios)} scenario(s)…")
    results = []
    for s in scenarios:
        r = await run_scenario(s, verbose=not args.no_verbose)
        results.append(r)

    summary = _print_report(results)

    # Write results
    out_path = args.out or str(RESULTS_DIR / f"benchmark_{int(time.time())}.json")
    pathlib.Path(out_path).write_text(json.dumps(summary, indent=2))
    print(f"\n  Results saved → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
