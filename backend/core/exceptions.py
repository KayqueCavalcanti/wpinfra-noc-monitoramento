class MonitorException(Exception):
    """Exceção base do domínio de monitoramento."""


class HostUnreachableError(MonitorException):
    """O host não respondeu à sonda ICMP."""


class PortClosedError(MonitorException):
    """A porta TCP recusou ou não aceitou a conexão."""


class MonitorTimeoutError(MonitorException):
    """A sonda excedeu o timeout configurado."""


class ConfigurationError(MonitorException):
    """Configuração inválida ou ausente."""
