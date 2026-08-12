"""proposta_emendas — emenda parlamentar que financia a proposta (e o autor)

É 1-N com a proposta (um plano de ação pode somar mais de uma emenda, cada uma
com seu autor e seus valores), então entidade própria — não coluna. A chave de
ligação é a da proposta na fonte: id do plano de ação e/ou nº da proposta.

Cache global com RLS só-SELECT por município, igual a propostas/pareceres/
obras: `municipio_ibge` é desnormalizado aqui para a policy recortar sem join, e
nulo permanece visível — a consulta por número de plano nem sempre resolve o
município, e sem isso a emenda sumiria da tela.

Revision ID: f3a4b5c6d7e8
Revises: e5f6a7b8c9d0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposta_emendas",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fonte", sa.String(length=32), nullable=False),
        sa.Column("id_externo", sa.String(length=128), nullable=False),
        # elos com a proposta (a fonte consulta por um destes)
        sa.Column("numero_plano_acao", sa.String(length=64), nullable=True),
        sa.Column("numero_proposta", sa.String(length=64), nullable=True),
        sa.Column("municipio_ibge", sa.String(length=7), nullable=True),
        # a emenda
        sa.Column("codigo_emenda", sa.String(length=64), nullable=True),
        sa.Column("numero_emenda", sa.String(length=64), nullable=True),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("tipo_emenda", sa.String(length=64), nullable=True),
        # o autor — com quem o gestor fala
        sa.Column("parlamentar", sa.String(length=255), nullable=True),
        sa.Column("partido", sa.String(length=32), nullable=True),
        sa.Column("uf_parlamentar", sa.String(length=2), nullable=True),
        sa.Column("cargo_parlamentar", sa.String(length=64), nullable=True),
        sa.Column("codigo_parlamentar", sa.String(length=32), nullable=True),
        # dinheiro
        sa.Column("valor", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("valor_empenhado", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("valor_pago", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("funcao", sa.String(length=255), nullable=True),
        sa.Column("situacao", sa.String(length=255), nullable=True),
        sa.Column("url_origem", sa.Text(), nullable=True),
        sa.Column("detalhe", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("proveniencia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("hash_conteudo", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cache_atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fonte", "id_externo", name="uq_proposta_emendas_fonte_id_externo"
        ),
    )
    op.create_index("ix_proposta_emendas_fonte", "proposta_emendas", ["fonte"])
    op.create_index(
        "ix_proposta_emendas_plano_acao", "proposta_emendas", ["numero_plano_acao"]
    )
    op.create_index(
        "ix_proposta_emendas_numero_proposta", "proposta_emendas", ["numero_proposta"]
    )
    op.create_index(
        "ix_proposta_emendas_municipio_ibge", "proposta_emendas", ["municipio_ibge"]
    )
    op.create_index("ix_proposta_emendas_parlamentar", "proposta_emendas", ["parlamentar"])
    op.create_index(
        "ix_proposta_emendas_cache_atualizado_em",
        "proposta_emendas",
        ["cache_atualizado_em"],
    )

    uid = "current_setting('app.usuario_id', true)::uuid"
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON proposta_emendas TO hubcapture_app")
    op.execute("ALTER TABLE proposta_emendas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE proposta_emendas FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_proposta_emendas_select ON proposta_emendas
          FOR SELECT
          USING (
            municipio_ibge IS NULL
            OR municipio_ibge IN (
              SELECT ibge FROM municipios_interesse WHERE usuario_id = {uid}
            )
          )
        """
    )
    op.execute(
        "CREATE POLICY p_proposta_emendas_insert ON proposta_emendas "
        "FOR INSERT WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY p_proposta_emendas_update ON proposta_emendas "
        "FOR UPDATE USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY p_proposta_emendas_delete ON proposta_emendas FOR DELETE USING (true)"
    )


def downgrade() -> None:
    for pol in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS p_proposta_emendas_{pol} ON proposta_emendas")
    op.execute("ALTER TABLE proposta_emendas DISABLE ROW LEVEL SECURITY")
    for idx in (
        "ix_proposta_emendas_cache_atualizado_em",
        "ix_proposta_emendas_parlamentar",
        "ix_proposta_emendas_municipio_ibge",
        "ix_proposta_emendas_numero_proposta",
        "ix_proposta_emendas_plano_acao",
        "ix_proposta_emendas_fonte",
    ):
        op.drop_index(idx, table_name="proposta_emendas")
    op.drop_table("proposta_emendas")
