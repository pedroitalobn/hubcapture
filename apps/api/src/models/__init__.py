"""Registro central dos models — importa todos para que `Base.metadata` os veja."""

from ..db.base import Base
from .alerta import Alerta
from .audit_log import AuditLog
from .configuracao import Configuracao
from .convite import Convite
from .favorito import Favorito
from .monitoramento import Monitoramento
from .municipio_interesse import MunicipioInteresse
from .pasta import Pasta, PastaProposta
from .plano import Plano
from .preferencias import PreferenciasUsuario
from .proposta import Proposta
from .proposta_embedding import PropostaEmbedding
from .repasse import Repasse
from .sync_run import SyncRun
from .usuario import Usuario

__all__ = [
    "Base",
    "Usuario",
    "MunicipioInteresse",
    "PreferenciasUsuario",
    "Proposta",
    "PropostaEmbedding",
    "Repasse",
    "Favorito",
    "Pasta",
    "PastaProposta",
    "Monitoramento",
    "Alerta",
    "SyncRun",
    "AuditLog",
    "Plano",
    "Convite",
    "Configuracao",
]
