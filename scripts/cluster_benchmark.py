"""
cluster_benchmark.py — Benchmark the semantic incident correlation/clustering engine.

Usage:
    python scripts/cluster_benchmark.py
    python scripts/cluster_benchmark.py --threshold 0.72
    python scripts/cluster_benchmark.py --out results/cluster_benchmark.json
    python scripts/cluster_benchmark.py --verbose

Measures:
    Cluster Precision    — of pairs the engine grouped, what % truly belong together
    Cluster Recall       — of pairs that truly belong together, what % did the engine find
    F1 Score             — harmonic mean of precision and recall
    False Correlation Rate (FCR) — pairs grouped that should NOT be together
    Over-clustering rate  — fixture groups that got merged into one cluster
    Under-clustering rate — fixture groups split across 2+ clusters
    Chaining score        — avg (avg_sim - min_sim) per cluster; high = chaining risk

Fixtures encode ground truth as `group_id`:
    Same group_id → should be in the same cluster
    Different group_id → should NOT be clustered together

The benchmark generates embeddings via Gemini text-embedding-004 (same model used
in production) so similarity scores are directly comparable to live behaviour.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "cluster_fixtures"
sys.path.insert(0, str(ROOT))

# Load .env so GEMINI_API_KEY is available when running directly
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_THRESHOLD = float(os.getenv("CLUSTER_THRESHOLD", "0.50"))
EMBEDDING_MODEL   = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


# ── Embedding ─────────────────────────────────────────────────────────────────

_bench_model = None

def _get_bench_model():
    global _bench_model
    if _bench_model is None:
        from sentence_transformers import SentenceTransformer
        _bench_model = SentenceTransformer(EMBEDDING_MODEL)
    return _bench_model


async def _embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using sentence-transformers (mirrors production memory_store.py)."""
    model = await asyncio.to_thread(_get_bench_model)
    vectors = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


# ── Maths (mirrors correlation_engine.py — no shared import to keep standalone) ─

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _cluster(embeddings: list[list[float]], threshold: float) -> list[int]:
    """
    Single-linkage union-find clustering.
    Returns a label list: labels[i] = cluster_id for embedding i.
    """
    n = len(embeddings)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            if _cosine(embeddings[i], embeddings[j]) >= threshold:
                union(i, j)

    return [find(i) for i in range(n)]


def _min_pairwise(group_embeddings: list[list[float]]) -> float:
    """Minimum pairwise cosine similarity within a set of embeddings."""
    if len(group_embeddings) < 2:
        return 1.0
    mn = 1.0
    for i in range(len(group_embeddings)):
        for j in range(i + 1, len(group_embeddings)):
            s = _cosine(group_embeddings[i], group_embeddings[j])
            if s < mn:
                mn = s
    return mn


# ── Pair-level metrics ────────────────────────────────────────────────────────

def _pair_metrics(
    true_labels: list[int],
    pred_labels: list[int],
) -> dict[str, float]:
    """
    Compute precision, recall, F1, and false-correlation rate at the pair level.

    A "positive pair" is any (i, j) where i < j.
    True positive: same true_label AND same pred_label.
    False positive: different true_label but same pred_label.
    False negative: same true_label but different pred_label.
    """
    n = len(true_labels)
    tp = fp = fn = 0
    for i in range(n):
        for j in range(i + 1, n):
            same_true = true_labels[i] == true_labels[j]
            same_pred = pred_labels[i] == pred_labels[j]
            if same_true and same_pred:
                tp += 1
            elif not same_true and same_pred:
                fp += 1
            elif same_true and not same_pred:
                fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    total_neg_pairs = sum(
        1 for i in range(n) for j in range(i + 1, n)
        if true_labels[i] != true_labels[j]
    )
    fcr = fp / total_neg_pairs if total_neg_pairs > 0 else 0.0

    return {
        "precision":            round(precision, 4),
        "recall":               round(recall, 4),
        "f1":                   round(f1, 4),
        "false_correlation_rate": round(fcr, 4),
        "true_positives":       tp,
        "false_positives":      fp,
        "false_negatives":      fn,
    }


