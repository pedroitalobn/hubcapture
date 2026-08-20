"""critérios de alerta nos monitoramentos (+ snapshot da proposta monitorada)

Revision ID: a1b2c3d4e5f7
Revises: a4b5c6d7e8f9
Create Date: 2026-08-19

Monitorar era tudo-ou-nada: qualquer alteração virava alerta. `criterios`
guarda a escolha do usuário (multi-select) e `snapshot` guarda a última
fotografia da proposta, que é contra o que a varredura compara para saber O QUE
mudou. NULL em `criterios` = padrões do registro — nenhum monitoramento
existente deixa de receber o que já recebia.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoramentos",
        sa.Column("criterios", postgresql.ARRAY(postgresql.TEXT()), nullable=True),
    )
    op.add_column(
        "monitoramentos",
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "monitoramentos",
        sa.Column("ultimo_alerta_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "monitoramentos_busca",
        sa.Column("criterios", postgresql.ARRAY(postgresql.TEXT()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitoramentos_busca", "criterios")
    op.drop_column("monitoramentos", "ultimo_alerta_em")
    op.drop_column("monitoramentos", "snapshot")
    op.drop_column("monitoramentos", "criterios")
