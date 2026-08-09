"""pareceres (tramitação do plano de trabalho) + numero_plano_trabalho na proposta

O parecer é 1-N com a proposta (a mesma proposta acumula pareceres a cada
análise) e a chave de consulta é o NÚMERO DO PLANO DE TRABALHO — é por ele que
o parecer é emitido na fonte. Daí tabela própria e `propostas.numero_plano_trabalho`
como elo.

Cache global com RLS só-SELECT por município, igual a propostas/repasses/
obras/conformidades: `municipio_ibge` é desnormalizado aqui para a policy poder
recortar sem join.

Revision ID: a3c4d5e6f7b8
Revises: f2b3c4d5e6a7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3c4d5e6f7b8"
down_revision = "f2b3c4d5e6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # elo proposta → plano de trabalho (a chave pela qual o parecer é emitido)
    op.add_column(
        "propostas", sa.Column("numero_plano_trabalho", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "ix_propostas_numero_plano_trabalho",
        "propostas",
        ["numero_plano_trabalho"],
    )

    op.create_table(
        "pareceres",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fonte", sa.String(length=32), nullable=False),
        sa.Column("id_externo", sa.String(length=128), nullable=False),
        # chave de consulta: o parecer é do PLANO DE TRABALHO
        sa.Column("numero_plano_trabalho", sa.String(length=64), nullable=False),
        sa.Column("numero_proposta", sa.String(length=64), nullable=True),
        sa.Column("municipio_ibge", sa.String(length=7), nullable=True),
        sa.Column("data_parecer", sa.Date(), nullable=True),
        sa.Column("esfera", sa.String(length=32), nullable=True),  # CONCEDENTE|CONVENENTE
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("papel", sa.String(length=255), nullable=True),  # Gestor/Analista Técnico
        sa.Column("cargo", sa.String(length=255), nullable=True),  # COORDENADORA-GERAL
        sa.Column("situacao", sa.String(length=64), nullable=True),
        sa.Column("situacao_analise", sa.String(length=32), nullable=True),
        sa.Column("situacao_planejamento", sa.String(length=32), nullable=True),
        sa.Column("orgao_analise", sa.String(length=255), nullable=True),
        sa.Column("codigo_siorg_orgao", sa.String(length=32), nullable=True),
        sa.Column("valor_reprovado", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("url_parecer", sa.Text(), nullable=True),  # "Visualizar Parecer"
        sa.Column("detalhe", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("proveniencia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("hash_conteudo", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cache_atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fonte", "id_externo", name="uq_pareceres_fonte_id_externo"),
    )
    op.create_index("ix_pareceres_fonte", "pareceres", ["fonte"])
    op.create_index("ix_pareceres_plano_trabalho", "pareceres", ["numero_plano_trabalho"])
    op.create_index("ix_pareceres_municipio_ibge", "pareceres", ["municipio_ibge"])
    op.create_index("ix_pareceres_cache_atualizado_em", "pareceres", ["cache_atualizado_em"])

    # RLS: cache global (dado público). SELECT filtra por município de interesse;
    # escrita livre para a role de app. `municipio_ibge` nulo (parecer coletado
    # por número de plano, sem município resolvido) fica visível — é dado público
    # e sem ele a consulta por plano de trabalho não devolveria nada.
    uid = "current_setting('app.usuario_id', true)::uuid"
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON pareceres TO hubcapture_app")
    op.execute("ALTER TABLE pareceres ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pareceres FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_pareceres_select ON pareceres
          FOR SELECT
          USING (
            municipio_ibge IS NULL
            OR municipio_ibge IN (
              SELECT ibge FROM municipios_interesse WHERE usuario_id = {uid}
            )
          )
        """
    )
    op.execute("CREATE POLICY p_pareceres_insert ON pareceres FOR INSERT WITH CHECK (true)")
    op.execute(
        "CREATE POLICY p_pareceres_update ON pareceres FOR UPDATE USING (true) WITH CHECK (true)"
    )
    op.execute("CREATE POLICY p_pareceres_delete ON pareceres FOR DELETE USING (true)")


def downgrade() -> None:
    for pol in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS p_pareceres_{pol} ON pareceres")
    op.execute("ALTER TABLE pareceres DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_pareceres_cache_atualizado_em", table_name="pareceres")
    op.drop_index("ix_pareceres_municipio_ibge", table_name="pareceres")
    op.drop_index("ix_pareceres_plano_trabalho", table_name="pareceres")
    op.drop_index("ix_pareceres_fonte", table_name="pareceres")
    op.drop_table("pareceres")
    op.drop_index("ix_propostas_numero_plano_trabalho", table_name="propostas")
    op.drop_column("propostas", "numero_plano_trabalho")
