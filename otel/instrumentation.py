"""
OpenTelemetry instrumentation for AIOps Bot API server.

Install dependencies:
    pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc \
                opentelemetry-instrumentation-flask opentelemetry-instrumentation-requests

Call setup_tracing(app) once at Flask app startup before the first request.
"""

import os
import logging

logger = logging.getLogger("aiops.otel")

OTEL_ENABLED = False


def setup_tracing(app):
    """
    Initialise OpenTelemetry tracing and wire it into the Flask app.
    Falls back silently if OTEL packages are not installed so the server
    still starts without them.
    """
    global OTEL_ENABLED

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
    except ImportError:
        logger.warning(
            "OpenTelemetry packages not installed — tracing disabled. "
            "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc "
            "opentelemetry-instrumentation-flask opentelemetry-instrumentation-requests"
        )
        return

    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    service_name = os.getenv("OTEL_SERVICE_NAME", "aiops-bot")

    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Auto-instrument all Flask routes and outbound requests
    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()

    OTEL_ENABLED = True
    logger.info("OpenTelemetry tracing enabled — sending to %s", otel_endpoint)


def get_tracer(name: str = "aiops.manual"):
    """Return a tracer for manual span creation."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


class _NoopTracer:
    """Fallback no-op tracer when OTEL is not installed."""

    def start_as_current_span(self, name, **kwargs):
        from contextlib import contextmanager

        @contextmanager
        def _noop():
            yield None

        return _noop()
