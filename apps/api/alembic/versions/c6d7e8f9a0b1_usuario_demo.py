"""Conta de demonstração — flag `is_demo` em usuarios.

O acesso demo (apresentação/vendas) é um USUÁRIO comum com esta flag: entra
pelo `POST /auth/demo`, enxerga dados reais do cache pelo RLS de sempre e tem
as ações destrutivas/de identidade bloqueadas em `services/demo.py`. A flag na
linha (e não um e-mail hardcoded) é o que deixa o resto do sistema decidir por
`user.is_demo` sem consultar configuração.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("usuarios", "is_demo")
