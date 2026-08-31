"""proposta_documentos — o ARQUIVO que comprova o ato (publicação, contrato…)

Quando a publicação sai, o gestor precisa do documento, não só do rótulo
"Publicado" (ponto 10 do feedback de 28/08). A "Lista de Documentos
Digitalizados" da proposta é 1-N — publicação, ofício ao legislativo, contrato
de repasse —, então é tabela própria e não coluna.

Guardamos a REFERÊNCIA (nome, data, URL na fonte), nunca os bytes: o arquivo é
público na origem, pesa, e cachear binário de terceiro cria um acervo que
ninguém pediu para manter — além de envelhecer sem aviso quando a fonte
republica.

Cache global com RLS só-SELECT por município, igual a pareceres/empenhos:
`municipio_ibge` desnormalizado para a policy recortar sem join, e nulo
visível porque a consulta é pelo idProposta e nem sempre resolve o município.

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f8a0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b2c3d4e5f8a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposta_documentos",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fonte", sa.String(length=32), nullable=False),
        sa.Column("id_externo", sa.String(length=128), nullable=False),
        # elos com a proposta
        sa.Column("numero_proposta", sa.String(length=64), nullable=True),
        sa.Column("id_proposta_fonte", sa.String(length=64), nullable=True),
        sa.Column("municipio_ibge", sa.String(length=7), nullable=True),
        # o documento
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=True),
        sa.Column("data_upload", sa.Date(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
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
            "fonte", "id_externo", name="uq_proposta_documentos_fonte_id_externo"
        ),
    )
    op.create_index("ix_proposta_documentos_fonte", "proposta_documentos", ["fonte"])
    op.create_index(
        "ix_proposta_documentos_numero_proposta", "proposta_documentos", ["numero_proposta"]
    )
    op.create_index(
        "ix_proposta_documentos_id_proposta_fonte",
        "proposta_documentos",
        ["id_proposta_fonte"],
    )
    op.create_index(
        "ix_proposta_documentos_municipio_ibge", "proposta_documentos", ["municipio_ibge"]
    )
    op.create_index("ix_proposta_documentos_tipo", "proposta_documentos", ["tipo"])
    op.create_index("ix_proposta_documentos_data", "proposta_documentos", ["data_upload"])
    op.create_index(
        "ix_proposta_documentos_cache_atualizado_em",
        "proposta_documentos",
        ["cache_atualizado_em"],
    )

    uid = "current_setting('app.usuario_id', true)::uuid"
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON proposta_documentos TO hubcapture_app")
    op.execute("ALTER TABLE proposta_documentos ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE proposta_documentos FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_proposta_documentos_select ON proposta_documentos
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
        "CREATE POLICY p_proposta_documentos_insert ON proposta_documentos "
        "FOR INSERT WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY p_proposta_documentos_update ON proposta_documentos "
        "FOR UPDATE USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY p_proposta_documentos_delete ON proposta_documentos FOR DELETE USING (true)"
    )


def downgrade() -> None:
    for pol in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS p_proposta_documentos_{pol} ON proposta_documentos")
    op.execute("ALTER TABLE proposta_documentos DISABLE ROW LEVEL SECURITY")
    for idx in (
        "ix_proposta_documentos_cache_atualizado_em",
        "ix_proposta_documentos_data",
        "ix_proposta_documentos_tipo",
        "ix_proposta_documentos_municipio_ibge",
        "ix_proposta_documentos_id_proposta_fonte",
        "ix_proposta_documentos_numero_proposta",
        "ix_proposta_documentos_fonte",
    ):
        op.drop_index(idx, table_name="proposta_documentos")
    op.drop_table("proposta_documentos")
