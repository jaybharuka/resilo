"""
config/shutdown.py -- Graceful shutdown handling for all AIOps services.

Usage (inside a FastAPI startup event or at module level for Flask):
    from config.shutdown import register_signal_handlers
    register_signal_handlers(app)

WebSocket connection tracking:
    from config.shutdown import register_connection, unregister_connection
    register_connection(ws)    # on connect
    unregister_connection(ws)  # on disconnect
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import Any

logger = logging.getLogger(__name__)

# Mutable set of active WebSocket connections.
# register_connection / unregister_connection keep it current.
_active_connections: set[Any] = set()

# Set when a shutdown signal arrives so long-running coroutines can exit cleanly.
_shutdown_event: asyncio.Event | None = None


def register_connection(conn: Any) -> None:
    """Track an active WebSocket connection so it can be closed on shutdown."""
    _active_connections.add(conn)


def unregister_connection(conn: Any) -> None:
    """Remove a WebSocket connection from the tracked set."""
    _active_connections.discard(conn)


def get_shutdown_event() -> asyncio.Event:
    """Return the per-loop shutdown event, creating it if needed."""
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = asyncio.Event()
    return _shutdown_event


async def shutdown_handler(signal_name: str) -> None:
    """
    Async shutdown sequence:
    1. Signal all coroutines via the shutdown event.
    2. Close active WebSocket connections with a 1001 Going Away frame.
    3. Wait up to SHUTDOWN_TIMEOUT_SECONDS for in-flight requests to drain.
    4. Exit 0.
    """
    logger.info("Received %s — starting graceful shutdown", signal_name)
    get_shutdown_event().set()

    timeout = int(os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "30"))

    # Close active WebSocket connections cleanly.
    for conn in list(_active_connections):
        try:
            await conn.close(code=1001, reason="Server shutting down")
        except Exception:
            pass

    logger.info("Waiting up to %ds for in-flight requests to complete", timeout)
    await asyncio.sleep(timeout)
    logger.info("Shutdown complete")
    sys.exit(0)


def register_signal_handlers(app: Any = None) -> None:
    """
    Register SIGTERM and SIGINT handlers.

    - On Unix with a running event loop: uses loop.add_signal_handler() so the
      async shutdown_handler runs inside the event loop without blocking.
    - On Windows or when no loop is running (Flask): falls back to synchronous
      signal.signal() which exits cleanly on the first signal received.

    Call this from within a running event loop context (e.g. a FastAPI startup
    event) for the async path, or at module level for Flask (sync fallback).
    """
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown_handler(s.name)),
            )
        logger.info("Graceful shutdown handlers registered (SIGTERM, SIGINT)")
    except (NotImplementedError, RuntimeError):
        # Windows does not support loop.add_signal_handler; Flask has no running loop.
        def _sync_handler(signum: int, frame: Any) -> None:
            logger.info("Received signal %d — shutting down", signum)
            sys.exit(0)

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, _sync_handler)
        logger.info("Graceful shutdown handlers registered (sync fallback)")
