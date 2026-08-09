"""helpdesk — central de ajuda interna (artigos, mídias, hints contextuais)

Revision ID: d4e5f6a7b8c9
Revises: a3c4d5e6f7b8
Create Date: 2026-08-09 12:00:00.000000

Conteúdo de ajuda é NÍVEL-PLATAFORMA (sem RLS), como `base_conhecimento`:
todo usuário logado lê os artigos publicados; só o admin escreve (guard de
endpoint, `is_superuser`). O upload de mídia vive em bytea na própria linha —
o deploy é container efêmero (Dokploy), então disco local não serve de
storage; vídeo grande fica em URL externa (YouTube/Vimeo/mp4).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "a3c4d5e6f7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"


def upgrade() -> None:
    op.create_table(
        "helpdesk_categorias",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_helpdesk_categorias_slug"),
    )

    op.create_table(
        "helpdesk_artigos",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("categoria_id", sa.UUID(), nullable=True),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=280), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("corpo", sa.Text(), nullable=False, server_default=""),
        sa.Column("publicado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["categoria_id"], ["helpdesk_categorias.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_helpdesk_artigos_slug"),
    )
    op.create_index(op.f("ix_helpdesk_artigos_categoria_id"), "helpdesk_artigos", ["categoria_id"])
    op.create_index(op.f("ix_helpdesk_artigos_publicado"), "helpdesk_artigos", ["publicado"])

    op.create_table(
        "helpdesk_midias",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("artigo_id", sa.UUID(), nullable=False),
        # 'video' | 'documento'
        sa.Column("tipo", sa.String(length=16), nullable=False, server_default="documento"),
        sa.Column("titulo", sa.String(length=255), nullable=True),
        # mídia por URL (YouTube/Vimeo/mp4 externo) OU arquivo enviado (conteudo)
        sa.Column("url", sa.Text(), nullable=True),
        # 'horizontal' | 'vertical' — decide o aspecto do player (16:9 × 9:16)
        sa.Column("orientacao", sa.String(length=12), nullable=False, server_default="horizontal"),
        sa.Column("nome_arquivo", sa.String(length=255), nullable=True),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("tamanho", sa.Integer(), nullable=True),
        sa.Column("conteudo", sa.LargeBinary(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["artigo_id"], ["helpdesk_artigos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_helpdesk_midias_artigo_id"), "helpdesk_midias", ["artigo_id"])

    # o hint contextual: chave do elemento de UI (catálogo em services/helpdesk)
    # → artigo. Uma chave, um artigo (o ícone abre UM conteúdo, sem ambiguidade).
    op.create_table(
        "helpdesk_hints",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("chave", sa.String(length=120), nullable=False),
        sa.Column("artigo_id", sa.UUID(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["artigo_id"], ["helpdesk_artigos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chave", name="uq_helpdesk_hints_chave"),
    )
    op.create_index(op.f("ix_helpdesk_hints_artigo_id"), "helpdesk_hints", ["artigo_id"])

    for tabela in (
        "helpdesk_categorias",
        "helpdesk_artigos",
        "helpdesk_midias",
        "helpdesk_hints",
    ):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tabela} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("helpdesk_hints")
    op.drop_table("helpdesk_midias")
    op.drop_table("helpdesk_artigos")
    op.drop_table("helpdesk_categorias")
