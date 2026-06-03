"""One-shot threshold calibrator for all-MiniLM-L6-v2 against cluster fixtures."""
import sys, json, math
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES_DIR = ROOT / "cluster_fixtures"

from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")

fixtures = []
for p in sorted(FIXTURES_DIR.glob("*.json")):
    data = json.loads(p.read_text())
    if isinstance(data, list):
        fixtures.extend(data)
    else:
        fixtures.append(data)

all_alerts = []
for fx in fixtures:
    for a in fx["alerts"]:
        all_alerts.append({"text": a["text"], "group_id": a["group_id"], "fixture": fx["id"]})

texts = [a["text"] for a in all_alerts]
vecs = model.encode(texts, normalize_embeddings=True)

# pairwise similarities with same/different label
same_sims, diff_sims = [], []
for i in range(len(vecs)):
    for j in range(i+1, len(vecs)):
        s = float(np.dot(vecs[i], vecs[j]))
        if all_alerts[i]["group_id"] == all_alerts[j]["group_id"] and all_alerts[i]["fixture"] == all_alerts[j]["fixture"]:
            same_sims.append(s)
        else:
            diff_sims.append(s)

same_sims.sort()
diff_sims.sort()

def pct(lst, p):
    idx = int(len(lst) * p / 100)
    return lst[min(idx, len(lst)-1)]

print(f"SAME-group pairs: n={len(same_sims)}  min={same_sims[0]:.3f}  p25={pct(same_sims,25):.3f}  median={pct(same_sims,50):.3f}  p75={pct(same_sims,75):.3f}  max={same_sims[-1]:.3f}")
print(f"DIFF-group pairs: n={len(diff_sims)}  min={diff_sims[0]:.3f}  p25={pct(diff_sims,25):.3f}  median={pct(diff_sims,50):.3f}  p75={pct(diff_sims,75):.3f}  max={diff_sims[-1]:.3f}")

# find threshold that maximises F1 on pairs
print("\nThreshold sweep:")
best_f1, best_t = 0, 0
for t_int in range(30, 95, 3):
    t = t_int / 100
    tp = sum(1 for s in same_sims if s >= t)
    fp = sum(1 for s in diff_sims if s >= t)
    fn = sum(1 for s in same_sims if s < t)
    p = tp/(tp+fp) if (tp+fp) else 1.0
    r = tp/(tp+fn) if (tp+fn) else 1.0
    f1 = 2*p*r/(p+r) if (p+r) else 0
    fcr = fp/len(diff_sims) if diff_sims else 0
    marker = " <-- best" if f1 > best_f1 else ""
    print(f"  t={t:.2f}  P={p:.2f}  R={r:.2f}  F1={f1:.2f}  FCR={fcr:.2f}{marker}")
    if f1 > best_f1:
        best_f1, best_t = f1, t

print(f"\nRecommended threshold: {best_t:.2f}  (F1={best_f1:.2f})")
