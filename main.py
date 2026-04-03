from config.env_validator import validate_environment

validate_environment()

from fastapi import FastAPI

from api import agents, alerts, auth, chat, health, metrics, stream, websocket
from config.logger import get_logger
from config.otel import setup_otel
from config.shutdown import register_signal_handlers
from app.api.runtime import seed_admin_user
from app.core.database import init_db, wait_for_db
logger = get_logger("resilo")
app = FastAPI(title="Resilo", version="1.0.0")
app.state.chat_state = chat.ChatState()

app.include_router(auth.router)
app.include_router(metrics.router)
app.include_router(alerts.router)
app.include_router(agents.router)
app.include_router(health.router)
app.include_router(websocket.router)
app.include_router(stream.router)
app.include_router(chat.router)

app.include_router(auth.legacy_router)
app.include_router(metrics.legacy_router)
app.include_router(alerts.legacy_router)
app.include_router(agents.legacy_router)
app.include_router(health.legacy_router)
app.include_router(websocket.legacy_router)
app.include_router(stream.legacy_router)
app.include_router(chat.legacy_router)

setup_otel("resilo-api")
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import-not-found]
    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    pass


@app.on_event("startup")
async def _register_shutdown_handlers() -> None:
    register_signal_handlers(app)


@app.on_event("startup")
async def _startup_db() -> None:
    await wait_for_db()
    await init_db()
    await seed_admin_user()

logger.info("Unified FastAPI app initialized")
