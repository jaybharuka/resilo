from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

_MAX_HISTORY = 200


# ── Learning intelligence ────────────────────────────────────────────────────

@dataclass
class AlertIntelligence:
    """Per-alert-name statistics that guide future remediation ordering."""
    total_attempts: int = 0
    successful_resolutions: int = 0
    failed_resolutions: int = 0
    avg_resolution_time: float = 0.0
    action_stats: dict = field(default_factory=dict)   # action → {"success": int, "fail": int}
    last_successful_action: str = ""
    # Advanced learning signals
    rollback_count: int = 0                            # times an action caused metric regression
    effectiveness_score: float = 0.0                  # rolling weighted effectiveness (0-1)
    correlation_patterns: dict = field(default_factory=dict)  # pattern → occurrence_count


# ── Incident record ──────────────────────────────────────────────────────────

@dataclass
class IncidentRecord:
    fingerprint: str
    alert_name: str
    severity: str
    root_cause: str
    confidence: float
    impact: str
    remediation_results: list
    escalated: bool = False
    skipped_reason: str = ""
    # Lifecycle
    status: str = "OPEN"
    resolution_time: float | None = None
    actions_executed: list = field(default_factory=list)
    # Explainability + evaluation (populated after execution)
    explanation: dict = field(default_factory=dict)
    evaluation: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Store ────────────────────────────────────────────────────────────────────

class IncidentStore:
    """In-memory store for alert history, attempt counts, active-processing
    tracking, and per-alert-name learning intelligence."""

    def __init__(self) -> None:
        self._history: deque[IncidentRecord] = deque(maxlen=_MAX_HISTORY)
        self._attempts: dict[str, int] = defaultdict(int)
        self._active: set[str] = set()
        self._intel: dict[str, AlertIntelligence] = defaultdict(AlertIntelligence)

    # ── Existing API (unchanged) ─────────────────────────────────────────────

    def attempt_count(self, fingerprint: str) -> int:
        return self._attempts[fingerprint]

    def is_active(self, fingerprint: str) -> bool:
        return fingerprint in self._active

    def mark_active(self, fingerprint: str) -> None:
        self._active.add(fingerprint)

    def mark_inactive(self, fingerprint: str) -> None:
        self._active.discard(fingerprint)

    def record(self, rec: IncidentRecord) -> None:
        self._attempts[rec.fingerprint] += 1
        self._history.appendleft(rec)

    def history(self, limit: int = 50) -> list[dict]:
        return [vars(r) for r in list(self._history)[:limit]]

    def status(self) -> dict:
        return {
            "total_incidents": len(self._history),
            "tracked_fingerprints": len(self._attempts),
            "active_processing": list(self._active),
            "attempt_counts": dict(self._attempts),
        }

    # ── Learning API ─────────────────────────────────────────────────────────

    def record_success(self, alert_name: str, action: str, resolution_time: float) -> None:
        """Record that `action` successfully resolved an alert of type `alert_name`."""
        intel = self._intel[alert_name]
        intel.total_attempts += 1
        intel.successful_resolutions += 1
        n = intel.successful_resolutions
        intel.avg_resolution_time = (
            intel.avg_resolution_time * (n - 1) + resolution_time
        ) / n
        stats = intel.action_stats.setdefault(action, {"success": 0, "fail": 0})
        stats["success"] += 1
        intel.last_successful_action = action
        # Boost effectiveness score: faster resolution = higher boost
        speed_bonus = max(0.0, 1.0 - resolution_time / 300.0)  # caps at 0 after 5 min
        intel.effectiveness_score = min(
            1.0, intel.effectiveness_score * 0.9 + speed_bonus * 0.1
        )

    def record_failure(self, alert_name: str, action: str) -> None:
        """Record that `action` failed (or errored) for `alert_name`."""
        intel = self._intel[alert_name]
        intel.total_attempts += 1
        intel.failed_resolutions += 1
        stats = intel.action_stats.setdefault(action, {"success": 0, "fail": 0})
        stats["fail"] += 1
        # Decay effectiveness on failure
        intel.effectiveness_score = max(0.0, intel.effectiveness_score * 0.85)

    def record_rollback(self, alert_name: str, action: str) -> None:
        """Record a rollback — double penalty because the action worsened metrics."""
        intel = self._intel[alert_name]
        intel.rollback_count += 1
        stats = intel.action_stats.setdefault(action, {"success": 0, "fail": 0})
        stats["fail"] += 2  # 2× penalty for causing metric regression
        intel.total_attempts += 1
        intel.failed_resolutions += 1
        # Larger effectiveness decay for rollbacks
        intel.effectiveness_score = max(0.0, intel.effectiveness_score * 0.70)

    def record_correlation(self, alert_name: str, pattern: str) -> None:
        """Track which correlation patterns co-occur with this alert type."""
        intel = self._intel[alert_name]
        intel.correlation_patterns[pattern] = (
            intel.correlation_patterns.get(pattern, 0) + 1
        )

    def get_best_actions(self, alert_name: str) -> list[str]:
        """Return actions sorted best → worst by historical success rate.

        Actions with >2 failures are pushed to the end regardless of rate.
        Cost-aware secondary sorting is handled by the caller (reorder_steps).
        Returns [] when no history exists — caller keeps original LLM order.
        """
        intel = self._intel.get(alert_name)
        if not intel or not intel.action_stats:
            return []

        def _key(item: tuple[str, dict]) -> tuple[int, float]:
            action, stats = item
            total = stats["success"] + stats["fail"]
            rate = stats["success"] / total if total else 0.5
            bucket = 2 if stats["fail"] > 2 else 1
            return (bucket, -rate)

        return [a for a, _ in sorted(intel.action_stats.items(), key=_key)]

    def intelligence(self) -> dict:
        """Return learning stats — exposed via /agent/status."""
        return {name: vars(intel) for name, intel in self._intel.items()}
