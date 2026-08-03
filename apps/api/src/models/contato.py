"""Agenda de contatos do usuário (por-tenant, RLS por `usuario_id`).

Diferente de `propostas`/`repasses`/`obras` (cache global de dado público), o
contato é dado PESSOAL do usuário: RLS FOR ALL por `usuario_id`, como `pastas`.

`arquivado` é tombstone: apagar de vez impediria propagar a remoção para os
provedores externos no próximo sync (o vínculo precisa sobreviver ao delete).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import uuid_pk

# de onde o contato entrou na base (manual ou provedor externo)
ORIGENS = ("manual", "google", "microsoft", "apple", "carddav", "vcard")


class Contato(Base):
    __tablename__ = "contatos"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    nome: Mapped[str] = mapped_column(String(255))
    sobrenome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # [{"tipo": "trabalho", "valor": "x@y.com"}] — múltiplos por contato
    emails: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    telefones: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    enderecos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # território: o contato também é lido pela lente do município (profile-centric)
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tags: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    origem: Mapped[str] = mapped_column(String(16), default="manual")
    # e-mail principal normalizado (ou telefone E.164, ou nome+org) — casamento
    # entre a agenda local e o que vem dos provedores. Não é único: gabinetes
    # compartilham e-mail/telefone entre pessoas diferentes.
    chave_dedup: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    arquivado: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
