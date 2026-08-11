"""propostas: soft delete (excluido_em) — zerar não apaga linha

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-11

`propostas` é CACHE GLOBAL e suas FKs são ON DELETE CASCADE — e cascade IGNORA
RLS. Um DELETE (do admin ou de uma zeragem por usuário) levava junto favoritos,
pastas, monitoramentos e alertas de QUALQUER usuário que acompanhasse aquele
município. Com `excluido_em`, zerar vira marcação: nada some do banco, a
curadoria de todo mundo sobrevive e a coleta seguinte ressuscita a linha.

O filtro de "não aparece" fica na CAMADA DE CONSULTA, não na policy de SELECT:
`INSERT ... ON CONFLICT DO UPDATE` valida a linha EXISTENTE contra a policy de
SELECT, então esconder por RLS deixaria a proposta zerada impossível de
ressuscitar — a coleta quebraria com violação de RLS em vez de reativar o
registro que a fonte ainda publica.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "propostas",
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
    )
    # o painel lê quase sempre "as não excluídas do meu território"
    op.create_index(
        "ix_propostas_ativas",
        "propostas",
        ["municipio_ibge"],
        postgresql_where=sa.text("excluido_em IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_propostas_ativas", table_name="propostas")
    op.drop_column("propostas", "excluido_em")