def _cluster_level_metrics(
    true_labels: list[int],
    pred_labels: list[int],
    embeddings: list[list[float]],
) -> dict[str, Any]:
    """
    Over/under-clustering rates and chaining score per predicted cluster.
    """
    # Group indices by predicted cluster
    pred_groups: dict[int, list[int]] = {}
    for idx, pl in enumerate(pred_labels):
        pred_groups.setdefault(pl, []).append(idx)

    # Singletons (not clustered with anything)
    singletons = sum(1 for g in pred_groups.values() if len(g) == 1)

    # Over-clustering: a predicted cluster contains members from 2+ true groups
    true_groups: dict[int, set[int]] = {}
    for idx, tl in enumerate(true_labels):
        true_groups.setdefault(tl, set()).add(idx)

    over_clustered = 0
    chaining_deltas: list[float] = []
    for pred_label, members in pred_groups.items():
        if len(members) < 2:
            continue
        # How many distinct true groups are in this predicted cluster?
        true_ids_in_cluster = {true_labels[m] for m in members}
        if len(true_ids_in_cluster) > 1:
            over_clustered += 1

        # Chaining diagnostic: avg_sim - min_sim
        embs = [embeddings[m] for m in members]
        n = len(embs)
        sims = [_cosine(embs[i], embs[j]) for i in range(n) for j in range(i+1, n)]
        if sims:
            avg_s = sum(sims) / len(sims)
            min_s = min(sims)
            chaining_deltas.append(avg_s - min_s)

    # Under-clustering: a true group is split across 2+ predicted clusters
    under_clustered = 0
    for true_label, members in true_groups.items():
        if len(members) < 2:
            continue
        pred_ids_for_group = {pred_labels[m] for m in members}
        if len(pred_ids_for_group) > 1:
            under_clustered += 1

    return {
        "singletons":         singletons,
        "over_clustered":     over_clustered,
        "under_clustered":    under_clustered,
        "avg_chaining_delta": round(sum(chaining_deltas) / len(chaining_deltas), 4) if chaining_deltas else 0.0,
        "max_chaining_delta": round(max(chaining_deltas), 4) if chaining_deltas else 0.0,
    }


# ── Fixture loading ────────────────────────────────────────────────────────────

