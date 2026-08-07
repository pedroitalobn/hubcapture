"""Registro central dos models — importa todos para que `Base.metadata` os veja."""

from ..db.base import Base
from .alerta import Alerta
from .audit_log import AuditLog
from .base_conhecimento import BaseConhecimento
from .configuracao import Configuracao
from .conformidade import Conformidade
from .contato import Contato
from .convite import Convite
from .favorito import Favorito
from .integracao_contatos import ContatoVinculo, IntegracaoContatos
from .monitoramento import Monitoramento, MonitoramentoBusca
from .municipio_interesse import MunicipioInteresse
from .obra import Obra
from .parecer import Parecer
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
    "MonitoramentoBusca",
    "Alerta",
    "SyncRun",
    "AuditLog",
    "Plano",
    "Convite",
    "Configuracao",
    "BaseConhecimento",
    "Conformidade",
    "Obra",
    "Parecer",
    "Contato",
    "IntegracaoContatos",
    "ContatoVinculo",
]
