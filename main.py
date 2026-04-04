from config.env_validator import validate_environment

validate_environment()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api import agents, alerts, auth, chat, health, metrics, stream, websocket
from config.logger import get_logger
from config.otel import setup_otel
from config.shutdown import register_signal_handlers
from app.api.runtime import RealtimeHub, seed_admin_user
from app.core.database import init_db, wait_for_db
logger = get_logger("resilo")
app = FastAPI(title="Resilo", version="1.0.0")
app.state.chat_state = chat.ChatState()
app.state.realtime_hub = RealtimeHub()
app.state.shutting_down = False
app.state.active_requests = 0

app.include_router(auth.router)
app.include_router(metrics.router)
app.include_router(alerts.router)
app.include_router(agents.router)
app.include_router(health.router)
app.include_router(websocket.router)
app.include_router(stream.router)
app.include_router(chat.router)

setup_otel("resilo-api")
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import-not-found]
    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    pass


@app.on_event("startup")
async def _register_shutdown_handlers() -> None:
    register_signal_handlers(app)


@app.middleware("http")
async def request_lifecycle_guard(request: Request, call_next):
    if getattr(app.state, "shutting_down", False):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "server_shutting_down", "detail": "Server is shutting down"},
        )

    app.state.active_requests += 1
    try:
        return await call_next(request)
    finally:
        app.state.active_requests = max(0, app.state.active_requests - 1)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled API error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "internal_server_error", "detail": "Unexpected server error"},
    )


@app.on_event("startup")
async def _startup_db() -> None:
    await wait_for_db()
    await init_db()
    await seed_admin_user()

logger.info("Unified FastAPI app initialized")
