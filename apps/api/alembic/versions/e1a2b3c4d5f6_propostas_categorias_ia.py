"""propostas.categorias_ia — as pílulas de categoria da proposta

Slugs da taxonomia fechada de `ai/categorias.py` (['saude','infraestrutura'…]).
Preenchidas pelo classificador determinístico no fim de toda coleta e refinadas
pela IA quando há credencial de LLM. São dado DERIVADO: ficam fora do upsert da
ingestão, para um re-sync da fonte não apagar a curadoria.

Revision ID: e1a2b3c4d5f6
Revises: b41c7de90a12
Create Date: 2026-08-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e1a2b3c4d5f6"
down_revision: str | None = "b41c7de90a12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "propostas",
        sa.Column("categorias_ia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("propostas", "categorias_ia")
