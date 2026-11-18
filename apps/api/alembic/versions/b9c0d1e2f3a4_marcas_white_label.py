"""marcas + marca_assets + usuarios/convites.marca_id — white label (§69)

Nível-plataforma, SEM RLS (como `planos`/`convites`): a marca é lida pelo HOST
antes de existir usuário — a tela de login sai vestida — e o que ela guarda é
público por natureza (cores, logo, textos). Os dados do gestor seguem no RLS
por usuário; pertencer a uma marca não abre dado de ninguém.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"


def upgrade() -> None:
    op.create_table(
        "marcas",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("dono_id", sa.UUID(), nullable=True),
        sa.Column("plano_id", sa.UUID(), nullable=True),
        sa.Column("cadastro_aberto", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("dominio", sa.String(length=253), nullable=True),
        sa.Column("dominio_status", sa.String(length=16), nullable=True),
        sa.Column("dominio_detalhe", sa.Text(), nullable=True),
        sa.Column("dominio_verificado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provisionamento",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "tema", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "dominio_status IS NULL OR dominio_status IN ('pendente','verificado','ativo','erro')",
            name="ck_marcas_dominio_status",
        ),
        sa.ForeignKeyConstraint(["dono_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plano_id"], ["planos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dominio", name="uq_marcas_dominio"),
    )
    op.create_index("ix_marcas_slug", "marcas", ["slug"], unique=True)
    op.create_index("ix_marcas_dono_id", "marcas", ["dono_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON marcas TO {APP_ROLE}")

    op.create_table(
        "marca_assets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("marca_id", sa.UUID(), nullable=False),
        sa.Column("tipo", sa.String(length=24), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("nome_arquivo", sa.String(length=255), nullable=True),
        sa.Column("conteudo", sa.LargeBinary(), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["marca_id"], ["marcas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marca_id", "tipo", name="uq_marca_assets_tipo"),
    )
    op.create_index("ix_marca_assets_marca_id", "marca_assets", ["marca_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON marca_assets TO {APP_ROLE}")

    op.add_column("usuarios", sa.Column("marca_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_usuarios_marca_id", "usuarios", "marcas", ["marca_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_usuarios_marca_id", "usuarios", ["marca_id"])

    op.add_column("convites", sa.Column("marca_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_convites_marca_id", "convites", "marcas", ["marca_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_convites_marca_id", "convites", type_="foreignkey")
    op.drop_column("convites", "marca_id")
    op.drop_index("ix_usuarios_marca_id", table_name="usuarios")
    op.drop_constraint("fk_usuarios_marca_id", "usuarios", type_="foreignkey")
    op.drop_column("usuarios", "marca_id")
    op.drop_index("ix_marca_assets_marca_id", table_name="marca_assets")
    op.drop_table("marca_assets")
    op.drop_index("ix_marcas_dono_id", table_name="marcas")
    op.drop_index("ix_marcas_slug", table_name="marcas")
    op.drop_table("marcas")
