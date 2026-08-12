"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { StatusBadge } from "@/components/StatusBadge";
import { formatBRL, formatDate, humanizarCaixa } from "@/lib/format";

/**
 * Empenhos da proposta — os documentos que reservam o recurso no orçamento.
 *
 * O empenho não vem na linha do plano de ação; mora em rota própria do módulo
 * especiais, consultada pelo número da proposta. A seção soma os documentos
 * (empenhado líquido das anulações e pago); o "a utilizar" (empenhado − pago)
 * saiu daqui — era conta derivada que nas propostas dava zero. A faixa de
 * destaque da página mostra o valor global da fonte (VL_GLOBAL_PROP).
 */

export type EmpenhoResumo = {
  total: number;
  valor_empenhado?: string | null;
  valor_anulado?: string | null;
  valor_liquidado?: string | null;
  valor_pago?: string | null;
  valor_a_utilizar?: string | null;
  primeiro_empenho?: string | null;
  ultimo_empenho?: string | null;
};

type Empenho = {
  id: string;
  numero_empenho?: string | null;
  data_empenho?: string | null;
  tipo_empenho?: string | null;
  situacao?: string | null;
  valor_empenhado?: string | null;
  valor_anulado?: string | null;
  valor_liquidado?: string | null;
  valor_pago?: string | null;
  ug_emitente?: string | null;
  natureza_despesa?: string | null;
  fonte_recurso?: string | null;
  programa_trabalho?: string | null;
};

type Coleta = { status: string; total: number; origem?: string | null; erro?: string | null };

function num(v?: string | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

interface Props {
  proposta: { id: string };
  podeConsultarFonte?: boolean;
}

export function EmpenhosProposta({ proposta, podeConsultarFonte = true }: Props) {
  const [itens, setItens] = useState<Empenho[]>([]);
  const [resumo, setResumo] = useState<EmpenhoResumo | null>(null);
  const [coleta, setColeta] = useState<Coleta | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);

  const carregar = useCallback(
    async (atualizar = false) => {
      atualizar ? setAtualizando(true) : setCarregando(true);
      const { data } = await api.GET("/api/v1/proposals/{proposta_id}/commitments", {
        params: { path: { proposta_id: proposta.id }, query: { atualizar } },
      });
      if (data) {
        setItens((data.itens ?? []) as Empenho[]);
        setResumo((data.resumo ?? null) as EmpenhoResumo | null);
        setColeta(data.coleta as Coleta);
      }
      setCarregando(false);
      setAtualizando(false);
    },
    [proposta.id],
  );

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Sem empenho e sem incidente: a proposta ainda não teve recurso reservado.
  // Isso é informação, não vazio — o gestor precisa saber que não saiu do papel.
  const semEmpenho = !carregando && itens.length === 0 && coleta?.status === "ok";

  return (
    <section className="card p-5">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="label-mono">Empenhos</h2>
          {resumo && resumo.total > 0 && (
            <span className="text-xs text-ink-3">
              {resumo.total} documento{resumo.total > 1 ? "s" : ""}
            </span>
          )}
        </div>
        {podeConsultarFonte && (
          <button
            onClick={() => void carregar(true)}
            disabled={atualizando}
            className="btn btn-ghost btn-sm"
          >
            {atualizando ? "Consultando…" : "Consultar fonte"}
          </button>
        )}
      </div>

      {carregando ? (
        <p className="text-sm text-ink-3">Carregando…</p>
      ) : coleta?.status === "erro" ? (
        <div className="flex flex-col gap-1">
          <p className="tone-warn text-sm">
            Não consegui consultar os empenhos desta proposta na fonte.
          </p>
          <p className="text-xs text-ink-3">
            {coleta.erro ?? "Fonte indisponível."} Um administrador pode calibrar a
            rota em Administração → Configuração → Fontes.
          </p>
        </div>
      ) : coleta?.status === "sem_chave" ? (
        <p className="text-sm text-ink-3">
          Esta proposta ainda não tem número no cache — o empenho é consultado por
          ele. O número costuma chegar numa nova coleta.
        </p>
      ) : semEmpenho ? (
        <p className="text-sm text-ink-3">
          Nenhum empenho emitido até agora — o recurso desta proposta ainda não foi
          reservado no orçamento.
        </p>
      ) : (
        <>
          {resumo && (
            <div className="data-grid mb-4">
              <Valor rotulo="Empenhado" valor={resumo.valor_empenhado} destaque />
              <Valor rotulo="Pago" valor={resumo.valor_pago} />
              {num(resumo.valor_anulado) > 0 && (
                <Valor rotulo="Anulado" valor={resumo.valor_anulado} tom="danger" />
              )}
            </div>
          )}

          <ul className="flex flex-col divide-y divide-hairline">
            {itens.map((e) => {
              const anulado = num(e.valor_anulado);
              const liquido = num(e.valor_empenhado) - anulado;
              return (
                <li
                  key={e.id}
                  className="flex flex-wrap items-start justify-between gap-4 py-3"
                >
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="num text-sm text-ink">
                        {formatDate(e.data_empenho)}
                      </span>
                      {e.numero_empenho && (
                        <span className="num select-all text-sm text-ink-2">
                          {e.numero_empenho}
                        </span>
                      )}
                      {anulado > 0 && (
                        <StatusBadge tone={liquido > 0 ? "warning" : "danger"}>
                          {liquido > 0 ? "anulado em parte" : "anulado"}
                        </StatusBadge>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-3">
                      {[
                        humanizarCaixa(e.ug_emitente),
                        humanizarCaixa(e.tipo_empenho),
                        e.natureza_despesa,
                        humanizarCaixa(e.situacao),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-wrap gap-x-5 gap-y-1">
                    <Valor rotulo="Empenhado" valor={String(liquido)} />
                    {num(e.valor_pago) > 0 && (
                      <Valor rotulo="Pago" valor={e.valor_pago} />
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

function Valor({
  rotulo,
  valor,
  tom,
  destaque,
}: {
  rotulo: string;
  valor?: string | null;
  tom?: "ok" | "danger";
  destaque?: boolean;
}) {
  return (
    <span className="field">
      <span className="field-label">{rotulo}</span>
      <span
        className={[
          destaque ? "value-lg" : "num text-sm",
          tom === "ok" ? "tone-ok" : tom === "danger" ? "tone-danger" : "text-ink",
        ].join(" ")}
      >
        {formatBRL(valor)}
      </span>
    </span>
  );
}
