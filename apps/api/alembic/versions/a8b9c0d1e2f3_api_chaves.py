"""api_chaves + api_uso — chaves de API de parceiros e consumo diário (§67)

Nível-plataforma, SEM RLS (como `convites`): a chave é resolvida no começo do
request, antes de existir tenant — é ela que DIZ quem é o tenant. O isolamento
dos dados continua no RLS das tabelas por-tenant: quem entra com a chave é o
usuário dono dela, e só vê o território dele.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"


def upgrade() -> None:
    op.create_table(
        "api_chaves",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("prefixo", sa.String(length=32), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("ambiente", sa.String(length=8), nullable=False),
        sa.Column("escopo", sa.String(length=16), nullable=False, server_default="leitura"),
        sa.Column("limite_por_minuto", sa.Integer(), nullable=True),
        sa.Column("limite_por_dia", sa.Integer(), nullable=True),
        sa.Column("criada_por", sa.UUID(), nullable=True),
        sa.Column("ultimo_uso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ambiente IN ('live','test')", name="ck_api_chaves_ambiente"),
        sa.CheckConstraint("escopo IN ('leitura','escrita')", name="ck_api_chaves_escopo"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criada_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_chaves_hash", "api_chaves", ["hash"], unique=True)
    op.create_index("ix_api_chaves_usuario_id", "api_chaves", ["usuario_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON api_chaves TO {APP_ROLE}")

    op.create_table(
        "api_uso",
        sa.Column("chave_id", sa.UUID(), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("requisicoes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bloqueadas", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["chave_id"], ["api_chaves.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chave_id", "dia"),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON api_uso TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("api_uso")
    op.drop_index("ix_api_chaves_usuario_id", table_name="api_chaves")
    op.drop_index("ix_api_chaves_hash", table_name="api_chaves")
    op.drop_table("api_chaves")
