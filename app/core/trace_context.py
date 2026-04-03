"""
Distributed request tracing with W3C Trace Context standard.

Propagates trace context across services for request correlation:
- traceparent: W3C standard trace ID format
- tracestate: Vendor-specific trace state
- X-Request-ID: Custom correlation ID (fallback)

Enables end-to-end request tracing across multiple services.
"""

import uuid
from contextvars import ContextVar
from typing import Dict, Optional

# Context variables for trace information
trace_id: ContextVar[str] = ContextVar("trace_id", default="")
span_id: ContextVar[str] = ContextVar("span_id", default="")
trace_flags: ContextVar[str] = ContextVar("trace_flags", default="01")  # sampled


def generate_trace_id() -> str:
    """Generate a W3C-compliant trace ID (32 hex characters)."""
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generate a W3C-compliant span ID (16 hex characters)."""
    return uuid.uuid4().hex[:16]


def parse_traceparent(traceparent: str) -> tuple:
    """
    Parse W3C traceparent header format: version-trace_id-span_id-trace_flags
    
    Example: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
    
    Returns: (trace_id, span_id, trace_flags) or (None, None, None) if invalid
    """
    try:
        parts = traceparent.split("-")
        if len(parts) != 4:
            return None, None, None
        version, tid, sid, flags = parts
        if version != "00":  # Only support version 0
            return None, None, None
        if len(tid) != 32 or len(sid) != 16 or len(flags) != 2:
            return None, None, None
        return tid, sid, flags
    except Exception:
        return None, None, None


def set_trace_context(trace_id_val: str, span_id_val: str, flags: str = "01") -> None:
    """Set the current request's trace context."""
    trace_id.set(trace_id_val)
    span_id.set(span_id_val)
    trace_flags.set(flags)


def get_trace_context() -> Dict[str, str]:
    """Get the current trace context as a dictionary."""
    return {
        "trace_id": trace_id.get(),
        "span_id": span_id.get(),
        "trace_flags": trace_flags.get(),
    }


def get_traceparent() -> str:
    """Get the current trace context as a W3C traceparent header value."""
    tid = trace_id.get()
    sid = span_id.get()
    flags = trace_flags.get()
    if not tid or not sid:
        return ""
    return f"00-{tid}-{sid}-{flags}"


def get_propagation_headers() -> Dict[str, str]:
    """
    Get headers to propagate trace context to downstream services.
    
    Returns dict with:
    - traceparent: W3C standard header
    - X-Request-ID: Custom correlation ID (for backward compatibility)
    """
    tid = trace_id.get()
    sid = span_id.get()
    flags = trace_flags.get()
    
    headers = {}
    
    if tid and sid:
        headers["traceparent"] = f"00-{tid}-{sid}-{flags}"
    
    # Also include X-Request-ID for backward compatibility
    if tid:
        headers["X-Request-ID"] = tid
    
    return headers


def init_trace_context(
    traceparent: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """
    Initialize trace context from incoming request headers.
    
    Priority:
    1. Parse traceparent header (W3C standard)
    2. Use X-Request-ID as trace ID (fallback)
    3. Generate new trace ID
    """
    tid = None
    sid = None
    flags = "01"
    
    # Try to parse W3C traceparent header
    if traceparent:
        tid, sid, flags = parse_traceparent(traceparent)
    
    # Fallback to X-Request-ID
    if not tid and request_id:
        tid = request_id
    
    # Generate new trace ID if not found
    if not tid:
        tid = generate_trace_id()
    
    # Always generate a new span ID for this service
    if not sid:
        sid = generate_span_id()
    
    set_trace_context(tid, sid, flags)
