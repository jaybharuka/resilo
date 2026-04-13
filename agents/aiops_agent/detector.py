import logging
from datetime import datetime, timedelta, timezone

import httpx

from config import Config

log = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

_PROMETHEUS_QUERIES: dict[str, str] = {
    "cpu_usage_pct": (
        '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle",'
        'instance="{instance}"}[5m])) * 100)'
    ),
    "memory_usage_pct": (
        '(1 - (node_memory_MemAvailable_bytes{instance="{instance}"}'
        ' / node_memory_MemTotal_bytes{instance="{instance}"})) * 100'
    ),
    "disk_usage_pct": (
        '(1 - (node_filesystem_avail_bytes{instance="{instance}",mountpoint="/"}'
        ' / node_filesystem_size_bytes{instance="{instance}",mountpoint="/"})) * 100'
    ),
    "http_error_rate": (
        'sum(rate(http_requests_total{instance="{instance}",status=~"5.."}[5m]))'
        ' / sum(rate(http_requests_total{instance="{instance}"}[5m]))'
    ),
    "http_p99_latency_ms": (
        'histogram_quantile(0.99, sum by (le, instance)'
        ' (rate(http_request_duration_seconds_bucket{instance="{instance}"}[5m]))) * 1000'
    ),
}

# Authoritative healthy thresholds — remediator imports this.
HEALTHY_THRESHOLDS: dict[str, float] = {
    "cpu_usage_pct":       80.0,
    "memory_usage_pct":    85.0,
    "disk_usage_pct":      90.0,
    "http_error_rate":     0.05,
    "http_p99_latency_ms": 2000.0,
}


def metric_priority_for(alert_name: str) -> list[str]:
    """Return metrics in priority order for the given alert name."""
    name = alert_name.lower()
    if "cpu" in name:
        return ["cpu_usage_pct", "memory_usage_pct"]
    if "mem" in name or "memory" in name:
        return ["memory_usage_pct", "cpu_usage_pct"]
    if "disk" in name or "filesystem" in name:
        return ["disk_usage_pct"]
    if "http" in name or "latency" in name or "error" in name:
        return ["http_error_rate", "http_p99_latency_ms"]
    return list(HEALTHY_THRESHOLDS.keys())


# ── Public fetch / enrich ────────────────────────────────────────────────────

