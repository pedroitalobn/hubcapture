"""Registro central dos models — importa todos para que `Base.metadata` os veja."""

from ..db.base import Base
from .alerta import Alerta
from .audit_log import AuditLog
from .base_conhecimento import BaseConhecimento
from .configuracao import Configuracao
from .conformidade import Conformidade
from .contato import Contato
from .convite import Convite
from .demanda import Demanda
from .favorito import Favorito
from .helpdesk import (
    HelpdeskArtigo,
    HelpdeskCategoria,
    HelpdeskHint,
    HelpdeskMidia,
    HelpdeskModulo,
)
from .integracao_contatos import ContatoVinculo, IntegracaoContatos
from .monitoramento import Monitoramento, MonitoramentoBusca
from .municipio_interesse import MunicipioInteresse
from .obra import Obra
from .parecer import Parecer
from .pasta import Pasta, PastaProposta
from .plano import Plano
from .preferencias import PreferenciasUsuario
from .proposta import Proposta
from .proposta_documento import PropostaDocumento
from .proposta_embedding import PropostaEmbedding
from .proposta_emenda import PropostaEmenda
from .proposta_empenho import PropostaEmpenho
from .repasse import Repasse
from .sync_run import SyncRun
from .usuario import Usuario

__all__ = [
    "Alerta",
    "AuditLog",
    "Base",
    "BaseConhecimento",
    "Configuracao",
    "Conformidade",
    "Contato",
    "ContatoVinculo",
    "Convite",
    "Demanda",
    "Favorito",
    "HelpdeskArtigo",
    "HelpdeskCategoria",
    "HelpdeskHint",
    "HelpdeskMidia",
    "HelpdeskModulo",
    "IntegracaoContatos",
    "Monitoramento",
    "MonitoramentoBusca",
    "MunicipioInteresse",
    "Obra",
    "Parecer",
    "Pasta",
    "PastaProposta",
    "Plano",
    "PreferenciasUsuario",
    "Proposta",
    "PropostaDocumento",
    "PropostaEmbedding",
    "PropostaEmenda",
    "PropostaEmpenho",
    "Repasse",
    "SyncRun",
    "Usuario",
]
