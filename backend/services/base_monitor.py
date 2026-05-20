from abc import ABC, abstractmethod

from ..core.entities import MonitorTarget, MonitorResult


class BaseMonitor(ABC):
    """
    Princípio Open/Closed: esta abstração está fechada para modificação.
    Novos tipos de monitor (HTTP, DNS, SNMP) apenas estendem esta classe.

    Princípio de Substituição de Liskov: qualquer subclasse pode substituir
    BaseMonitor sem quebrar o contrato do MonitoringEngine.
    """

    @abstractmethod
    async def check(self, target: MonitorTarget) -> MonitorResult:
        """Executa uma única sonda e retorna o resultado. Nunca deve lançar exceção."""
        ...