async def fetch_alerts(cfg: Config) -> list[dict]:
    """Return active, non-silenced warning/critical alerts enriched with Prometheus metrics."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{cfg.alertmanager_url}/api/v2/alerts",
            params={"silenced": "false", "inhibited": "false", "active": "true"},
        )
        r.raise_for_status()
        raw_alerts: list[dict] = r.json()

    actionable = [
        a for a in raw_alerts
        if a.get("labels", {}).get("severity", "info") in ("warning", "critical")
    ]

    seen: set[str] = set()
    deduped: list[dict] = []
    for alert in actionable:
        fp = alert.get("fingerprint", "")
        if fp and fp in seen:
            continue
        seen.add(fp)
        deduped.append(alert)

    deduped.sort(
        key=lambda a: _SEVERITY_ORDER.get(
            a.get("labels", {}).get("severity", "info"), 99
        )
    )

    enriched: list[dict] = []
    for alert in deduped:
        ctx = await _enrich(cfg, alert)
        enriched.append({**alert, "prometheus_context": ctx})

    log.info("Fetched %d actionable alerts (deduplicated)", len(enriched))
    return enriched


async def _enrich(cfg: Config, alert: dict) -> dict:
    instance = alert.get("labels", {}).get("instance", "")
    if not instance:
        return {}

    context: dict[str, float | None] = {}
    async with httpx.AsyncClient(timeout=10) as client:
        for metric, tmpl in _PROMETHEUS_QUERIES.items():
            query = tmpl.format(instance=instance)
            try:
                r = await client.get(
                    f"{cfg.prometheus_url}/api/v1/query",
                    params={"query": query},
                )
                results = r.json().get("data", {}).get("result", [])
                context[metric] = float(results[0]["value"][1]) if results else None
            except Exception as exc:
                log.debug("Prometheus query %s failed: %s", metric, exc)
                context[metric] = None

    return context


async def query_metric(cfg: Config, instance: str, metric: str) -> float | None:
    """Query a single metric for post-remediation validation."""
    tmpl = _PROMETHEUS_QUERIES.get(metric)
    if not tmpl or not instance:
        return None
    query = tmpl.format(instance=instance)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{cfg.prometheus_url}/api/v1/query",
                params={"query": query},
            )
            results = r.json().get("data", {}).get("result", [])
            return float(results[0]["value"][1]) if results else None
    except Exception as exc:
        log.debug("Validation query %s failed: %s", metric, exc)
        return None


# ── Time-series range helpers ────────────────────────────────────────────────

async def _query_range_stats(
    cfg: Config, query: str, minutes: int = 5
) -> dict | None:
    """Return {max, avg, min} for a PromQL query over the last `minutes` minutes.

    Returns None when Prometheus is unavailable or the query yields no data.
    """
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{cfg.prometheus_url}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": "30s"},
            )
            data = r.json().get("data", {}).get("result", [])
            if not data:
                return None
            values = [
                float(v[1])
                for series in data
                for v in series.get("values", [])
            ]
            if not values:
                return None
            return {
                "max": max(values),
                "avg": sum(values) / len(values),
                "min": min(values),
            }
    except Exception as exc:
        log.debug("Range stats query failed: %s", exc)
        return None


async def _query_range_max(cfg: Config, query: str, minutes: int = 5) -> float | None:
    """Return the maximum value over the last `minutes` minutes (backward compat)."""
    stats = await _query_range_stats(cfg, query, minutes)
    return stats["max"] if stats else None


# ── Alert trend classification ───────────────────────────────────────────────

async def classify_alert_trend(cfg: Config, alert: dict) -> str:
    """Classify the alert's metric trend over the last 5 minutes.

    Returns one of:
      "transient_spike"  — peak was high but value is back below threshold
      "sustained_issue"  — consistently above threshold
      "gradual_increase" — still rising (current > 5-min avg by >10%)
      "unknown"          — insufficient Prometheus data

    Only "sustained_issue" and "gradual_increase" warrant remediation.
    """
    instance = alert.get("labels", {}).get("instance", "")
    alert_name = alert.get("labels", {}).get("alertname", "")
    if not instance:
        return "unknown"

    for metric in metric_priority_for(alert_name)[:1]:  # check primary metric only
        tmpl = _PROMETHEUS_QUERIES.get(metric)
        threshold = HEALTHY_THRESHOLDS.get(metric)
        if not tmpl or threshold is None:
            continue

        query = tmpl.format(instance=instance)
        current = await query_metric(cfg, instance, metric)
        stats = await _query_range_stats(cfg, query, minutes=5)

        if current is None or not stats:
            return "unknown"

        range_max = stats["max"]
        range_avg = stats["avg"]

        # Metric never crossed the threshold in this window
        if range_max <= threshold:
            return "unknown"

        # Value is back below threshold → spike has passed
        if current < threshold:
            log.info(
                "Transient spike | alert=%s metric=%s peak=%.2f current=%.2f",
                alert_name, metric, range_max, current,
            )
            return "transient_spike"

        # Still above threshold and trending up → gradual increase
        if current > range_avg * 1.10:
            log.info(
                "Gradual increase | alert=%s metric=%s avg=%.2f current=%.2f",
                alert_name, metric, range_avg, current,
            )
            return "gradual_increase"

        # Persistently above threshold
        log.info(
            "Sustained issue | alert=%s metric=%s avg=%.2f current=%.2f",
            alert_name, metric, range_avg, current,
        )
        return "sustained_issue"

    return "unknown"


async def is_transient_spike(cfg: Config, alert: dict) -> bool:
    """Backward-compatible wrapper: True only for transient_spike classification."""
    return await classify_alert_trend(cfg, alert) == "transient_spike"
