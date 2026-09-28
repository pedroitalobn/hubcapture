"""Inscrição de Web Push de um navegador (§63).

Dado PESSOAL por-tenant (RLS `FOR ALL` por `usuario_id`). Cada navegador em que
o gestor clicou "ativar notificações" vira uma linha: o `endpoint` é a URL do
serviço de push do navegador (FCM, Mozilla, Apple) e `p256dh`/`auth` são as
chaves com que o payload é cifrado para ELE — sem elas o servidor de push
entrega uma caixa que ninguém abre.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk


class PushInscricao(Base):
    __tablename__ = "push_inscricoes"
    __table_args__ = (
        UniqueConstraint("usuario_id", "endpoint", name="uq_push_inscricoes_usuario_endpoint"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ultimo_envio_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
