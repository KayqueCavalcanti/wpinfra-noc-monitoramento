import asyncio
import time

from ..core.entities import MonitorTarget, MonitorResult
from ..core.enums import MonitorStatus
from ..core.exceptions import ConfigurationError
from .base_monitor import BaseMonitor

_DEGRADED_LATENCY_MS = 500.0


class TcpMonitor(BaseMonitor):
    """
    Verifica se uma porta TCP está aceitando conexões.

    A sonda estabelece o three-way handshake completo e fecha imediatamente.
    Isso detecta: porta aberta (ONLINE), porta fechada/recusada (OFFLINE),
    host inacessível (OFFLINE com timeout).

    Por que asyncio.open_connection e não socket bloqueante?
    Em asyncio, uma chamada bloqueante congela o event loop inteiro.
    asyncio.open_connection() é não-bloqueante: o event loop continua
    servindo outras corrotinas enquanto aguarda o TCP handshake.
    """

    async def check(self, target: MonitorTarget) -> MonitorResult:
        if target.port is None:
            raise ConfigurationError(
                f"TcpMonitor requer 'port' para o alvo '{target.id}'"
            )

        start = time.perf_counter()
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(target.host, target.port),
                timeout=target.timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            # Fecha a conexão adequadamente para não deixar sockets orphans
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass  # Alguns servidores fecham antes de nós — irrelevante aqui

            status = (
                MonitorStatus.DEGRADED
                if elapsed_ms > _DEGRADED_LATENCY_MS
                else MonitorStatus.ONLINE
            )
            return MonitorResult(
                target_id=target.id,
                status=status,
                response_time_ms=round(elapsed_ms, 2),
            )

        except asyncio.TimeoutError:
            return MonitorResult(
                target_id=target.id,
                status=MonitorStatus.OFFLINE,
                response_time_ms=None,
                error_message=f"TCP timeout após {target.timeout_seconds}s na porta {target.port}",
            )
        except (ConnectionRefusedError, OSError) as exc:
            return MonitorResult(
                target_id=target.id,
                status=MonitorStatus.OFFLINE,
                response_time_ms=None,
                error_message=f"Porta {target.port} recusada: {exc}",
            )
        except Exception as exc:
            return MonitorResult(
                target_id=target.id,
                status=MonitorStatus.UNKNOWN,
                response_time_ms=None,
                error_message=f"Erro inesperado: {exc}",
            )
