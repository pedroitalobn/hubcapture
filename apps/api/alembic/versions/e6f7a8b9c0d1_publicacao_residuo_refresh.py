"""limpa o resíduo que o refresh diário deixou em execucao, snapshots e alertas (§62)

Revision ID: e6f7a8b9c0d1
Revises: d2e3f4a5b6c7
Create Date: 2026-09-23

Até a §62, `services/propostas.upsert` SUBSTITUÍA `propostas.execucao` inteira a
cada recoleta, apagando o que o pacote SIconv (`convenio`), o enriquecimento
(`webapp`) e a conferência no DOU (`dou`) tinham gravado. O código foi corrigido
(a recoleta agora FUNDE), mas o banco carrega o rastro dos dias em que o estado
oscilou — e é dele que o gestor reclama: "publicada sem ter sido, ou vice-versa".

Migration de DADOS, idempotente. O que foi apagado NÃO volta por aqui (não há
de onde tirar): o pacote (07:00) e o enriquecimento (08:00) reconstroem, e desta
vez o resultado fica. O que ESTA migration faz é tirar do caminho o que ainda
afirma coisa errada e evitar a enxurrada de alertas falsos da reconstrução:

1. `execucao.situacao_publicacao` de TOPO sem nenhum bloco que o sustente
   (`webapp`/`convenio`/`dou` sem a chave) é REMOVIDO. O topo é cópia do que
   esses blocos gravam; sozinho, veio do palpite do normalizador sobre uma
   coluna booleana ou o painel raspado — a classe exata do "Publicado" indevido
   (§56/§56b). O cliente fixou que a resposta está no campo da FICHA da
   proposta (§56b): sem ele, o estado honesto é "sem informação". A recoleta
   seguinte recoloca a chave se o connector ainda a emite (agora por fusão).
2. Carimbo `enriquecimento` sem bloco `webapp` (disc/voluntárias): o job
   marcou que passou, mas o resultado foi apagado pelo refresh — a proposta
   volta ao INÍCIO da fila do enriquecimento em vez de esperar `REVISITA_DIAS`.
3. `monitoramentos.snapshot`: os campos de publicação/empenho/pagamento saem da
   fotografia. Eles fotografaram o estado APAGADO; comparar a reconstrução com
   ele emitiria "passou a publicada"/"empenho novo" para toda proposta que
   sempre esteve assim. Sem a chave, `detect_changes.avaliar` trata a próxima
   varredura como linha de base (§53) — silêncio, não alerta falso. Custo
   assumido: um fato REAL desses critérios ocorrido na janela da oscilação não
   gera alerta (vira baseline).
4. `alertas` (marcados como LIDOS, nunca apagados): (a) os artefatos do
   apagamento — publicação que "desfez" (`publicada` true→false) e empenho/pago
   que caiu para zero/nulo, estados que não existem na fonte; (b) repetições —
   o mesmo `mudou` para a mesma (usuário, proposta, tipo) emitido dia após dia
   pelo ciclo apagar→reconstruir; fica não lido só o mais recente.

Sessão de migration roda como OWNER/superuser (é assim que o compose e o Neon
estão configurados). `propostas` tem a policy de SELECT da plataforma
(`b5c6d7e8f9a0`), então a bandeira `app.plataforma` entra por segurança para o
WHERE ler linha sob FORCE RLS; as contagens saem do rowcount, nunca de um
SELECT posterior (§41).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATAFORMA = "SELECT set_config('app.plataforma', 'on', true)"

#: topo de `execucao` sem bloco que o sustente — o palpite do normalizador
SQL_TOPO_SEM_BLOCO = """
UPDATE propostas
SET execucao = execucao - 'situacao_publicacao'
WHERE jsonb_typeof(execucao) = 'object'
  AND execucao ? 'situacao_publicacao'
  AND coalesce(execucao -> 'webapp'   ->> 'situacao_publicacao', '') = ''
  AND coalesce(execucao -> 'convenio' ->> 'situacao_publicacao', '') = ''
  AND coalesce(execucao -> 'dou'      ->> 'situacao_publicacao', '') = ''
