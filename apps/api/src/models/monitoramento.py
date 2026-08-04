"""Monitoramentos: proposta-chave (mudança) e busca (futuras propostas)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk


class Monitoramento(Base):
    __tablename__ = "monitoramentos"
    __table_args__ = (
        UniqueConstraint("usuario_id", "proposta_id", name="uq_monitoramentos_usuario_proposta"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    proposta_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("propostas.id", ondelete="CASCADE")
    )
    ativo: Mapped[bool] = mapped_column(default=True)
    canais: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class MonitoramentoBusca(Base):
    """Monitoramento de FUTURAS propostas: vigia um município (e opcionalmente
    uma área/fonte) e gera alerta 'nova_proposta' quando algo novo aparece —
    notificável por painel/email/WhatsApp conforme `canais`."""

    __tablename__ = "monitoramentos_busca"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            "municipio_ibge",
            "area",
            "fonte",
            name="uq_monitoramentos_busca_escopo",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    municipio_ibge: Mapped[str] = mapped_column(String(7))
    area: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fonte: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ativo: Mapped[bool] = mapped_column(default=True)
    canais: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    ultimo_alerta_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()
