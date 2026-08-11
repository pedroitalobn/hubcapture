"""backfill de numero_proposta (NR_PROPOSTA) a partir do registro-fonte

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-11

O nº da proposta virou PÍLULA em destaque nas listas (§44) — mas a pílula não
renderiza sem número, e as propostas ingeridas ANTES da calibração do
NR_PROPOSTA (§35b) têm a coluna vazia: o painel abre sem número nenhum, como se
a fonte não publicasse. O dado, porém, já está no banco — `dados_fonte` guarda o
registro-fonte inteiro. Aqui ele é promovido para a coluna.

Duas passadas, na mesma ordem de precedência do normalizador:

1. NR_PROPOSTA explícito SOBRESCREVE o que estiver lá. É a referência oficial e
   vence os demais candidatos (§35b); linha ingerida antes podia ter pescado
   `numero_plano_acao` ou o nº do convênio e mostrar um número que o portal da
   fonte não reconhece.
2. Os demais candidatos preenchem só o que ficou NULL — nunca sobrescrevem.

`dados_fonte` vem em dois formatos: achatado (painel/API) e aninhado sob
`plano_acao` (é o caso do CSV do SIconv, de onde vem o transferegov_disc), e a
CAIXA da chave varia por fonte — o normalizador resolve isso com alias, o jsonb
cru não. Daí o COALESCE cobrindo os dois níveis e as duas caixas.

Aproveita para fechar o mesmo buraco em `data_proposta`: o backfill anterior
(a7b8c9d0e1f2) só olhava o nível raiz, então as linhas do CSV — justamente as
que têm DIA_PROP/MES_PROP/ANO_PROP — passaram batido e seguem no fim da
ordenação "recentes" (§43).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Onde o valor pode estar dentro de `dados_fonte`, do mais específico para o
# mais genérico. `plano_acao->csv` é a LINHA BRUTA que os connectors de CSV
# guardam ao lado do de-para (é onde estava o NR_PROPOSTA que não chegava à
# tela); `csv` cobre o mesmo formato sem o agrupamento.
_NIVEIS = (
    "dados_fonte",
    "dados_fonte->'plano_acao'",
    "dados_fonte->'plano_acao'->'csv'",
    "dados_fonte->'csv'",
)


def _campo(*nomes: str) -> str:
    """COALESCE do campo em todos os níveis do registro-fonte, nas duas caixas."""
    partes = [
        f"NULLIF(btrim({nivel}->>'{chave}'), '')"
        for nome in nomes
        for chave in (nome.lower(), nome.upper())
        for nivel in _NIVEIS
    ]
    return f"COALESCE({', '.join(partes)})"


_NR_PROPOSTA = _campo("nr_proposta")
# mesma ordem de `normalizer.normalize`, sem o NR_PROPOSTA (já aplicado acima)
_OUTROS = _campo(
    "numero_plano_acao",
    "numero_proposta",
    "numero_convenio",
    "nr_convenio",
    "codigo_plano_acao",
)


def upgrade() -> None:
    # 1) NR_PROPOSTA manda — corrige inclusive quem gravou o candidato errado
    op.execute(
        f"""
        UPDATE propostas
           SET numero_proposta = {_NR_PROPOSTA}
         WHERE dados_fonte IS NOT NULL
           AND {_NR_PROPOSTA} IS NOT NULL
           AND numero_proposta IS DISTINCT FROM {_NR_PROPOSTA}
        """
    )
    # 2) demais candidatos só preenchem o vazio
    op.execute(
        f"""
        UPDATE propostas
           SET numero_proposta = {_OUTROS}
         WHERE dados_fonte IS NOT NULL
           AND numero_proposta IS NULL
           AND {_OUTROS} IS NOT NULL
        """
    )
    # 3) data de criação das linhas aninhadas (o backfill anterior só viu a raiz)
    componentes = f"""
        SELECT id,
               {_campo("dia_prop")} AS d,
               {_campo("mes_prop")} AS m,
               {_campo("ano_prop")} AS a
          FROM propostas
         WHERE dados_fonte IS NOT NULL
    """
    # to_date (e não make_date): data impossível que passe pelos guardas não
    # pode derrubar a migration inteira.
    data = "to_date(lpad(s.d, 2, '0') || lpad(s.m, 2, '0') || s.a, 'DDMMYYYY')"
    op.execute(
        f"""
        UPDATE propostas p
           SET data_proposta = {data}
          FROM ({componentes}) s
         WHERE p.id = s.id
           AND s.d ~ '^[0-9]{{1,2}}$' AND s.m ~ '^[0-9]{{1,2}}$' AND s.a ~ '^[0-9]{{4}}$'
           AND s.m::int BETWEEN 1 AND 12
           AND s.d::int BETWEEN 1 AND 31
           AND s.a::int BETWEEN 1990 AND 2100
           AND p.data_proposta IS DISTINCT FROM {data}
        """
    )


def downgrade() -> None:
    # Sem volta: o valor anterior era o vazio (ou o número errado), e depois de
    # sobrescrito não há como distinguir um do outro.
    pass
