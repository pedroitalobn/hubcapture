"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { useEhAdmin } from "@/lib/admin";
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
  /** A execução vem junto porque a seção precisa saber o que a faixa de
   *  destaque está mostrando: sem isso ela afirmava "nenhum empenho emitido"
   *  logo abaixo de um "Empenhado R$ 500.000" — a mesma tela dizendo as duas
   *  coisas. Os dois números têm origens diferentes (§56), e é isso que o
   *  texto passa a explicar. */
  proposta: { id: string; execucao?: { valor_empenhado?: string | null } | null };
  podeConsultarFonte?: boolean;
}

export function EmpenhosProposta({ proposta, podeConsultarFonte = true }: Props) {
  const admin = useEhAdmin();
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
  // …a não ser que a FONTE informe empenho no agregado. Aí "nenhum empenho
  // emitido" é falso: o que falta é o documento, não a reserva orçamentária.
  const agregado = num(proposta.execucao?.valor_empenhado);

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
          {/* Falha de fonte não é conteúdo para o gestor: a tela diz que não
              consultou; o texto cru do connector aparece só para a
              administração (Administração → Configurações → Fontes). */}
          <p className="text-sm text-ink-3">
            Não foi possível consultar a fonte agora.
          </p>
          {admin && coleta.erro && (
            <details className="text-xs text-ink-3">
              <summary className="cursor-pointer select-none">
                Detalhe técnico (para a administração)
              </summary>
              <p className="mt-1.5 break-words">
                {coleta.erro} A rota é calibrável em Administração →
                Configurações → Fontes.
              </p>
            </details>
          )}
        </div>
      ) : coleta?.status === "sem_chave" ? (
        <p className="text-sm text-ink-3">Sem dados.</p>
      ) : semEmpenho && agregado > 0 ? (
        <p className="text-sm text-ink-3">
          A fonte informa <strong className="font-medium text-ink">{formatBRL(
            proposta.execucao?.valor_empenhado,
          )}</strong>{" "}
          empenhados para esta proposta, mas ainda não publicou as notas de
          empenho na consulta de documentos. O valor da faixa acima vem desse
          total informado pela fonte; o detalhe nota a nota aparece aqui quando
          a fonte publicar.
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
