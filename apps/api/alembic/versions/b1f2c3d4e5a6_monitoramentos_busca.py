"""monitoramentos_busca (futuras propostas) + alertas.proposta_id nullable

Revision ID: b1f2c3d4e5a6
Revises: 66ddf34515bd
Create Date: 2026-07-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1f2c3d4e5a6"
down_revision: str | None = "66ddf34515bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"
UID = "current_setting('app.usuario_id', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "monitoramentos_busca",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("municipio_ibge", sa.String(length=7), nullable=False),
        sa.Column("area", sa.String(length=32), nullable=True),
        sa.Column("fonte", sa.String(length=32), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("canais", postgresql.ARRAY(postgresql.TEXT()), nullable=True),
        sa.Column("ultimo_alerta_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id", "municipio_ibge", "area", "fonte",
            name="uq_monitoramentos_busca_escopo",
        ),
    )
    op.create_index(
        "ix_monitoramentos_busca_usuario_id", "monitoramentos_busca", ["usuario_id"]
    )

    # RLS por-tenant, mesmo modelo das demais tabelas com usuario_id
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON monitoramentos_busca TO {APP_ROLE}")
    op.execute("ALTER TABLE monitoramentos_busca ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE monitoramentos_busca FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_monitoramentos_busca_tenant ON monitoramentos_busca
          FOR ALL
          USING (usuario_id = {UID})
          WITH CHECK (usuario_id = {UID})
        """
    )

    # alertas de oportunidade não têm proposta associada
    op.alter_column("alertas", "proposta_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column("alertas", "proposta_id", existing_type=sa.UUID(), nullable=False)
    op.drop_index("ix_monitoramentos_busca_usuario_id", table_name="monitoramentos_busca")
    op.drop_table("monitoramentos_busca")
