"""Chaves de API de parceiros (§67). Nível-plataforma — sem RLS por-tenant.

A chave pertence a um USUÁRIO (a conta do parceiro): quem entra com ela é
aquele usuário, com o RLS de sempre — o parceiro só enxerga o território da
conta dele. Da chave em si guardamos só o HASH (sha256) e um prefixo para
reconhecê-la na tela; o texto inteiro aparece uma única vez, na criação.

`api_uso` agrega o consumo por chave e por dia (requisições atendidas e
bloqueadas pelo limite) — é a base para cobrar e para conversar com o parceiro.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk

AMBIENTES = ("live", "test")
ESCOPOS = ("leitura", "escrita")


class ApiChave(Base):
    __tablename__ = "api_chaves"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    nome: Mapped[str] = mapped_column(String(120))
    # começo da chave (ex.: "hub_live_a1B2c3"), para reconhecê-la na lista
    prefixo: Mapped[str] = mapped_column(String(32))
    # sha256 hex da chave inteira — a chave em texto nunca é gravada
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ambiente: Mapped[str] = mapped_column(String(8))
    escopo: Mapped[str] = mapped_column(String(16), default="leitura")
    # sobrepõem o plano/padrão quando preenchidos
    limite_por_minuto: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limite_por_dia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criada_por: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class ApiUso(Base):
    __tablename__ = "api_uso"

    chave_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("api_chaves.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dia: Mapped[date] = mapped_column(Date, primary_key=True)
    requisicoes: Mapped[int] = mapped_column(Integer, default=0)
    bloqueadas: Mapped[int] = mapped_column(Integer, default=0)
