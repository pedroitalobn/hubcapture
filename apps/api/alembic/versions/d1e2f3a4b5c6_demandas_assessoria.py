"""demandas — central de recebimento da Assessoria (por-tenant)

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"
# `nullif` antes do cast: sessão SEM tenant (a de plataforma) faria
# `''::uuid` e a leitura estouraria com InvalidTextRepresentation em vez de
# devolver zero linhas. Com nullif o resultado é NULL, a comparação é falsa e a
# sessão sem tenant simplesmente não enxerga nada — que é o comportamento
# seguro.
UID = "nullif(current_setting('app.usuario_id', true), '')::uuid"
# Bandeira da sessão de PLATAFORMA: a fila da assessoria é cross-tenant por
# natureza (quem responde é a administração, e ela precisa ver todas). Só a
# dependency `get_plataforma_db` liga esta bandeira, e só `demandas` tem uma
# policy que a reconhece — o modelo de confiança é o mesmo do `app.usuario_id`:
# quem decide é a camada de API.
PLATAFORMA = "nullif(current_setting('app.plataforma', true), '') = 'on'"


def upgrade() -> None:
    op.create_table(
        "demandas",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("assunto", sa.String(length=255), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("municipio_ibge", sa.String(length=7), nullable=True),
        sa.Column("proposta_id", sa.UUID(), nullable=True),
        sa.Column("situacao", sa.String(length=16), nullable=False, server_default="aberta"),
        sa.Column("origem", sa.String(length=16), nullable=False, server_default="painel"),
        sa.Column("historico", sa.JSON(), nullable=True),
        sa.Column("resolvida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        # SET NULL: a proposta é cache global e pode ser zerada (§41). Com
        # CASCADE, uma recoleta apagaria o pedido do gestor junto.
        sa.ForeignKeyConstraint(["proposta_id"], ["propostas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demandas_usuario_id", "demandas", ["usuario_id"])
    op.create_index("ix_demandas_situacao", "demandas", ["situacao"])
    op.create_index("ix_demandas_municipio_ibge", "demandas", ["municipio_ibge"])

    # RLS por-tenant, mesmo modelo de `pastas`/`monitoramentos_busca`: a demanda
    # é do usuário que a abriu. A administração responde pela sessão de
    # plataforma, que não passa por esta policy.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON demandas TO {APP_ROLE}")
    op.execute("ALTER TABLE demandas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE demandas FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_demandas_tenant ON demandas
          FOR ALL
          USING (usuario_id = {UID})
          WITH CHECK (usuario_id = {UID})
        """
    )
    # Policies permissivas são somadas (OR): a de plataforma abre a fila para a
    # administração sem afrouxar a do tenant.
    op.execute(
        f"""
        CREATE POLICY p_demandas_plataforma ON demandas
          FOR ALL
          USING ({PLATAFORMA})
          WITH CHECK ({PLATAFORMA})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS p_demandas_plataforma ON demandas")
    op.execute("DROP POLICY IF EXISTS p_demandas_tenant ON demandas")
    op.drop_index("ix_demandas_municipio_ibge", table_name="demandas")
    op.drop_index("ix_demandas_situacao", table_name="demandas")
    op.drop_index("ix_demandas_usuario_id", table_name="demandas")
    op.drop_table("demandas")
