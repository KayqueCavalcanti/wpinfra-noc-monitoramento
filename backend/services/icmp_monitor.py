import asyncio
import platform
import time

from ..core.entities import MonitorTarget, MonitorResult
from ..core.enums import MonitorStatus
from .base_monitor import BaseMonitor

# Limiar em ms acima do qual o status passa de ONLINE para DEGRADED
_DEGRADED_LATENCY_MS = 200.0


class IcmpMonitor(BaseMonitor):
    """
    Sonda ICMP via subprocess do sistema operacional.

    Por que subprocess e não raw socket?
    Raw ICMP exige privilégios de root/administrador. Usar o comando
    nativo `ping` funciona em qualquer contexto sem elevação de permissão,
    garantindo portabilidade entre Windows, Linux e macOS.

    Tratamento de erros em camadas:
      1. asyncio.TimeoutError  → host demorou mais que timeout_seconds
      2. returncode != 0       → host não respondeu ao ICMP
      3. Exception genérica    → erro inesperado de sistema (UNKNOWN)
    """

    async def check(self, target: MonitorTarget) -> MonitorResult:
        start = time.perf_counter()
        try:
            responded = await asyncio.wait_for(
                self._ping(target.host),
                timeout=target.timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            if not responded:
                return MonitorResult(
                    target_id=target.id,
                    status=MonitorStatus.OFFLINE,
                    response_time_ms=None,
                    error_message="Host não respondeu ao ICMP",
                )

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
                error_message=f"Timeout após {target.timeout_seconds}s",
            )
        except Exception as exc:
            return MonitorResult(
                target_id=target.id,
                status=MonitorStatus.UNKNOWN,
                response_time_ms=None,
                error_message=f"Erro inesperado: {exc}",
            )

    @staticmethod
    async def _ping(host: str) -> bool:
        """Retorna True se o host respondeu ao ping."""
        is_windows = platform.system().lower() == "windows"
        cmd = (
            ["ping", "-n", "1", "-w", "1000", host]
            if is_windows
            else ["ping", "-c", "1", "-W", "1", host]
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        return proc.returncode == 0
