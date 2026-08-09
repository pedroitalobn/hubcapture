"""propostas: data de criação da proposta na fonte (DIA_PROPOSTA)

`data_atualizacao_fonte` é quando a FONTE mexeu no registro (D-1 do sync); não
responde "de quando é esta proposta". O gestor cita a proposta por número e
data ("14275/2026, de 26/03"), então a data de criação é dado próprio.

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b3c4d5e6a7"
down_revision = "e1a2b3c4d5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("propostas", sa.Column("data_proposta", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("propostas", "data_proposta")
