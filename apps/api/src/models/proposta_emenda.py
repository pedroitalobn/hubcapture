"""Emenda parlamentar que financia a proposta — e o parlamentar AUTOR.

Entidade própria (não coluna) porque é 1-N: um plano de ação pode ser composto
por mais de uma emenda, cada uma com seu autor e seus valores. A chave de
consulta é a da PROPOSTA na fonte (id do plano de ação / nº da proposta), como
em `pareceres`.

Não confundir com o eixo "recebidos" (§26b): lá a emenda é lente sobre
`repasses` (dinheiro que JÁ caiu, do Portal da Transparência). Aqui é a origem
da captação — de quem é a emenda que banca esta proposta.

Cache global, RLS só-SELECT por município (igual a propostas/pareceres); o
`municipio_ibge` é desnormalizado para a policy recortar sem join, e nulo é
visível porque a consulta por número de plano nem sempre resolve o município.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import updated_at_col, uuid_pk


class PropostaEmenda(Base):
    __tablename__ = "proposta_emendas"
    __table_args__ = (
        UniqueConstraint(
            "fonte", "id_externo", name="uq_proposta_emendas_fonte_id_externo"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(32), index=True)
    id_externo: Mapped[str] = mapped_column(String(128))

    # elos com a proposta — o que a fonte usa como chave de consulta
    numero_plano_acao: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    numero_proposta: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)

    # a emenda
    codigo_emenda: Mapped[str | None] = mapped_column(String(64), nullable=True)
    numero_emenda: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ano: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_emenda: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # o autor — é com o gabinete dele que o gestor fala
    parlamentar: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    partido: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uf_parlamentar: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cargo_parlamentar: Mapped[str | None] = mapped_column(String(64), nullable=True)
    codigo_parlamentar: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # dinheiro
    valor: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_empenhado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    funcao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url_origem: Mapped[str | None] = mapped_column(Text, nullable=True)

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
