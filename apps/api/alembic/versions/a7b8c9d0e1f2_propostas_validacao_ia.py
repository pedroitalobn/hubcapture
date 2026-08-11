"""propostas.validacao_ia + expurgo do resíduo de coleta já cacheado

Duas coisas, porque a coluna sem a limpeza não resolve o que o gestor está
vendo hoje no painel:

1. `validacao_ia` (jsonb) — cursor da auditoria por IA de `jobs/validacao.py`.
   NULL = ainda não auditada. Dado DERIVADO como `categorias_ia`: fica fora do
   `_UPSERT_FIELDS` da ingestão, para um re-sync não apagar a auditoria.

2. Expurgo das linhas que a triagem (`ingestion/validador.py`) agora barra na
   porta, mas que entraram antes dela existir: propostas cujo `id_externo` é um
   identificador FABRICADO pela coleta ("scrape-2611606", "painel-3550308-0") e
   propostas sem nada que as identifique (sem título, sem objeto, sem número).
   Elas apareciam no painel com o nome da etapa de scraping no lugar do nome do
   programa. As FKs de favoritos/pastas/monitoramentos/alertas/embeddings são
   ON DELETE CASCADE, então o vínculo some junto.

O expurgo é conservador de propósito — o mesmo critério do validador, que é de
evidência forte. Proposta com título ou número REAL não é tocada aqui, mesmo
tendo vindo de scraping; essa é a alçada da auditoria por IA, que sabe olhar o
conteúdo.

Revision ID: a7b8c9d0e1f2
Revises: e5f6a7b8c9d0
Create Date: 2026-08-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# espelha `ingestion/validador._ID_SINTETICO` — nomes de etapa do pipeline que
# a coleta usava como identificador quando não achava o da fonte. `~*` é o
# match de regex case-insensitive do Postgres (o mesmo padrão do validador).
_ID_SINTETICO = (
    r"^(scrape|scraping|crawl4ai|firecrawl|playwright|painel"
    r"|erro|error|none|null|undefined)([-_].*)?$"
)


def upgrade() -> None:
    op.add_column(
        "propostas",
        sa.Column("validacao_ia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # 1) identificador fabricado pela coleta ("scrape-2611606", "painel-…-0", …)
    op.execute(
        sa.text("DELETE FROM propostas WHERE id_externo ~* :padrao").bindparams(
            padrao=_ID_SINTETICO
        )
    )

    # 2) registro sem nada que o identifique (título, objeto ou número). O
    # `btrim` cobre o campo que veio só com espaço, que não é NULL mas é vazio.
    op.execute(
        """
        DELETE FROM propostas
         WHERE coalesce(btrim(titulo), '') = ''
           AND coalesce(btrim(objeto), '') = ''
           AND coalesce(btrim(numero_proposta), '') = ''
           AND coalesce(btrim(numero_plano_trabalho), '') = ''
        """
    )


def downgrade() -> None:
    # o expurgo não volta: as linhas apagadas eram resíduo de coleta, e a
    # coleta seguinte repõe qualquer proposta real do território.
    op.drop_column("propostas", "validacao_ia")
