"""monitoramentos.origem — favoritar já é acompanhar

Revision ID: b2c3d4e5f8a0
Revises: a1b2c3d4e5f7
Create Date: 2026-08-20

A proposta favoritada passa a gerar alerta quando o cron encontra novidade
nela: a varredura cria o monitoramento implícito (`origem='favorito'`) para
toda favorita que ainda não tem um. A coluna distingue esse acompanhamento
do que o gestor ligou na mão — inclusive na tela, que precisa dizer por que
aquela proposta está sendo acompanhada.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f8a0"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoramentos",
        sa.Column(
            "origem",
            sa.String(length=16),
            nullable=False,
            server_default="manual",
        ),
    )


def downgrade() -> None:
    op.drop_column("monitoramentos", "origem")
