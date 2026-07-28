"""propostas: exercício (ano) e descrição

O painel de captação abre no ano corrente, então o exercício precisa ser uma
coluna filtrável/indexável — antes só existia dentro de `execucao` (jsonb), que
só o painel SERPRO preenche, deixando as demais fontes sem ano nenhum. A
descrição entra ao lado do objeto porque as fontes preenchem ora um, ora outro.

Revision ID: d5e6f7a8b9c0
Revises: c7d8e9f0a1b2
Create Date: 2026-07-28 15:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("propostas", sa.Column("descricao", sa.Text(), nullable=True))
    op.add_column("propostas", sa.Column("ano", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_propostas_ano"), "propostas", ["ano"], unique=False)

    # Backfill do que já está em cache, na mesma ordem do normalizador. O padrão
    # evita grupo de captura (`substring` devolveria só o grupo) e dois-pontos
    # (`(?:...)` viraria bind param ao passar pelo SQLAlchemy).
    op.execute("""
        UPDATE propostas
           SET ano = substring(numero_proposta from '[12][0-9]{3}')::int
         WHERE ano IS NULL
           AND substring(numero_proposta from '[12][0-9]{3}') IS NOT NULL
        """)
    op.execute("""
        UPDATE propostas
           SET ano = substring(execucao->>'ano' from '[12][0-9]{3}')::int
         WHERE ano IS NULL
           AND substring(execucao->>'ano' from '[12][0-9]{3}') IS NOT NULL
        """)
    op.execute("""
        UPDATE propostas
           SET ano = EXTRACT(YEAR FROM data_atualizacao_fonte)::int
         WHERE ano IS NULL AND data_atualizacao_fonte IS NOT NULL
        """)


def downgrade() -> None:
    op.drop_index(op.f("ix_propostas_ano"), table_name="propostas")
    op.drop_column("propostas", "ano")
    op.drop_column("propostas", "descricao")
