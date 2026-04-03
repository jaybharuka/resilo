"""
config/otel.py -- OpenTelemetry tracing and metrics setup.

Usage:
    from config.otel import setup_otel
    tracer = setup_otel("core-api")

If OTEL_EXPORTER_OTLP_ENDPOINT is set, spans are exported to the OTLP
collector (grpc by default).  Otherwise they are printed to stdout via
ConsoleSpanExporter for local development.

Environment variables:
    OTEL_EXPORTER_OTLP_ENDPOINT   e.g. http://otel-collector:4317
    OTEL_EXPORTER_OTLP_PROTOCOL   "grpc" (default) or "http/protobuf"
    OTEL_SERVICE_VERSION           optional semantic-convention field
"""
from __future__ import annotations

import os

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

_OTEL_INITIALIZED = False


def setup_otel(service_name: str):
    """
    Initialise a TracerProvider (and optionally a MeterProvider) for
    *service_name* and register it globally.

    Returns a opentelemetry.trace.Tracer for the caller, or a no-op object
    if the SDK is not installed.
    """
    if not _OTEL_AVAILABLE:
        # Return a silent no-op so callers need no guard.
        class _NoopTracer:
            def start_as_current_span(self, *a, **kw):
                from contextlib import contextmanager

                @contextmanager
                def _noop(*_, **__):
                    yield None

                return _noop()

            def start_span(self, *a, **kw):
                return None

        return _NoopTracer()

    global _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        return trace.get_tracer(service_name)

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: os.getenv("APP_VERSION", os.getenv("OTEL_SERVICE_VERSION", "0.0.1")),
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        }
    )

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").strip().lower()

    # ── Span exporter ────────────────────────────────────────────────────────
    if otlp_endpoint:
        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter as HTTPSpanExporter,
            )
            span_exporter = HTTPSpanExporter(endpoint=otlp_endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    else:
        span_exporter = ConsoleSpanExporter()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # ── Metric exporter (only when OTLP endpoint is configured) ─────────────
    if otlp_endpoint:
        try:
            if protocol == "http/protobuf":
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                    OTLPMetricExporter as HTTPMetricExporter,
                )
                metric_exporter = HTTPMetricExporter(endpoint=otlp_endpoint)
            else:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                    OTLPMetricExporter,
                )
                metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)

            try:
                export_interval_ms = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "30000"))
            except ValueError:
                export_interval_ms = 30000
            if export_interval_ms < 1000:
                export_interval_ms = 1000
            reader = PeriodicExportingMetricReader(
                metric_exporter,
                export_interval_millis=export_interval_ms,
            )
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
        except ImportError:
            pass  # metric exporter package not installed — tracing still works

    _OTEL_INITIALIZED = True

    return trace.get_tracer(service_name)
