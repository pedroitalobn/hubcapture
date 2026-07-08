"""Municípios que o usuário acompanha (monitorado ou avulso).

É a base do escopo de RLS de `propostas`: o usuário só enxerga propostas de
municípios que estão aqui. A consulta-avulsa insere `modo='avulso'` para que o
próprio usuário veja o resultado que acabou de buscar.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk

MODOS = ("monitorado", "avulso")


class MunicipioInteresse(Base):
    __tablename__ = "municipios_interesse"
    __table_args__ = (
        UniqueConstraint("usuario_id", "ibge", name="uq_municipios_usuario_ibge"),
        CheckConstraint("modo in ('monitorado','avulso')", name="ck_municipios_modo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    ibge: Mapped[str] = mapped_column(String(7), index=True)
    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    modo: Mapped[str] = mapped_column(String(12), default="monitorado")
    created_at: Mapped[datetime] = created_at_col()
