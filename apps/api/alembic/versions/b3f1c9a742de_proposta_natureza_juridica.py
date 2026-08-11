"""proposta: natureza juridica (filtro de busca do painel)

Revision ID: b3f1c9a742de
Revises: 66ddf34515bd
Create Date: 2026-08-11 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3f1c9a742de'
down_revision: Union[str, None] = '66ddf34515bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Slug normalizado (ver models.proposta.NATUREZAS_JURIDICAS). Fica NULL nas
    # propostas já cacheadas — o próximo sync da fonte preenche.
    op.add_column(
        'propostas',
        sa.Column('natureza_juridica', sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f('ix_propostas_natureza_juridica'),
        'propostas',
        ['natureza_juridica'],
        unique=False,
    )
    # busca por número no painel é ILIKE '%…%' — índice trigram cobre os três
    # campos pesquisados sem varrer a tabela inteira.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_propostas_numero_proposta_trgm ON propostas "
        "USING gin (numero_proposta gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_propostas_id_externo_trgm ON propostas "
        "USING gin (id_externo gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_propostas_valor_total ON propostas (valor_total)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_propostas_valor_total")
    op.execute("DROP INDEX IF EXISTS ix_propostas_id_externo_trgm")
    op.execute("DROP INDEX IF EXISTS ix_propostas_numero_proposta_trgm")
    op.drop_index(op.f('ix_propostas_natureza_juridica'), table_name='propostas')
    op.drop_column('propostas', 'natureza_juridica')
