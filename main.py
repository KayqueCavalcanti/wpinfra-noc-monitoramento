import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.core.entities import MonitorResult, MonitorTarget
from backend.core.enums import MonitorType
from backend.repositories.log_repository import LogRepository
from backend.repositories.status_repository import StatusRepository
from backend.api.routes import create_router
from backend.api.websocket_manager import WebSocketManager
from backend.services.monitoring_engine import MonitoringEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_CONFIG_PATH  = Path("config.json")
_FRONTEND_DIR = Path("frontend")


def _load_targets(config: dict) -> list[MonitorTarget]:
    targets = []
    for item in config["targets"]:
        targets.append(
            MonitorTarget(
                id=item["id"],
                name=item["name"],
                host=item["host"],
                branch=item["branch"],
                monitor_type=MonitorType(item["monitor_type"]),
                port=item.get("port"),
                interval_seconds=item.get("interval_seconds", 30),
                timeout_seconds=item.get("timeout_seconds", 5),
            )
        )
    return targets


def build_app() -> FastAPI:
    raw_config = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    targets    = _load_targets(raw_config)

    status_repo = StatusRepository()
    log_repo    = LogRepository(maxlen=2000)
    ws_manager  = WebSocketManager()

    # Callback assíncrono injetado no engine.
    # Separa a responsabilidade: o engine não conhece WebSocket.
    async def on_result(result: MonitorResult) -> None:
        await ws_manager.broadcast({
            "event": "monitor_result",
            "data":  {
                "target_id":        result.target_id,
                "status":           result.status,
                "response_time_ms": result.response_time_ms,
                "timestamp":        result.timestamp.isoformat(),
                "error_message":    result.error_message,
            },
        })

    engine = MonitoringEngine(
        status_repo=status_repo,
        log_repo=log_repo,
        on_result=on_result,
    )
    for target in targets:
        engine.register_target(target)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Iniciando engine de monitoramento...")
        await engine.start()
        yield
        logger.info("Encerrando engine de monitoramento...")
        await engine.stop()

    app = FastAPI(
        title="WP Infra — NOC",
        description="Central de Monitoramento Multi-Filiais",
        version="1.0.0",
        lifespan=lifespan,
    )

    router = create_router(
        status_repo=status_repo,
        log_repo=log_repo,
        ws_manager=ws_manager,
        targets_config=raw_config["targets"],
    )
    app.include_router(router)

    # Arquivos estáticos (CSS, JS) servidos em /static
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_dashboard():
        return FileResponse(str(_FRONTEND_DIR / "index.html"))

    return app


app = build_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
