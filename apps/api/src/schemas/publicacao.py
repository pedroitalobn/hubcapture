"""Schemas da conferência da publicação (o double-check no DOU, §56c)."""

from __future__ import annotations

from pydantic import BaseModel

from .proposta import PublicacaoRead


class EvidenciaPublicacao(BaseModel):
    """Uma prova, com o caminho para conferi-la fora do Hub.

    `tipo` diz de que natureza é: `campo` (o que a ficha da proposta declara),
    `documento` (o PDF da publicação anexado à proposta) e `dou` (o extrato na
    Seção 3, que é o ato). Evidência sem `url` continua valendo — só não é
    clicável.
    """

    tipo: str  # campo | documento | dou
    rotulo: str
    detalhe: str | None = None
    data: str | None = None
    url: str | None = None


class ConferenciaPublicacao(BaseModel):
    """Estado da ida ao DOU — "não consegui" nunca vira "não foi publicado"."""

    status: str = "ok"  # ok | erro | sem_termo | nao_consultado
    confirmado: bool = False
    #: o que foi procurado (NEs e o código do instrumento) — é o que se confere
    #: na mão quando o gestor discorda do resultado
    termos: list[str] = []
    erro: str | None = None


class PublicacaoPagina(BaseModel):
    """Resposta do endpoint: a leitura, as provas e o estado da conferência."""

    publicacao: PublicacaoRead
    evidencias: list[EvidenciaPublicacao] = []
    conferencia: ConferenciaPublicacao = ConferenciaPublicacao(status="nao_consultado")
