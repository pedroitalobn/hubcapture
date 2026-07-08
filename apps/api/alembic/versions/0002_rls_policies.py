"""RLS policies (multi-tenancy por usuario_id)

Revision ID: 0002_rls_policies
Revises: a7cea6e95621
Create Date: 2026-07-08

Modelo de isolamento (ver CLAUDE.md / plano):
- Tabelas por-tenant (municipios_interesse, preferencias_usuario, favoritos,
  pastas, pasta_propostas, monitoramentos, alertas, audit_log): RLS FOR ALL por
  usuario_id = current_setting('app.usuario_id').
- propostas / proposta_embeddings = CACHE GLOBAL público: RLS só no SELECT
  (filtra por municípios de interesse do usuário); INSERT/UPDATE/DELETE livres
  para a role de app (senão o upsert do cache-first quebraria em WITH CHECK).
- usuarios: SEM RLS (lookup por email no login acontece antes de haver tenant;
  isolamento é por não expor endpoint de listagem).
- sync_runs: SEM RLS (tabela operacional; usuario_id pode ser null em sync global).
- FORCE ROW LEVEL SECURITY para o próprio owner também respeitar (evita falso-verde).
- current_setting(..., true) => missing_ok; sem tenant setado a policy nega tudo.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_rls_policies"
down_revision: str | None = "a7cea6e95621"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hubcapture_app"

# tabelas isoladas diretamente por usuario_id
TENANT_TABLES = [
    "municipios_interesse",
    "preferencias_usuario",
    "favoritos",
    "pastas",
    "monitoramentos",
    "alertas",
    "audit_log",
]

UID = "current_setting('app.usuario_id', true)::uuid"


def upgrade() -> None:
    # 0) privilégios de tabela para a role de app (cinto-e-suspensório com o init)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    # 1) tabelas por-tenant: RLS FOR ALL por usuario_id
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY p_{t}_tenant ON {t}
              FOR ALL
              USING (usuario_id = {UID})
              WITH CHECK (usuario_id = {UID})
            """
        )

    # 2) pasta_propostas: escopo via pastas do usuário
    op.execute("ALTER TABLE pasta_propostas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pasta_propostas FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_pasta_propostas_tenant ON pasta_propostas
          FOR ALL
          USING (pasta_id IN (SELECT id FROM pastas WHERE usuario_id = {UID}))
          WITH CHECK (pasta_id IN (SELECT id FROM pastas WHERE usuario_id = {UID}))
        """
    )

    # 3) propostas: cache global. SELECT filtra por município de interesse;
    #    INSERT/UPDATE/DELETE livres (upsert do cache-first).
    op.execute("ALTER TABLE propostas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE propostas FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_propostas_select ON propostas
          FOR SELECT
          USING (municipio_ibge IN (
            SELECT ibge FROM municipios_interesse WHERE usuario_id = {UID}
          ))
        """
    )
    op.execute("CREATE POLICY p_propostas_insert ON propostas FOR INSERT WITH CHECK (true)")
    op.execute("CREATE POLICY p_propostas_update ON propostas FOR UPDATE USING (true) WITH CHECK (true)")
    op.execute("CREATE POLICY p_propostas_delete ON propostas FOR DELETE USING (true)")

    # 4) proposta_embeddings: mesma lógica (SELECT por município via proposta)
    op.execute("ALTER TABLE proposta_embeddings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE proposta_embeddings FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY p_proposta_embeddings_select ON proposta_embeddings
          FOR SELECT
          USING (proposta_id IN (
            SELECT id FROM propostas WHERE municipio_ibge IN (
              SELECT ibge FROM municipios_interesse WHERE usuario_id = {UID}
            )
          ))
        """
    )
    op.execute("CREATE POLICY p_proposta_embeddings_insert ON proposta_embeddings FOR INSERT WITH CHECK (true)")
    op.execute("CREATE POLICY p_proposta_embeddings_update ON proposta_embeddings FOR UPDATE USING (true) WITH CHECK (true)")
    op.execute("CREATE POLICY p_proposta_embeddings_delete ON proposta_embeddings FOR DELETE USING (true)")


def downgrade() -> None:
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS p_{t}_tenant ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS p_pasta_propostas_tenant ON pasta_propostas")
    op.execute("ALTER TABLE pasta_propostas DISABLE ROW LEVEL SECURITY")

    for pol in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS p_propostas_{pol} ON propostas")
        op.execute(f"DROP POLICY IF EXISTS p_proposta_embeddings_{pol} ON proposta_embeddings")
    op.execute("ALTER TABLE propostas DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE proposta_embeddings DISABLE ROW LEVEL SECURITY")
