"""proposta_emendas: sessão de plataforma enxerga o cache inteiro

A carga diária do SIconv (`jobs/siconv_diario`) é GLOBAL — grava emenda de
qualquer município do país, sem tenant. E `INSERT … ON CONFLICT DO UPDATE`
aplica a policy de **SELECT** sobre a linha nova, não só as de INSERT/UPDATE
(o Postgres pode precisar lê-la). Como a policy de SELECT recorta por
`municipios_interesse` e o job não tem `app.usuario_id`, TODA linha com
`municipio_ibge` preenchido era recusada com "new row violates row-level
security policy" — e nenhuma emenda entrava.

A saída é a mesma que `demandas` já usa: uma policy PERMISSIVE adicional que
reconhece a bandeira `app.plataforma` (ligada por `db.session.plataforma_session`
e pelo job). Policies permissivas somam com OR, então a policy por município
segue intacta para o request do usuário — quem não liga a bandeira continua
vendo só o próprio território.

Mesmo tratamento em `proposta_empenhos` e `pareceres`, que têm a mesma policy
e serão alimentados pelo mesmo caminho quando a cadeia de execução entrar.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from __future__ import annotations

from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

# `nullif` antes da comparação: sessão sem a bandeira devolve string vazia, e
# comparar vazio com 'on' é falso — do jeito certo, sem erro de cast.
PLATAFORMA = "nullif(current_setting('app.plataforma', true), '') = 'on'"

TABELAS = ("proposta_emendas", "proposta_empenhos", "pareceres")


def upgrade() -> None:
    for tabela in TABELAS:
        op.execute(
            f"CREATE POLICY p_{tabela}_plataforma ON {tabela} " f"FOR SELECT USING ({PLATAFORMA})"
        )


def downgrade() -> None:
    for tabela in TABELAS:
        op.execute(f"DROP POLICY IF EXISTS p_{tabela}_plataforma ON {tabela}")
