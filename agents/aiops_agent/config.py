import json
import os
from dataclasses import dataclass, field

# ── Service criticality policy ───────────────────────────────────────────────
ALLOWED_ACTIONS_BY_CRITICALITY: dict[str, frozenset[str]] = {
    "high": frozenset({"notify_only", "create_incident"}),
    "medium": frozenset({
        "notify_only", "create_incident", "silence_alert",
        "restart_service", "scale_deployment",
    }),
    "low": frozenset({
        "notify_only", "create_incident", "silence_alert",
        "restart_service", "scale_deployment", "run_script",
    }),
}

_DEFAULT_CRITICALITY: dict[str, str] = {
    "auth-service":    "high",
    "payment-service": "high",
    "api-gateway":     "medium",
    "worker":          "low",
}

# ── Action cost policy ───────────────────────────────────────────────────────
# Used for cost-aware step ordering when success rates are similar.
# Higher = more disruptive / expensive.
ACTION_COST: dict[str, int] = {
    "notify_only":      0,
    "silence_alert":    0,
    "create_incident":  0,
    "scale_deployment": 3,
    "restart_service":  1,
    "run_script":       5,
}


# ── Config dataclass ─────────────────────────────────────────────────────────

@dataclass
class Config:
    nvidia_api_key: str
    nvidia_base_url: str
    llm_model: str
    alertmanager_url: str
    prometheus_url: str
    poll_interval: int
    max_remediation_attempts: int
    confidence_threshold: float
    step_delay_seconds: int
    verify_delay_seconds: int
    dry_run: bool
    service_criticality: dict = field(default_factory=dict)


def load_config() -> Config:
    raw = os.getenv("SERVICE_CRITICALITY", "")
    try:
        criticality = json.loads(raw) if raw else _DEFAULT_CRITICALITY
    except json.JSONDecodeError:
        criticality = _DEFAULT_CRITICALITY

    return Config(
        nvidia_api_key=os.environ["NVIDIA_API_KEY"],
        nvidia_base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        llm_model=os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct"),
        alertmanager_url=os.getenv("ALERTMANAGER_URL", "http://localhost:9093"),
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
        poll_interval=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
        max_remediation_attempts=int(os.getenv("MAX_REMEDIATION_ATTEMPTS", "3")),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.6")),
        step_delay_seconds=int(os.getenv("STEP_DELAY_SECONDS", "2")),
        verify_delay_seconds=int(os.getenv("VERIFY_DELAY_SECONDS", "10")),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        service_criticality=criticality,
    )
