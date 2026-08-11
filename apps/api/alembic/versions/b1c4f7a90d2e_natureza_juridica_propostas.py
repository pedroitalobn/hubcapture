"""natureza juridica das propostas

Revision ID: b1c4f7a90d2e
Revises: 66ddf34515bd
Create Date: 2026-08-11 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1c4f7a90d2e'
down_revision: Union[str, None] = '66ddf34515bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'propostas', sa.Column('natureza_juridica', sa.String(length=32), nullable=True)
    )
    op.add_column(
        'propostas',
        sa.Column('natureza_juridica_descricao', sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f('ix_propostas_natureza_juridica'),
        'propostas',
        ['natureza_juridica'],
        unique=False,
    )

    # Backfill do cache existente: as fontes fundo a fundo repassam ao próprio
    # ente municipal; o restante fica 'outros' até a próxima sync reclassificar
    # com os dados do proponente (ingestion/natureza_juridica.py).
    op.execute(
        """
        UPDATE propostas
           SET natureza_juridica = CASE
                 WHEN fonte IN ('transferegov_ff', 'fns') THEN 'entes_municipais'
                 ELSE 'outros'
               END
         WHERE natureza_juridica IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_propostas_natureza_juridica'), table_name='propostas')
    op.drop_column('propostas', 'natureza_juridica_descricao')
    op.drop_column('propostas', 'natureza_juridica')
