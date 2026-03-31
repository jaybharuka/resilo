"""
HTTP client helper for propagating trace context to downstream services.

Ensures all outbound HTTP calls include trace context headers for distributed tracing.
"""

import aiohttp
from typing import Dict, Optional, Any
from trace_context import get_propagation_headers


async def make_traced_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> aiohttp.ClientResponse:
    """
    Make an HTTP request with automatic trace context propagation.
    
    Adds traceparent and X-Request-ID headers to outbound requests.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Target URL
        headers: Additional headers to include
        **kwargs: Additional arguments to pass to aiohttp.ClientSession
    
    Returns:
        aiohttp.ClientResponse
    
    Example:
        async with make_traced_request("GET", "http://api.example.com/data") as resp:
            data = await resp.json()
    """
    if headers is None:
        headers = {}
    
    # Add trace context headers
    trace_headers = get_propagation_headers()
    headers.update(trace_headers)
    
    async with aiohttp.ClientSession() as session:
        return await session.request(method, url, headers=headers, **kwargs)


def get_traced_headers(additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Get headers with trace context for outbound requests.
    
    Merges trace context headers with any additional headers provided.
    
    Args:
        additional_headers: Optional dict of additional headers to include
    
    Returns:
        Dict of headers including trace context
    
    Example:
        headers = get_traced_headers({"Authorization": "Bearer token"})
        response = requests.get("http://api.example.com/data", headers=headers)
    """
    headers = get_propagation_headers()
    
    if additional_headers:
        headers.update(additional_headers)
    
    return headers
