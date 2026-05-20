from collections import deque

from ..core.entities import MonitorResult


class LogRepository:
    """
    Buffer circular de logs usando collections.deque com maxlen.

    Por que deque e não list?

    list.append()  → O(1) amortizado  ✓
    list.pop(0)    → O(n) — todos os elementos se deslocam à esquerda ✗

    deque.append() → O(1) amortizado  ✓
    deque.popleft()→ O(1) — estrutura duplamente encadeada, sem deslocamento ✓

    Quando o deque atinge maxlen, a evicção do elemento mais antigo é
    automática e O(1). É a estrutura ideal para qualquer buffer circular.
    """

    def __init__(self, maxlen: int = 2000) -> None:
        self._buffer: deque[MonitorResult] = deque(maxlen=maxlen)

    def append(self, result: MonitorResult) -> None:
        """Adiciona ao final. Se cheio, o mais antigo é removido em O(1)."""
        self._buffer.append(result)

    def get_recent(self, n: int = 50) -> list[MonitorResult]:
        """
        Retorna os n eventos mais recentes em ordem decrescente.
        O(k) onde k = min(n, len(buffer)).
        """
        entries = list(self._buffer)
        return list(reversed(entries[-n:]))

    def get_by_target(self, target_id: str, n: int = 20) -> list[MonitorResult]:
        """
        Filtra por alvo. O(len(buffer)) — scan linear necessário
        pois deque não oferece índice secundário.
        """
        filtered = [r for r in self._buffer if r.target_id == target_id]
        return list(reversed(filtered[-n:]))
