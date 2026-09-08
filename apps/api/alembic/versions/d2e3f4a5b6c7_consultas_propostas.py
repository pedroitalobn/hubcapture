"""consultas_propostas — as abas do construtor de consultas (§61)

Dado PESSOAL por-tenant (RLS `FOR ALL` por usuario_id), no mesmo molde de
`pastas`: a aba é a consulta salva do gestor, não cache público.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"
UID = "current_setting('app.usuario_id', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "consultas_propostas",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column(
            "filtros",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ordem", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consultas_propostas_usuario_id", "consultas_propostas", ["usuario_id"])

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON consultas_propostas TO {APP_ROLE}")
    op.execute("ALTER TABLE consultas_propostas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE consultas_propostas FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_consultas_propostas_tenant ON consultas_propostas
          FOR ALL
          USING (usuario_id = {UID})
          WITH CHECK (usuario_id = {UID})
        """
    )


def downgrade() -> None:
    op.drop_index("ix_consultas_propostas_usuario_id", table_name="consultas_propostas")
    op.drop_table("consultas_propostas")
