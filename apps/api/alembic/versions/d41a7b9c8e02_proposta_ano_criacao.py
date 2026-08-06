"""proposta: ano/data de criação (classificação por safra, não por atualização)

Revision ID: d41a7b9c8e02
Revises: 66ddf34515bd
Create Date: 2026-08-06

A listagem classificava propostas pelo movimento mais recente, então uma proposta
criada em 2022 com atualização em 2026 aparecia como 2026. Passa a existir o ano
de criação como coluna própria (`ano`, indexada) + a data de criação na fonte.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d41a7b9c8e02"
down_revision: str | None = "66ddf34515bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# nº de proposta do TransfereGov é 'NNNNNN/AAAA' — o sufixo é o ano de criação
_ANO_NO_NUMERO = r"/\s*((19|20)[0-9]{2})"


def upgrade() -> None:
    op.add_column("propostas", sa.Column("ano", sa.Integer(), nullable=True))
    op.add_column(
        "propostas", sa.Column("data_criacao_fonte", sa.Date(), nullable=True)
    )
    op.create_index(op.f("ix_propostas_ano"), "propostas", ["ano"], unique=False)

    # Backfill do que já está em cache: o UPDATE tem WHERE, e sob FORCE RLS o
    # policy de SELECT (por município do tenant) filtraria tudo numa sessão sem
    # `app.usuario_id`. Suspende o FORCE só durante o backfill.
    op.execute("ALTER TABLE propostas NO FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        UPDATE propostas
           SET ano = substring(numero_proposta from '{_ANO_NO_NUMERO}')::int
         WHERE ano IS NULL
           AND numero_proposta ~ '{_ANO_NO_NUMERO}'
        """
    )
    op.execute("ALTER TABLE propostas FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index(op.f("ix_propostas_ano"), table_name="propostas")
    op.drop_column("propostas", "data_criacao_fonte")
    op.drop_column("propostas", "ano")
