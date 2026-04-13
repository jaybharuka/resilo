"""correlator.py — Cross-alert correlation and pattern detection.

Groups co-occurring alerts and identifies known failure patterns.
Called once per poll cycle before individual alert processing.
"""
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Known multi-alert patterns.  Keys are frozensets of alertname values.
_PATTERNS: dict[frozenset, str] = {
    frozenset({"HighCpuUsage", "HighLatency"}):          "overload",
    frozenset({"HighCpuUsage", "HighMemoryUsage"}):       "resource_exhaustion",
    frozenset({"HttpErrorRate", "AuthFailures"}):         "auth_system_issue",
    frozenset({"HttpErrorRate", "HighLatency"}):          "service_degradation",
    frozenset({"DiskSpaceHigh", "HighMemoryUsage"}):      "disk_pressure",
    frozenset({"HighCpuUsage", "HttpErrorRate"}):         "cpu_induced_errors",
}


def correlate_alerts(alerts: list[dict], time_window_seconds: int = 300) -> dict:
    """Group alerts that started within `time_window_seconds` and detect patterns.

    Args:
        alerts: Enriched alert list from fetch_alerts().
        time_window_seconds: How recently alerts must have started to be considered
            co-occurring. Default 300 s (5 min) — broad enough to catch related
            alerts that don't fire at the exact same second.

    Returns:
        {
          "correlated": bool,
          "pattern": str | None,        # named pattern or "multi_alert"
          "affected_services": [str],
          "co_occurring_alerts": [str],
        }

    Attaches a "correlation" key to each alert dict in-place so that
    analyze_alert can include it in the LLM context.
    """
    _no_correlation: dict = {
        "correlated": False, "pattern": None,
        "affected_services": [], "co_occurring_alerts": [],
    }

    if len(alerts) <= 1:
        return _no_correlation

    now = datetime.now(timezone.utc)
    recent: list[dict] = []

    for alert in alerts:
        starts_at = alert.get("startsAt", "")
        try:
            started = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
            if (now - started).total_seconds() <= time_window_seconds:
                recent.append(alert)
        except (ValueError, AttributeError):
            # Can't parse timestamp — include it conservatively
            recent.append(alert)

    if len(recent) < 2:
        return _no_correlation

    # Collect names and services from recent alerts
    alert_names: set[str] = set()
    services: set[str] = set()
    for alert in recent:
        labels = alert.get("labels", {})
        name = labels.get("alertname", "")
        svc = labels.get("service", labels.get("job", ""))
        if name:
            alert_names.add(name)
        if svc:
            services.add(svc)

    # Pattern matching — first match wins
    matched_pattern: str | None = None
    for pattern_set, pattern_name in _PATTERNS.items():
        if pattern_set.issubset(alert_names):
            matched_pattern = pattern_name
            break

    correlated = matched_pattern is not None or len(alert_names) > 1
    result: dict = {
        "correlated": correlated,
        "pattern": matched_pattern or ("multi_alert" if correlated else None),
        "affected_services": list(services),
        "co_occurring_alerts": list(alert_names),
    }

    if correlated:
        log.info(
            "Correlation detected | pattern=%s alerts=%s services=%s",
            result["pattern"], list(alert_names), list(services),
        )

    return result
