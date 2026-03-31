"""
Prometheus metrics collection for API monitoring.

Collects:
- Request latency histogram (per endpoint)
- Request counter (per endpoint, status code)
- Error rate counter
- Database query duration histogram
"""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
from fastapi import Request
from fastapi.responses import Response

# Request latency histogram (in seconds)
request_latency = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=["method", "endpoint", "status_code"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Request counter
request_count = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status_code"],
)

# Error counter
error_count = Counter(
    "http_errors_total",
    "Total HTTP errors (5xx)",
    labelnames=["method", "endpoint"],
)

# Database query duration histogram
db_query_duration = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    labelnames=["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)


async def metrics_middleware(request: Request, call_next):
    """
    Middleware to collect request metrics.
    Records latency, request count, and error count.
    """
    start_time = time.time()
    
    # Get endpoint path (normalize for metrics)
    endpoint = request.url.path
    method = request.method
    
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:
        status_code = 500
        raise
    finally:
        # Record metrics
        duration = time.time() - start_time
        
        request_latency.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).observe(duration)
        
        request_count.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()
        
        # Track errors (5xx status codes)
        if status_code >= 500:
            error_count.labels(
                method=method,
                endpoint=endpoint,
            ).inc()
    
    return response


def get_metrics():
    """
    Return Prometheus metrics in text format.
    Called by /metrics endpoint.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
