"""contatos e integracoes de agenda (google/microsoft/apple/carddav)

Revision ID: b41c7de90a12
Revises: d8e9f0a1b2c3
Create Date: 2026-08-03 12:00:00.000000

Dado PESSOAL do usuário (não é cache público como propostas/repasses/obras):
RLS FOR ALL por `usuario_id`, no mesmo molde de `pastas`/`favoritos`.
`contato_vinculos` não tem `usuario_id` — o escopo vem da integração dona,
igual ao que `pasta_propostas` faz via `pastas`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b41c7de90a12"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"
UID = "current_setting('app.usuario_id', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "contatos",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("sobrenome", sa.String(length=255), nullable=True),
        sa.Column("organizacao", sa.String(length=255), nullable=True),
        sa.Column("cargo", sa.String(length=255), nullable=True),
        sa.Column("emails", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("telefones", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enderecos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("municipio_ibge", sa.String(length=7), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("origem", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("chave_dedup", sa.String(length=255), nullable=True),
        sa.Column("hash_conteudo", sa.String(length=64), nullable=True),
        sa.Column("arquivado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contatos_usuario_id"), "contatos", ["usuario_id"], unique=False)
    op.create_index(op.f("ix_contatos_municipio_ibge"), "contatos", ["municipio_ibge"], unique=False)
    op.create_index(op.f("ix_contatos_chave_dedup"), "contatos", ["chave_dedup"], unique=False)
    op.create_index(op.f("ix_contatos_arquivado"), "contatos", ["arquivado"], unique=False)

    op.create_table(
        "integracoes_contatos",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("provedor", sa.String(length=16), nullable=False),
        sa.Column("conta", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="conectada"),
        sa.Column("direcao", sa.String(length=16), nullable=False, server_default="bidirecional"),
        sa.Column("credenciais", sa.Text(), nullable=True),
        sa.Column("sync_token", sa.Text(), nullable=True),
        sa.Column("ultima_sync_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("total_contatos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "provedor", "conta", name="uq_integracoes_contatos_conta"),
    )
    op.create_index(
        op.f("ix_integracoes_contatos_usuario_id"), "integracoes_contatos", ["usuario_id"], unique=False
    )

    op.create_table(
        "contato_vinculos",
        sa.Column("integracao_id", sa.UUID(), nullable=False),
        sa.Column("contato_id", sa.UUID(), nullable=False),
        sa.Column("id_externo", sa.String(length=512), nullable=False),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("hash_sincronizado", sa.String(length=64), nullable=True),
        sa.Column("removido_remoto", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["integracao_id"], ["integracoes_contatos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contato_id"], ["contatos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("integracao_id", "contato_id"),
        sa.UniqueConstraint("integracao_id", "id_externo", name="uq_contato_vinculos_externo"),
    )

    # ── RLS ────────────────────────────────────────────────────────────────
    for tabela in ("contatos", "integracoes_contatos", "contato_vinculos"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tabela} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")

    for tabela in ("contatos", "integracoes_contatos"):
        op.execute(
            f"""
            CREATE POLICY p_{tabela}_tenant ON {tabela}
              FOR ALL
              USING (usuario_id = {UID})
              WITH CHECK (usuario_id = {UID})
            """
        )

    # vínculo herda o escopo da integração dona (mesmo padrão de pasta_propostas)
    op.execute(
        f"""
        CREATE POLICY p_contato_vinculos_tenant ON contato_vinculos
          FOR ALL
          USING (integracao_id IN (
            SELECT id FROM integracoes_contatos WHERE usuario_id = {UID}
          ))
          WITH CHECK (integracao_id IN (
            SELECT id FROM integracoes_contatos WHERE usuario_id = {UID}
          ))
        """
    )


def downgrade() -> None:
    for tabela in ("contato_vinculos", "integracoes_contatos", "contatos"):
        op.execute(f"DROP POLICY IF EXISTS p_{tabela}_tenant ON {tabela}")
        op.execute(f"ALTER TABLE {tabela} DISABLE ROW LEVEL SECURITY")

    op.drop_table("contato_vinculos")
    op.drop_index(op.f("ix_integracoes_contatos_usuario_id"), table_name="integracoes_contatos")
    op.drop_table("integracoes_contatos")
    op.drop_index(op.f("ix_contatos_arquivado"), table_name="contatos")
    op.drop_index(op.f("ix_contatos_chave_dedup"), table_name="contatos")
    op.drop_index(op.f("ix_contatos_municipio_ibge"), table_name="contatos")
    op.drop_index(op.f("ix_contatos_usuario_id"), table_name="contatos")
    op.drop_table("contatos")
