from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import MonitorStatus, MonitorType


@dataclass
class MonitorTarget:
    """
    Representa um alvo de monitoramento — imutável por convenção.
    Usamos dataclass (não dict) para ter tipagem estática e acesso por atributo.
    """
    id:               str
    name:             str
    host:             str
    branch:           str
    monitor_type:     MonitorType
    port:             Optional[int] = None
    interval_seconds: int           = 30
    timeout_seconds:  int           = 5


@dataclass
class MonitorResult:
    """
    Resultado de uma única verificação. Imutável após criação.
    O campo timestamp usa default_factory para nunca compartilhar a mesma instância.
    """
    target_id:        str
    status:           MonitorStatus
    response_time_ms: Optional[float]
    timestamp:        datetime        = field(default_factory=datetime.utcnow)
    error_message:    Optional[str]   = None
