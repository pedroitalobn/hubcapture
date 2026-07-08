"""Interface comum dos connectors + registry.

Cada fonte implementa o mesmo Protocol. Novas fontes entram registrando uma
instância — o core (normalização, cache-first) não muda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass
class RawRecord:
    """Registro cru de uma fonte, antes da normalização."""

    source_id: str
    id_externo: str
    raw: dict
    municipio_ibge: str | None = None
    endpoint: str | None = None
    extra: dict = field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    source_id: str

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        """Coleta registros crus de um município desde `since`."""
        ...

    async def health_check(self) -> bool:
        """True se a fonte está respondendo."""
        ...


_registry: dict[str, Connector] = {}


def register(connector: Connector) -> Connector:
    """Registra uma instância de connector pelo seu source_id."""
    _registry[connector.source_id] = connector
    return connector


def get_connector(source_id: str) -> Connector:
    if source_id not in _registry:
        raise KeyError(f"connector não registrado: {source_id!r}")
    return _registry[source_id]


def available_sources() -> list[str]:
    return sorted(_registry)
