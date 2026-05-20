import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..repositories.status_repository import StatusRepository
from ..repositories.log_repository import LogRepository
from .websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


def _serialize_result(r) -> dict:
    return {
        "target_id":        r.target_id,
        "status":           r.status,
        "response_time_ms": r.response_time_ms,
        "timestamp":        r.timestamp.isoformat(),
        "error_message":    r.error_message,
    }


def create_router(
    status_repo:    StatusRepository,
    log_repo:       LogRepository,
    ws_manager:     WebSocketManager,
    targets_config: list[dict],
) -> APIRouter:
    """
    Princípio de Inversão de Dependência: o router recebe suas dependências
    injetadas, não as instancia diretamente. Facilita testes unitários.
    """
    router = APIRouter()

    @router.get("/api/status")
    async def get_status():
        return {
            "summary": status_repo.get_summary(),
            "targets": [_serialize_result(r) for r in status_repo.get_all()],
        }

    @router.get("/api/logs")
    async def get_logs(n: int = 50):
        return {
            "logs": [_serialize_result(r) for r in log_repo.get_recent(n)],
        }

    @router.get("/api/targets")
    async def get_targets():
        return {"targets": targets_config}

    @router.get("/api/history")
    async def get_history():
        """
        Retorna os últimos 20 resultados de cada alvo para inicializar
        os sparklines no frontend sem esperar ciclos completos de monitoramento.
        """
        return {
            t["id"]: [
                {
                    "status":           r.status,
                    "response_time_ms": r.response_time_ms,
                    "timestamp":        r.timestamp.isoformat(),
                }
                for r in log_repo.get_by_target(t["id"], n=20)
            ]
            for t in targets_config
        }

    @router.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "ws_clients": ws_manager.active_connections,
        }

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                # Mantém a conexão viva aguardando dados do cliente
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception as exc:
            logger.warning("Conexão WS encerrada inesperadamente: %s", exc)
            ws_manager.disconnect(websocket)

    return router
