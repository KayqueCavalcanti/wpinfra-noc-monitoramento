from typing import Optional

from ..core.entities import MonitorResult
from ..core.enums import MonitorStatus


class StatusRepository:
    """
    Armazena o último resultado de cada alvo em memória.

    Escolha de estrutura — dict[str, MonitorResult]:
      - update(result):   O(1)  — atribuição de chave em dict
      - get(target_id):   O(1)  — lookup por hash
      - get_all():        O(n)  — iteração completa, inevitável
      - get_summary():    O(n)  — uma passagem pelos n alvos

    Se tivéssemos usado list[MonitorResult], encontrar o resultado de um
    alvo específico custaria O(n) a cada chamada (scan linear). Com dict,
    essa operação é O(1) independente do número de filiais monitoradas.
    """

    def __init__(self) -> None:
        self._store: dict[str, MonitorResult] = {}

    def update(self, result: MonitorResult) -> None:
        """Substitui (ou cria) o status do alvo. O(1)."""
        self._store[result.target_id] = result

    def get(self, target_id: str) -> Optional[MonitorResult]:
        """Retorna o último resultado do alvo ou None. O(1)."""
        return self._store.get(target_id)

    def get_all(self) -> list[MonitorResult]:
        """Retorna todos os resultados. O(n)."""
        return list(self._store.values())

    def get_summary(self) -> dict:
        """Conta totais por status em uma única passagem O(n)."""
        results = self.get_all()
        counts = {s: 0 for s in MonitorStatus}
        for r in results:
            counts[r.status] += 1
        return {
            "total":    len(results),
            "online":   counts[MonitorStatus.ONLINE],
            "offline":  counts[MonitorStatus.OFFLINE],
            "degraded": counts[MonitorStatus.DEGRADED],
            "unknown":  counts[MonitorStatus.UNKNOWN],
        }
