"""programas (Oportunidades) + push_inscricoes + canais de alerta da conta

Três coisas que andam juntas nesta rodada (§63):

1. `programas` — catálogo NACIONAL de programas do TransfereGov (pacote SIconv,
   `programa.csv`). Nível-plataforma, SEM RLS: é o mesmo catálogo para todo
   gestor, e quem recorta pelo território é o serviço (UF + natureza jurídica
   de cada programa), não uma policy. Mesma natureza de `base_conhecimento`.
2. `push_inscricoes` — inscrições de Web Push por navegador. Dado PESSOAL
   (RLS `FOR ALL` por usuario_id, molde de `pastas`).
3. `preferencias_usuario.canais_alerta` — os canais escolhidos para a CONTA
   (e-mail…). NULL = legado: só os canais de cada monitoramento valem.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"
UID = "current_setting('app.usuario_id', true)::uuid"
_TEXTOS = postgresql.ARRAY(sa.Text())


def upgrade() -> None:
    op.create_table(
        "programas",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fonte", sa.String(length=32), nullable=False),
        sa.Column("id_externo", sa.String(length=64), nullable=False),
        sa.Column("codigo", sa.String(length=64), nullable=True),
        sa.Column("nome", sa.Text(), nullable=True),
        sa.Column("orgao_superior", sa.String(length=255), nullable=True),
        sa.Column("orgao", sa.String(length=255), nullable=True),
        sa.Column("situacao", sa.String(length=64), nullable=True),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("acao_orcamentaria", sa.String(length=255), nullable=True),
        sa.Column("modalidades", _TEXTOS, nullable=True),
        sa.Column("naturezas", _TEXTOS, nullable=True),
        sa.Column("ufs", _TEXTOS, nullable=True),
        sa.Column("disponibilizado_em", sa.Date(), nullable=True),
        sa.Column("inicio_proposta", sa.Date(), nullable=True),
        sa.Column("fim_proposta", sa.Date(), nullable=True),
        sa.Column("inicio_emenda", sa.Date(), nullable=True),
        sa.Column("fim_emenda", sa.Date(), nullable=True),
        sa.Column("inicio_beneficiario", sa.Date(), nullable=True),
        sa.Column("fim_beneficiario", sa.Date(), nullable=True),
        # municípios do TERRITÓRIO monitorado que já propuseram neste programa
        # (programa_proposta → proposta) — é o sinal de "vocês já captam aqui"
        sa.Column("municipios_historico", _TEXTOS, nullable=True),
        sa.Column("detalhe", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("hash_conteudo", sa.String(length=64), nullable=True),
        sa.Column("cache_atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fonte", "id_externo", name="uq_programas_fonte_id_externo"),
    )
    op.create_index("ix_programas_fim_proposta", "programas", ["fim_proposta"])
    op.create_index("ix_programas_fim_emenda", "programas", ["fim_emenda"])
    op.create_index("ix_programas_fim_beneficiario", "programas", ["fim_beneficiario"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON programas TO {APP_ROLE}")

    op.create_table(
        "push_inscricoes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ultimo_envio_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # por (usuário, endpoint) e não só endpoint: sob RLS, o ON CONFLICT de
        # uma inscrição de OUTRA conta no mesmo navegador leria uma linha que o
        # tenant não enxerga e o upsert estouraria em vez de gravar
        sa.UniqueConstraint("usuario_id", "endpoint", name="uq_push_inscricoes_usuario_endpoint"),
    )
    op.create_index("ix_push_inscricoes_usuario_id", "push_inscricoes", ["usuario_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON push_inscricoes TO {APP_ROLE}")
    op.execute("ALTER TABLE push_inscricoes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE push_inscricoes FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_push_inscricoes_tenant ON push_inscricoes
          FOR ALL
          USING (usuario_id = {UID})
          WITH CHECK (usuario_id = {UID})
        """
    )

    op.add_column("preferencias_usuario", sa.Column("canais_alerta", _TEXTOS, nullable=True))


def downgrade() -> None:
    op.drop_column("preferencias_usuario", "canais_alerta")
    op.drop_index("ix_push_inscricoes_usuario_id", table_name="push_inscricoes")
    op.drop_table("push_inscricoes")
    op.drop_index("ix_programas_fim_beneficiario", table_name="programas")
    op.drop_index("ix_programas_fim_emenda", table_name="programas")
    op.drop_index("ix_programas_fim_proposta", table_name="programas")
    op.drop_table("programas")