def _load_fixtures() -> list[dict[str, Any]]:
    """Load all JSON fixture files from cluster_fixtures/."""
    fixtures = []
    for p in sorted(FIXTURES_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            # Normalise: each fixture is a list of alert objects
            if isinstance(data, list):
                fixtures.extend(data)
            elif isinstance(data, dict) and "alerts" in data:
                fixtures.append(data)
        except Exception as exc:
            print(f"  [WARN] Could not load {p.name}: {exc}")
    return fixtures


# ── Per-fixture benchmark ─────────────────────────────────────────────────────

async def _run_fixture(
    fixture: dict[str, Any],
    threshold: float,
    verbose: bool,
) -> dict[str, Any]:
    """Run the clustering algorithm on one fixture and return metrics."""
    alerts = fixture["alerts"]
    texts       = [a["text"] for a in alerts]
    true_labels = [a["group_id"] for a in alerts]
    fixture_id  = fixture.get("id", "unknown")
    expected_n  = fixture.get("expected_clusters")

    t0 = time.monotonic()
    embeddings = await _embed(texts)
    embed_ms = int((time.monotonic() - t0) * 1000)

    pred_labels = _cluster(embeddings, threshold)
    n_pred_clusters = len(set(l for l, indices in
        {l: [i for i, p in enumerate(pred_labels) if p == l] for l in set(pred_labels)}.items()
        if len(indices) >= 2) | {l for l in pred_labels
        if pred_labels.count(l) >= 2})
    # Simpler count: number of distinct labels with ≥2 members (true clusters, not singletons)
    label_counts: dict[int, int] = {}
    for l in pred_labels:
        label_counts[l] = label_counts.get(l, 0) + 1
    n_pred_clusters = len([l for l, c in label_counts.items() if c >= 2])

    pair_m = _pair_metrics(true_labels, pred_labels)
    cluster_m = _cluster_level_metrics(true_labels, pred_labels, embeddings)

    cluster_count_ok = (n_pred_clusters == expected_n) if expected_n is not None else None

    result = {
        "fixture_id":         fixture_id,
        "n_alerts":           len(alerts),
        "expected_clusters":  expected_n,
        "predicted_clusters": n_pred_clusters,
        "cluster_count_ok":   cluster_count_ok,
        "embed_ms":           embed_ms,
        **pair_m,
        **cluster_m,
    }

    if verbose:
        ok = "✓" if cluster_count_ok else ("?" if cluster_count_ok is None else "✗")
        print(f"\n  [{ok}] {fixture_id}")
        print(f"      alerts={len(alerts)}  expected={expected_n}  predicted={n_pred_clusters}")
        print(f"      P={pair_m['precision']:.2f}  R={pair_m['recall']:.2f}  "
              f"F1={pair_m['f1']:.2f}  FCR={pair_m['false_correlation_rate']:.2f}")
        print(f"      chaining_delta(avg={cluster_m['avg_chaining_delta']:.3f}  "
              f"max={cluster_m['max_chaining_delta']:.3f})")
        if cluster_m["over_clustered"]:
            print(f"      ⚠ over-clustered: {cluster_m['over_clustered']} group(s) incorrectly merged")
        if cluster_m["under_clustered"]:
            print(f"      ⚠ under-clustered: {cluster_m['under_clustered']} group(s) split")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark incident clustering quality")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Cosine similarity threshold (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--model",     default=EMBEDDING_MODEL,
                        help=f"sentence-transformers model name (default: {EMBEDDING_MODEL})")
    parser.add_argument("--out",       help="Write JSON results to this file")
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    if not FIXTURES_DIR.exists():
        print(f"[error] No cluster_fixtures/ directory found at {FIXTURES_DIR}")
        sys.exit(1)

    fixtures = _load_fixtures()
    if not fixtures:
        print(f"[error] No fixture files found in {FIXTURES_DIR}")
        sys.exit(1)

    # Override module-level model if --model was supplied
    global EMBEDDING_MODEL, _bench_model
    if args.model != EMBEDDING_MODEL:
        EMBEDDING_MODEL = args.model
        _bench_model = None  # force reload with new model name

    print(f"\nCluster Benchmark — model={EMBEDDING_MODEL}  threshold={args.threshold}  fixtures={len(fixtures)}")
    print("=" * 60)

    t0 = time.monotonic()
    results = []
    for fx in fixtures:
        r = await _run_fixture(fx, args.threshold, args.verbose)
        results.append(r)

    elapsed = time.monotonic() - t0

    # Aggregate
    n = len(results)
    avg_p   = sum(r["precision"]            for r in results) / n
    avg_r   = sum(r["recall"]               for r in results) / n
    avg_f1  = sum(r["f1"]                   for r in results) / n
    avg_fcr = sum(r["false_correlation_rate"] for r in results) / n
    avg_cd  = sum(r["avg_chaining_delta"]   for r in results) / n
    count_ok = sum(1 for r in results if r.get("cluster_count_ok") is True)
    count_total_with_expected = sum(1 for r in results if r.get("expected_clusters") is not None)

    over_total  = sum(r["over_clustered"]  for r in results)
    under_total = sum(r["under_clustered"] for r in results)

    print("\n" + "=" * 60)
    print("  CLUSTER BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Fixtures:              {n}")
    print(f"  Threshold:             {args.threshold}")
    print(f"  Cluster Count Correct: {count_ok}/{count_total_with_expected}")
    print(f"  Avg Precision:         {avg_p:.3f}")
    print(f"  Avg Recall:            {avg_r:.3f}")
    print(f"  Avg F1:                {avg_f1:.3f}")
    print(f"  False Correlation Rate:{avg_fcr:.3f}  (lower is better)")
    print(f"  Avg Chaining Delta:    {avg_cd:.3f}  (lower = less chaining risk)")
    print(f"  Over-clustered:        {over_total} fixture(s)")
    print(f"  Under-clustered:       {under_total} fixture(s)")
    print(f"  Total time:            {elapsed:.1f}s")
    print("=" * 60)

    # Threshold sweep hint
    if avg_fcr > 0.10:
        print(f"\n  ⚠ FCR={avg_fcr:.2f} is high — consider raising threshold above {args.threshold}")
    if avg_r < 0.70:
        print(f"\n  ⚠ Recall={avg_r:.2f} is low — consider lowering threshold below {args.threshold}")
    if avg_cd > 0.15:
        print(f"\n  ⚠ Chaining delta={avg_cd:.3f} — some clusters likely formed via chain links")

    summary = {
        "model":                 EMBEDDING_MODEL,
        "threshold":             args.threshold,
        "n_fixtures":            n,
        "cluster_count_accuracy": count_ok / count_total_with_expected if count_total_with_expected else None,
        "avg_precision":         round(avg_p, 4),
        "avg_recall":            round(avg_r, 4),
        "avg_f1":                round(avg_f1, 4),
        "avg_false_correlation_rate": round(avg_fcr, 4),
        "avg_chaining_delta":    round(avg_cd, 4),
        "over_clustered_total":  over_total,
        "under_clustered_total": under_total,
        "elapsed_s":             round(elapsed, 2),
        "per_fixture":           results,
    }

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(summary, indent=2))
        print(f"\n  Results written to {args.out}")

    return summary


if __name__ == "__main__":
    asyncio.run(main())
