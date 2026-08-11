"""proposta_empenhos — os empenhos da proposta (o recurso saiu do papel)

O empenho não vem na linha do plano de ação: mora em rota própria do módulo
especiais (`/empenhos_especiais`), consultada pelo NÚMERO DA PROPOSTA. Como a
proposta acumula empenhos (ordinário, reforço, anulação), é 1-N — tabela
própria, não coluna.

Não substitui `propostas.execucao.valor_empenhado` (§28), que é o agregado do
painel da Visão Geral: aqui é o documento item a item, e é dele que sai o total
quando aquele agregado não vem — que era o caso em que a faixa de destaque
aparecia sem empenho nenhum.

Cache global com RLS só-SELECT por município, igual a pareceres/proposta_emendas:
`municipio_ibge` desnormalizado para a policy recortar sem join, nulo visível
porque a consulta por número de proposta nem sempre resolve o município.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposta_empenhos",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fonte", sa.String(length=32), nullable=False),
        sa.Column("id_externo", sa.String(length=128), nullable=False),
        # elos com a proposta — a consulta é pelo número da proposta
        sa.Column("numero_proposta", sa.String(length=64), nullable=True),
        sa.Column("numero_plano_acao", sa.String(length=64), nullable=True),
        sa.Column("municipio_ibge", sa.String(length=7), nullable=True),
        # o documento
        sa.Column("numero_empenho", sa.String(length=64), nullable=True),
        sa.Column("data_empenho", sa.Date(), nullable=True),
        sa.Column("tipo_empenho", sa.String(length=64), nullable=True),
        sa.Column("situacao", sa.String(length=128), nullable=True),
        sa.Column("ano", sa.String(length=4), nullable=True),
        # dinheiro
        sa.Column("valor_empenhado", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("valor_anulado", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("valor_liquidado", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("valor_pago", sa.Numeric(precision=15, scale=2), nullable=True),
        # de onde saiu o recurso
        sa.Column("ug_emitente", sa.String(length=255), nullable=True),
        sa.Column("gestao_emitente", sa.String(length=255), nullable=True),
        sa.Column("natureza_despesa", sa.String(length=255), nullable=True),
        sa.Column("fonte_recurso", sa.String(length=255), nullable=True),
        sa.Column("programa_trabalho", sa.String(length=255), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
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
            "fonte", "id_externo", name="uq_proposta_empenhos_fonte_id_externo"
        ),
    )
    op.create_index("ix_proposta_empenhos_fonte", "proposta_empenhos", ["fonte"])
    op.create_index(
        "ix_proposta_empenhos_numero_proposta", "proposta_empenhos", ["numero_proposta"]
    )
    op.create_index(
        "ix_proposta_empenhos_plano_acao", "proposta_empenhos", ["numero_plano_acao"]
    )
    op.create_index(
        "ix_proposta_empenhos_municipio_ibge", "proposta_empenhos", ["municipio_ibge"]
    )
    op.create_index("ix_proposta_empenhos_data", "proposta_empenhos", ["data_empenho"])
    op.create_index(
        "ix_proposta_empenhos_cache_atualizado_em",
        "proposta_empenhos",
        ["cache_atualizado_em"],
    )

    uid = "current_setting('app.usuario_id', true)::uuid"
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON proposta_empenhos TO hubcapture_app")
    op.execute("ALTER TABLE proposta_empenhos ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE proposta_empenhos FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_proposta_empenhos_select ON proposta_empenhos
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
        "CREATE POLICY p_proposta_empenhos_insert ON proposta_empenhos "
        "FOR INSERT WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY p_proposta_empenhos_update ON proposta_empenhos "
        "FOR UPDATE USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY p_proposta_empenhos_delete ON proposta_empenhos FOR DELETE USING (true)"
    )


def downgrade() -> None:
    for pol in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS p_proposta_empenhos_{pol} ON proposta_empenhos")
    op.execute("ALTER TABLE proposta_empenhos DISABLE ROW LEVEL SECURITY")
    for idx in (
        "ix_proposta_empenhos_cache_atualizado_em",
        "ix_proposta_empenhos_data",
        "ix_proposta_empenhos_municipio_ibge",
        "ix_proposta_empenhos_plano_acao",
        "ix_proposta_empenhos_numero_proposta",
        "ix_proposta_empenhos_fonte",
    ):
        op.drop_index(idx, table_name="proposta_empenhos")
    op.drop_table("proposta_empenhos")
