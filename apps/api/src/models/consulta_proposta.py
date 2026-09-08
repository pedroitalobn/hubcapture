"""Consultas de propostas — as abas do construtor de consultas (§61).

Entidade PRÓPRIA, por-tenant: cada aba é uma consulta salva (nome + recorte)
que o gestor monta na tela de Propostas. Ela não é estado de tela — vivia em
`localStorage`, então sumia ao trocar de navegador e não existia para nenhuma
outra superfície. Como `pastas`, é dado PESSOAL (RLS `FOR ALL` por
`usuario_id`), não cache público.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col, updated_at_col, uuid_pk


class ConsultaProposta(Base):
    __tablename__ = "consultas_propostas"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    nome: Mapped[str] = mapped_column(String(120))
    # O recorte guardado usa as MESMAS chaves dos query params de
    # `GET /proposals` (ver schemas/consultas.py): a aba é literalmente a
    # consulta, então o front não traduz nada para executá-la.
    filtros: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # posição na fileira de abas (o gestor arrasta/reordena)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = updated_at_col()
