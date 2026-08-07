"""propostas.dados_fonte — registro-fonte COMPLETO (todos os campos do site)

Guarda o RawRecord.raw inteiro (ex.: {plano_acao: {...}, programa: {...}}) para
a tela de detalhe exibir "todos os dados" da proposta, iguais ao site de origem —
sem depender do subconjunto curado em `execucao`.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "propostas",
        sa.Column("dados_fonte", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("propostas", "dados_fonte")
