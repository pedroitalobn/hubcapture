"""propostas: índices de busca (trigram nos números + valor_total)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-11 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A busca por número (`q`) é ILIKE '%…%' — sem trigram, cada tecla digitada no
# painel varre a tabela inteira. Índice só nas colunas de IDENTIFICAÇÃO: são as
# que o gestor digita para achar UMA proposta. Título/objeto continuam em seq
# scan de propósito (texto longo, ganho menor, índice bem mais caro).
_COLUNAS = ("numero_proposta", "id_externo", "numero_plano_trabalho", "emenda")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for coluna in _COLUNAS:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_propostas_{coluna}_trgm "
            f"ON propostas USING gin ({coluna} gin_trgm_ops)"
        )
    # faixa de valor (valor_min/valor_max) do painel e da captação
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_propostas_valor_total "
        "ON propostas (valor_total)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_propostas_valor_total")
    for coluna in _COLUNAS:
        op.execute(f"DROP INDEX IF EXISTS ix_propostas_{coluna}_trgm")
