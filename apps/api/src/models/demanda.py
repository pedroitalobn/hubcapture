"""Central de demandas da Assessoria (por-tenant, RLS por `usuario_id`).

Ponto 20 do feedback: "colocar na parte Assessoria uma central de recebimento de
demandas". Hoje a Assessoria só abre o WhatsApp — o pedido some na conversa e
ninguém sabe o que ficou pendente. A demanda registrada tem estado, histórico e
dono, então o gestor acompanha e a assessoria trabalha uma FILA.

É dado do usuário (como `pastas` e `contatos`), não cache público: RLS FOR ALL
por `usuario_id`. A administração enxerga a fila inteira pela sessão de
plataforma — é ela que responde.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk

# Ciclo de vida da demanda. "aberta" nasce com o pedido; "resolvida" é o fim.
SITUACOES = ("aberta", "em_andamento", "resolvida", "cancelada")

# De onde veio o pedido — a mesma demanda pode chegar pelo painel ou pelo zap.
ORIGENS = ("painel", "whatsapp", "email")


class Demanda(Base):
    __tablename__ = "demandas"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    assunto: Mapped[str] = mapped_column(String(255))
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # território: a demanda quase sempre é sobre um município do perfil
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    # proposta relacionada, quando o pedido nasce de uma tela de proposta.
    # SET NULL (e não CASCADE): a proposta é cache global e pode ser zerada —
    # levar a demanda do gestor junto seria perder o pedido dele por causa de
    # uma recoleta.
    proposta_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("propostas.id", ondelete="SET NULL"), nullable=True
    )
    situacao: Mapped[str] = mapped_column(String(16), default="aberta", index=True)
    origem: Mapped[str] = mapped_column(String(16), default="painel")
    # [{em, autor, texto, situacao}] — o histórico da conversa, em ordem
    historico: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    resolvida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
