"""propostas.execucao — execução financeira do TransfereGov (empenhado etc.)

Revision ID: c7d8e9f0a1b2
Revises: b1f2c3d4e5a6
Create Date: 2026-07-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b1f2c3d4e5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # {valor_global, valor_empenhado, valor_liberado, valor_pago, saldo_conta,
    #  ano, qtd_transferencias, ente_recebedor, natureza_juridica,
    #  data_assinatura, data_inicio_vigencia, data_fim_vigencia}
    op.add_column(
        "propostas",
        sa.Column("execucao", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("propostas", "execucao")