"""

#: carimbo de enriquecimento cujo resultado (bloco webapp) foi apagado
SQL_CARIMBO_SEM_RESULTADO = """
UPDATE propostas
SET execucao = execucao - 'enriquecimento'
WHERE fonte IN ('transferegov_disc', 'transferegov_voluntarias')
  AND jsonb_typeof(execucao) = 'object'
  AND execucao ? 'enriquecimento'
  AND NOT (execucao ? 'webapp')
"""

#: campos do snapshot que fotografaram o estado apagado (CAMPOS_POR_CRITERIO de
#: publicacao · empenho · empenho_pago · pagamento)
CAMPOS_OSCILARAM = (
    "publicada",
    "publicacao_situacao",
    "publicacao_valor",
    "valor_empenhado",
    "empenhos_total",
    "empenhos_empenhado",
    "empenhos_pago",
    "empenhos_liquidado",
    "valor_pago",
    "valor_liberado",
)
_ARRAY_CAMPOS = "ARRAY[" + ", ".join(f"'{c}'" for c in CAMPOS_OSCILARAM) + "]"
SQL_SNAPSHOT_REBASELINE = f"""
UPDATE monitoramentos
SET snapshot = snapshot - {_ARRAY_CAMPOS}
WHERE jsonb_typeof(snapshot) = 'object'
  AND snapshot ?| {_ARRAY_CAMPOS}
"""

_ZERO = r"^0*(\.0+)?$"
#: alerta que registra um estado que não existe na fonte: publicação desfeita,
#: empenho/pago que "voltou a zero" — é o apagamento do refresh, não um fato
SQL_ALERTAS_ARTEFATO = f"""
UPDATE alertas SET lido = true
WHERE lido = false
  AND (
    (tipo = 'publicacao'
     AND payload -> 'mudou' -> 'publicada' ->> 'antes' = 'true'
     AND coalesce(payload -> 'mudou' -> 'publicada' ->> 'depois', 'false') <> 'true')
    OR (tipo = 'empenho'
     AND coalesce(payload -> 'mudou' -> 'valor_empenhado' ->> 'antes', '0') !~ '{_ZERO}'
     AND coalesce(nullif(payload -> 'mudou' -> 'valor_empenhado' ->> 'depois', ''), '0') ~ '{_ZERO}')
    OR (tipo = 'pagamento'
     AND coalesce(payload -> 'mudou' -> 'valor_pago' ->> 'antes', '0') !~ '{_ZERO}'
     AND coalesce(nullif(payload -> 'mudou' -> 'valor_pago' ->> 'depois', ''), '0') ~ '{_ZERO}')
  )
"""

#: o mesmo `mudou` emitido dia após dia para a mesma proposta: fica o mais recente
SQL_ALERTAS_REPETIDOS = """
UPDATE alertas a SET lido = true
FROM (
    SELECT id,
           row_number() OVER (
               PARTITION BY usuario_id, proposta_id, tipo, payload -> 'mudou'
               ORDER BY created_at DESC, id DESC
           ) AS n
    FROM alertas
    WHERE lido = false
      AND proposta_id IS NOT NULL
      AND tipo IN ('publicacao', 'empenho', 'pagamento')
) d
WHERE a.id = d.id AND d.n > 1
"""

PASSOS = (
    ("situacao_publicacao de topo sem bloco removida", SQL_TOPO_SEM_BLOCO),
    ("carimbo de enriquecimento sem resultado removido", SQL_CARIMBO_SEM_RESULTADO),
    ("snapshot de monitoramento re-baseado", SQL_SNAPSHOT_REBASELINE),
    ("alerta-artefato do apagamento marcado como lido", SQL_ALERTAS_ARTEFATO),
    ("alerta repetido marcado como lido", SQL_ALERTAS_REPETIDOS),
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(PLATAFORMA)
    for rotulo, sql in PASSOS:
        resultado = conn.exec_driver_sql(sql)
        print(f"[migration e6f7a8b9c0d1] {resultado.rowcount} linha(s): {rotulo}")


def downgrade() -> None:
    # Limpeza de dado: o que saiu era resíduo sem fonte que o sustentasse, e o
    # que foi marcado como lido segue no banco. Não há estado anterior a repor.
    pass
