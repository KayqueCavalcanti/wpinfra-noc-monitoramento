import asyncio
import logging
from typing import Awaitable, Callable

from ..core.entities import MonitorTarget, MonitorResult
from ..core.enums import MonitorType
from ..repositories.status_repository import StatusRepository
from ..repositories.log_repository import LogRepository
from .base_monitor import BaseMonitor
from .icmp_monitor import IcmpMonitor
from .tcp_monitor import TcpMonitor

logger = logging.getLogger(__name__)

ResultCallback = Callable[[MonitorResult], Awaitable[None]]


class MonitoringEngine:
    """
    Orquestra o monitoramento concorrente de todos os alvos.

    Modelo de concorrência:
    Cada alvo recebe sua própria asyncio.Task independente. As Tasks rodam
    no mesmo event loop sem criar threads — o asyncio multiplexa I/O via
    seletores do SO (epoll/kqueue/IOCP). Resultado: 100 alvos consomem
    recursos de ~1 thread, não de 100.

    Por que dict para _targets e _tasks?
    - register_target():  O(1) inserção
    - cancel por ID:      O(1) lookup em _tasks
    - get_all_targets():  O(n) — inevitável, mas ocorre só na inicialização
    """

    def __init__(
        self,
        status_repo: StatusRepository,
        log_repo:    LogRepository,
        on_result:   ResultCallback,
    ) -> None:
        self._status_repo = status_repo
        self._log_repo    = log_repo
        self._on_result   = on_result
        self._running     = False

        # Mapa de MonitorType → instância do monitor (Princípio D: depende da abstração)
        self._monitors: dict[MonitorType, BaseMonitor] = {
            MonitorType.ICMP: IcmpMonitor(),
            MonitorType.TCP:  TcpMonitor(),
        }

        # Estruturas de controle — O(1) por operação de ID
        self._targets: dict[str, MonitorTarget] = {}
        self._tasks:   dict[str, asyncio.Task]  = {}

    def register_target(self, target: MonitorTarget) -> None:
        """Registra um alvo. O(1) — inserção em dict."""
        self._targets[target.id] = target

    async def start(self) -> None:
        self._running = True
        logger.info("MonitoringEngine iniciado — %d alvos", len(self._targets))
        for target in self._targets.values():
            task = asyncio.create_task(
                self._monitor_loop(target),
                name=f"monitor-{target.id}",
            )
            self._tasks[target.id] = task

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        logger.info("MonitoringEngine encerrado")

    async def _monitor_loop(self, target: MonitorTarget) -> None:
        """
        Loop persistente por alvo. Dorme o tempo correto descontando a
        duração da sonda — mantém o intervalo real, não o intervalo + latência.
        """
        monitor = self._monitors[target.monitor_type]

        while self._running:
            tick_start = asyncio.get_event_loop().time()

            try:
                result = await monitor.check(target)
                self._status_repo.update(result)
                self._log_repo.append(result)
                await self._on_result(result)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Erro não tratado no loop de '%s': %s", target.id, exc)

            elapsed   = asyncio.get_event_loop().time() - tick_start
            sleep_for = max(0.0, target.interval_seconds - elapsed)
            await asyncio.sleep(sleep_for)
