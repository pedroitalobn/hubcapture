"""busca por numero_proposta (índice trigram)

Revision ID: b1f3c2a7d9e4
Revises: 66ddf34515bd
Create Date: 2026-08-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1f3c2a7d9e4'
down_revision: Union[str, None] = '66ddf34515bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # a busca do painel é ILIKE '%numero%' (curinga à esquerda): btree não
    # ajudaria, então usamos GIN + pg_trgm.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_propostas_numero_proposta_trgm "
        "ON propostas USING gin (numero_proposta gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_propostas_numero_proposta_trgm")
