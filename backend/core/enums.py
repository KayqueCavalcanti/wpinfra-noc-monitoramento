from enum import Enum


class MonitorStatus(str, Enum):
    """
    Herda de str para serialização JSON automática.
    MonitorStatus.ONLINE == "ONLINE" → True
    """
    ONLINE   = "ONLINE"
    OFFLINE  = "OFFLINE"
    DEGRADED = "DEGRADED"   # Host responde, mas latência acima do limiar
    UNKNOWN  = "UNKNOWN"    # Ainda não verificado


class MonitorType(str, Enum):
    ICMP = "ICMP"
    TCP  = "TCP"
