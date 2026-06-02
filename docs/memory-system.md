# Semantic Incident Memory System

## Purpose

The memory system gives the investigation engine access to institutional knowledge: every resolved incident is stored and retrievable by semantic similarity so future investigations benefit from past ones.

---

## Storage

**Table:** `incident_memory`

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `org_id` | String | Tenant isolation |
| `title` | String | Alert title |
| `severity` | String | critical / warning / info |
| `category` | String | cpu / memory / disk / database / network / service |
| `metrics_snapshot` | JSON | {cpu, memory, disk, load_avg_1m, swap_percent} |
| `root_cause` | Text | Final RCA conclusion |
| `reasoning` | Text | Reasoning steps joined |
| `hypotheses` | JSON | All hypotheses with confidences |
| `recommended_action` | String | Action taken |
| `alert_id` | FK | Source alert |
| `agent_id` | String | Reporting agent |
| `embedding` | vector(768) | pgvector float array |
| `created_at` | Timestamp | Auto |

---

## Write Path

After every completed investigation:

```python
await MemoryStore.save(
    db, org_id, title, severity, category,
    metrics_snapshot, root_cause, reasoning,
    hypotheses, recommended_action, alert_id, agent_id
)
```

The embedding is computed from a concatenation of:
```
"{category} {title} {root_cause} cpu={cpu} mem={memory}"
```

Embedding model: Gemini `text-embedding-004` (768-dimensional). Falls back gracefully if embedding fails — row saved without vector, won't be retrieved by similarity search but is still stored.

---

## Read Path — Semantic Retrieval

```python
similar = await MemoryStore.find_similar(
    org_id, incident_type, metrics_snapshot, top_k=5
)
```

1. Build query string from current incident metrics + type
2. Embed via same model
3. pgvector `<=>` cosine distance query:
   ```sql
   SELECT *, (embedding <=> $query_vec) AS distance
   FROM incident_memory
   WHERE org_id = $org_id
   ORDER BY distance ASC
   LIMIT 5
   ```
4. Convert distance to similarity: `similarity = 1 - distance`
5. Filter: only return entries with `similarity >= 0.65`

Returns list of `{title, similarity, root_cause, recommended_action, hypotheses, created_at}`.

---

## Memory Usefulness Measurement

At investigation completion, the engine checks how many retrieved memories were actually referenced in the final RCA:

```python
memories_used = sum(
    1 for title in mem_titles
    if title and any(title[:40].lower() in ref.lower() for ref in rca.historical_matches)
)
```

Stored as `investigations.memories_used_in_reasoning`. Aggregate `usefulness_rate` in `/investigations/stats`:

```
usefulness_rate = memories_used_in_reasoning / memories_retrieved
```

---

## Cold Start

On a fresh install with no incident history, `find_similar` returns an empty list. The investigation engine handles this gracefully — Stage 2 is skipped, hypotheses are generated from metrics and logs alone.

After ~10 resolved incidents, semantic retrieval starts providing value. After ~50, calibration gap between correct/incorrect confidence predictions typically improves 15–25%.

---

## Embedding Coverage

```
GET /investigations/stats
→ embedded_entries / memory_entries = embedding_coverage
```

If coverage drops below 1.0, some memories lack embeddings (e.g. Gemini embed API was unavailable at save time). Re-embedding is not automatically retried — monitor via the stats endpoint.
