"""
Integration adapters for Resilo.

Provides webhook handlers and adapters for external monitoring platforms
(Datadog, Prometheus, etc.) to feed alerts into the remediation pipeline.
"""

from app.integrations.datadog import router as datadog_router
from app.integrations.prometheus import router as prometheus_router

__all__ = ["datadog_router", "prometheus_router"]
