"""Carga global de propostas: a sessão de plataforma precisa enxergar o cache

A carga diária do pacote SIconv (`jobs/siconv_diario`) passou a alimentar
`propostas` — a tabela canônica de captação — com o arquivo NACIONAL do
TransfereGov. O job é global: roda sem tenant, com `app.plataforma = on`.

Dois bloqueios de RLS estavam no caminho, e os dois são silenciosos (entregam
zero linha em vez de erro visível):

1. **`propostas`** — `INSERT … ON CONFLICT DO UPDATE` aplica a policy de
   **SELECT** sobre a linha existente, não só as de INSERT/UPDATE. Como
   `p_propostas_select` recorta por `municipios_interesse` e o job não tem
   `app.usuario_id`, toda proposta que já estivesse no cache seria recusada com
   "new row violates row-level security policy". Mesmo tropeço documentado na
   §50 para `proposta_emendas`, e a saída é a mesma: uma policy PERMISSIVE
   adicional que reconhece a bandeira. Policies permissivas somam com OR, então
   o recorte por município segue valendo para o request do usuário.

2. **`municipios_interesse`** — o recorte padrão da carga é o TERRITÓRIO
   monitorado (o arquivo é nacional; carregar o país inteiro são milhões de
   linhas). Ler a lista exige atravessar o `FOR ALL` por-tenant, que sob FORCE
   RLS bloqueia até o owner. Aqui a policy nova é **só de SELECT** e só sob a
   bandeira: escrita segue exclusivamente por-tenant, e quem não liga a
   bandeira continua vendo apenas o próprio território. A bandeira é ligada por
   `db.session.plataforma_session` (rotas de admin) e pelos jobs.

E, de quebra, o `id_externo` das propostas do CSV passou a ser SEMPRE
`ID_PROPOSTA` (a chave primária publicada pela fonte), para os dois caminhos de
ingestão — busca ao vivo e carga do pacote — convergirem na MESMA linha em vez
de duplicar a proposta no painel. As linhas gravadas com a identidade anterior
(o nº do convênio, quando o arquivo o trazia) ficariam órfãs: são MARCADAS
(soft delete da §41 — nunca apagadas, o cascade ignora RLS e levaria junto a
curadoria dos usuários). É auto-corrigível: o upsert zera `excluido_em`, então
a linha volta assim que a fonte a reemitir sob o id certo.

Revision ID: b5c6d7e8f9a0
Revises: a1b2c3d4e5f7
"""

from __future__ import annotations

from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None

# `nullif` antes da comparação: sessão sem a bandeira devolve string vazia e
# comparar vazio com 'on' é falso — do jeito certo, sem erro de cast.
PLATAFORMA = "nullif(current_setting('app.plataforma', true), '') = 'on'"


def upgrade() -> None:
    op.execute(f"CREATE POLICY p_propostas_plataforma ON propostas FOR SELECT USING ({PLATAFORMA})")
    op.execute(
        "CREATE POLICY p_municipios_interesse_plataforma ON municipios_interesse "
        f"FOR SELECT USING ({PLATAFORMA})"
    )

    # Identidade antiga do CSV: `id_externo` que não é o ID_PROPOSTA da linha.
    # Sem WHERE de leitura cruzada com o RLS — o UPDATE precisa LER a linha, e
    # esta migration roda como owner na conexão do migrator, que não passa pela
    # policy por município apenas porque a bandeira acima já existe. Ligamo-la
    # explicitamente na transação para não depender de ordem de aplicação.
    op.execute("SELECT set_config('app.plataforma', 'on', true)")
    op.execute(
        """
        UPDATE propostas
           SET excluido_em = now(), cache_atualizado_em = NULL
         WHERE fonte = 'transferegov_disc'
           AND excluido_em IS NULL
           AND coalesce(
                 dados_fonte -> 'plano_acao' -> 'csv' ->> 'ID_PROPOSTA',
                 dados_fonte -> 'plano_acao' -> 'csv' ->> 'id_proposta'
               ) IS NOT NULL
           AND coalesce(
                 dados_fonte -> 'plano_acao' -> 'csv' ->> 'ID_PROPOSTA',
                 dados_fonte -> 'plano_acao' -> 'csv' ->> 'id_proposta'
               ) <> id_externo
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS p_propostas_plataforma ON propostas")
    op.execute("DROP POLICY IF EXISTS p_municipios_interesse_plataforma ON municipios_interesse")
