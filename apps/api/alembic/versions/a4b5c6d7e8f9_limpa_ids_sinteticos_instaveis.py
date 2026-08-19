"""limpa identificadores sintéticos instáveis (id_externo posicional/não escopado)

Revision ID: a4b5c6d7e8f9
Revises: e2f3a4b5c6d7
Create Date: 2026-08-19

O par `unique (fonte, id_externo)` é a chave do upsert da coleta: é por ele que
a ingestão decide se ATUALIZA uma linha ou CRIA outra. Alguns connectors caíam
numa retaguarda de identificador que não servia como identidade:

* POSICIONAL — `i`, `len(records) + 1`, `painel-{ibge}-{i}`: a posição muda a
  cada coleta (a fonte reordena, uma linha entra no meio), então a MESMA
  transferência trocava de identidade entre rodadas. É a contagem do município
  que "fica mudando" sem nada ter mudado na fonte.
* NÃO ESCOPADO NO MUNICÍPIO — `i` puro e `str(None)` (que vira o id literal
  "None"): o par único é GLOBAL. A proposta "1" de um município e a "1" de
  outro são a MESMA linha para o banco; uma sobrescrevia a outra e a linha
  mudava de território, fazendo o filtro de município mostrar dado que não é
  dali.

Os connectors passaram a derivar a identidade do CONTEÚDO da linha, escopada no
município (`connectors/_identidade.py`). As linhas gravadas com o esquema antigo
não serão mais reemitidas — ficariam órfãs no painel para sempre, congeladas e
possivelmente no município errado.

Por isso esta migration as MARCA (soft delete), nunca apaga: `propostas` é cache
global e o cascade das FKs ignora RLS — um DELETE levaria junto favoritos,
pastas e alertas de qualquer usuário (ver f6a7b8c9d0e1). A marcação é
auto-corrigível nos dois sentidos: o upsert zera `excluido_em`, então uma linha
cujo id era LEGÍTIMO (um `id_proposta` de fato curto, por exemplo) volta sozinha
na próxima coleta, e o "Atualizar fontes" do painel a traz na hora.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Cada padrão é o formato EXATO que a retaguarda antiga produzia — nada de
# heurística larga sobre id de fonte real.
_MARCAR = """
UPDATE propostas SET excluido_em = now()
WHERE excluido_em IS NULL
  AND (
    -- transferegov_esp: `str(row.get(ID) or row.get("id"))` com ambos ausentes
    (fonte = 'transferegov_esp' AND id_externo = 'None')
    -- serpro: `painel-{ibge}-{posição}`
    OR (fonte = 'serpro' AND id_externo ~ '^painel-[0-9]+-[0-9]+$')
    -- transferegov_voluntarias: um registro por página, sem conteúdo na chave
    OR (fonte = 'transferegov_voluntarias' AND id_externo ~ '^scrape-[0-9]+$')
    -- disc/voluntarias: contador posicional ("1", "2", "3"… em TODO município)
    OR (fonte IN ('transferegov_disc', 'transferegov_voluntarias')
        AND id_externo ~ '^[0-9]{1,4}$')
  )
"""


def upgrade() -> None:
    # Sessão de migration roda como OWNER (sem tenant): sob o FORCE RLS de
    # `propostas` um WHERE que LÊ linha enxergaria zero (mesmo motivo do
    # DELETE /admin/proposals). O owner é dono da tabela e não é filtrado pelas
    # policies, então aqui o WHERE vale — mas a contagem sai do rowcount, nunca
    # de um SELECT count(*) posterior.
    resultado = op.get_bind().exec_driver_sql(_MARCAR)
    print(f"[migration a4b5c6d7e8f9] {resultado.rowcount} proposta(s) com id sintético marcadas")


def downgrade() -> None:
    # Não há como distinguir estas marcações das de uma zeragem legítima
    # (admin ou usuário) depois do fato — desmarcar tudo devolveria ao painel
    # proposta que alguém zerou de propósito. A coleta seguinte ressuscita o que
    # a fonte ainda publica, que é o caminho certo de volta.
    pass
