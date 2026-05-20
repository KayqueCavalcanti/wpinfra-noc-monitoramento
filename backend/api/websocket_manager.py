import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Gerencia conexões WebSocket ativas.

    Escolha de estrutura — set[WebSocket]:
      - connect():    O(1) — set.add() por hash
      - disconnect(): O(1) — set.discard() por hash
      - broadcast():  O(n) — enviar para n clientes é inevitável O(n)

    Por que set e não list?
    Com list, checar se uma conexão já existe seria O(n). Com set, é O(1).
    Além disso, set garante unicidade — impossível registrar a mesma
    conexão duas vezes, o que evitaria mensagens duplicadas.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("Cliente WS conectado. Total: %d", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        logger.info("Cliente WS desconectado. Total: %d", len(self._connections))

    async def broadcast(self, message: dict) -> None:
        """
        Envia mensagem para todos os clientes.
        Conexões mortas são coletadas e removidas em O(1) cada.
        """
        payload = json.dumps(message, default=str)
        stale: set[WebSocket] = set()

        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.add(ws)

        # Remoção em lote — set difference é O(len(stale))
        self._connections -= stale

    @property
    def active_connections(self) -> int:
        return len(self._connections)
