"""class — módulos de aprendizagem (aulas dentro de módulos)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-09 21:00:00.000000

A Central de ajuda virou CLASS e ganhou a camada de curso: `helpdesk_modulos`
agrupa AULAS em sequência. Aula não é entidade nova — é um artigo com
`modulo_id` preenchido (reusa corpo, mídias, hints, editor e link
compartilhável); `ordem` já existia e vira a posição da aula no módulo.
Excluir módulo NÃO apaga conteúdo: as aulas voltam a ser artigos avulsos
(FK SET NULL).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"


def upgrade() -> None:
    op.create_table(
        "helpdesk_modulos",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=280), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("publicado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_helpdesk_modulos_slug"),
    )

    op.add_column(
        "helpdesk_artigos",
        sa.Column("modulo_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_helpdesk_artigos_modulo",
        "helpdesk_artigos",
        "helpdesk_modulos",
        ["modulo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_helpdesk_artigos_modulo_id"), "helpdesk_artigos", ["modulo_id"])

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON helpdesk_modulos TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_index(op.f("ix_helpdesk_artigos_modulo_id"), table_name="helpdesk_artigos")
    op.drop_constraint("fk_helpdesk_artigos_modulo", "helpdesk_artigos", type_="foreignkey")
    op.drop_column("helpdesk_artigos", "modulo_id")
    op.drop_table("helpdesk_modulos")
