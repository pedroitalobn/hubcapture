"""backfill de data_proposta a partir de DIA_PROP+MES_PROP+ANO_PROP

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-11

O painel passou a ordenar por `data_proposta` (a data de CRIAÇÃO da proposta na
fonte) em vez de `cache_atualizado_em` (quando NÓS coletamos). O normalizador já
remonta essa data das três variáveis oficiais do SIconv — DIA_PROP, MES_PROP e
ANO_PROP —, mas as linhas ingeridas antes disso têm a coluna vazia ou montada de
um candidato errado, e ficariam todas no fim da lista até a próxima recoleta.

Aqui a data é remontada direto do registro-fonte já guardado em `dados_fonte`,
com as mesmas três variáveis. Só toca em linha cujos três componentes existem e
são plausíveis; o resto continua como está (e a recoleta resolve).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# CAIXA da chave varia por fonte (o CSV do SIconv manda em maiúsculas); o
# normalizador trata isso com alias, o jsonb bruto não — daí o COALESCE.
_COMPONENTES = """
    SELECT id,
           btrim(COALESCE(dados_fonte->>'DIA_PROP', dados_fonte->>'dia_prop')) AS d,
           btrim(COALESCE(dados_fonte->>'MES_PROP', dados_fonte->>'mes_prop')) AS m,
           btrim(COALESCE(dados_fonte->>'ANO_PROP', dados_fonte->>'ano_prop')) AS a
      FROM propostas
     WHERE dados_fonte IS NOT NULL
"""

# to_date (e não make_date) de propósito: não levanta exceção em data
# impossível que tenha passado pelos guardas — um registro sujo não pode
# derrubar a migration inteira.
_DATA = "to_date(lpad(s.d, 2, '0') || lpad(s.m, 2, '0') || s.a, 'DDMMYYYY')"

_PLAUSIVEL = """
      s.d ~ '^[0-9]{1,2}$' AND s.m ~ '^[0-9]{1,2}$' AND s.a ~ '^[0-9]{4}$'
      AND s.m::int BETWEEN 1 AND 12
      AND s.d::int BETWEEN 1 AND 31
      AND s.a::int BETWEEN 1990 AND 2100
"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE propostas p
           SET data_proposta = {_DATA}
          FROM ({_COMPONENTES}) s
         WHERE p.id = s.id
           AND {_PLAUSIVEL}
           AND p.data_proposta IS DISTINCT FROM {_DATA}
        """
    )


def downgrade() -> None:
    # Sem volta: a data anterior era justamente a que estava errada (ou vazia),
    # e não há como distingui-la da correta depois de sobrescrita.
    pass
