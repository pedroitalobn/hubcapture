"""Documentos digitalizados da proposta — o ARQUIVO que comprova o ato.

Quando a fonte diz "Publicado", o gestor quer o documento: é o que ele anexa
ao processo, manda para o jurídico e leva para a reunião. A tela dizia
"Publicado" e parava ali (ponto 10 do feedback de 28/08); o PDF estava a três
cliques dentro do portal, na "Lista de Documentos Digitalizados".

É 1-N (a proposta acumula publicação, ofício, contrato de repasse, projeto
básico), então é tabela e não coluna. Guardamos a REFERÊNCIA, nunca os bytes:
o arquivo é público na fonte, pesa, muda de versão, e cachear binário de
terceiro cria um acervo que ninguém pediu para manter.

Cache global, RLS só-SELECT por município como `pareceres`/`proposta_empenhos`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import updated_at_col, uuid_pk


class PropostaDocumento(Base):
    __tablename__ = "proposta_documentos"
    __table_args__ = (
        UniqueConstraint(
            "fonte", "id_externo", name="uq_proposta_documentos_fonte_id_externo"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(32), index=True)
    id_externo: Mapped[str] = mapped_column(String(128))

    # elos com a proposta — a consulta é pelo idProposta interno do SIconv
    numero_proposta: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    id_proposta_fonte: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)

    # o documento
    nome: Mapped[str] = mapped_column(Text)
    #: espécie derivada do nome (publicacao|oficio|contrato|projeto|termo|outro)
    tipo: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    data_upload: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    #: URL de download na FONTE (o Hub não hospeda o arquivo)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proveniencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = updated_at_col()
    cache_atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
