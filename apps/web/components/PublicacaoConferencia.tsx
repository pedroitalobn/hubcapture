"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { useEhAdmin } from "@/lib/admin";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/lib/format";

/**
 * "Saiu ou não saiu?" — com as PROVAS ao lado (§56c).
 *
 * O gestor foi informado de propostas publicadas que não tinham sido, e o
 * remédio para isso não é um rótulo mais bonito: é poder conferir. A seção
 * mostra as três evidências que respondem por caminhos independentes — o campo
 * da ficha do TransfereGov, o PDF da publicação anexado à proposta e o extrato
 * no DOU Seção 3 — cada uma com o seu link.
 *
 * Duas regras que a tela não quebra:
 *
 * - **Discordância aparece.** Quando o DOU e a ficha dizem coisas diferentes, os
 *   dois ficam na lista com um aviso. Esconder um dos lados é como o Hub passou
 *   a afirmar o que o portal desmentia.
 * - **Não achar no DOU não é "não foi publicado".** A busca é textual e a fonte
 *   cai; o texto do vazio diz exatamente isso, e nunca nega a publicação.
 */

type Evidencia = {
  tipo: string;
  rotulo: string;
  detalhe?: string | null;
  data?: string | null;
  url?: string | null;
};

type Conferencia = {
  status: string;
  confirmado: boolean;
  termos?: string[];
  erro?: string | null;
};

type Publicacao = { estado: string; rotulo: string };

const TIPO_ROTULO: Record<string, string> = {
  dou: "Diário Oficial",
  campo: "Ficha da proposta",
  documento: "Documento anexado",
};

const TOM: Record<string, "success" | "danger" | "neutral"> = {
  publicado: "success",
  nao_publicado: "danger",
  sem_informacao: "neutral",
};

interface Props {
  proposta: { id: string };
  /** Conferir no DOU é consulta ATIVA — obedece ao módulo captação (§40). */
  podeConsultarFonte?: boolean;
}

export function PublicacaoConferencia({ proposta, podeConsultarFonte = true }: Props) {
  const admin = useEhAdmin();
  const [publicacao, setPublicacao] = useState<Publicacao | null>(null);
  const [evidencias, setEvidencias] = useState<Evidencia[]>([]);
  const [conferencia, setConferencia] = useState<Conferencia | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [conferindo, setConferindo] = useState(false);

  const carregar = useCallback(
    async (conferir = false) => {
      conferir ? setConferindo(true) : setCarregando(true);
      try {
        const { data } = await api.GET("/api/v1/proposals/{proposta_id}/publication", {
          params: { path: { proposta_id: proposta.id }, query: { conferir } },
        });
        if (data) {
          setPublicacao(data.publicacao as Publicacao);
          setEvidencias((data.evidencias ?? []) as Evidencia[]);
          setConferencia(data.conferencia as Conferencia);
        }
      } finally {
        // handler async que liga um estado de "…ando" desliga no finally (§52):
        // promessa rejeitada deixaria o botão preso em "Conferindo…" para sempre
        setCarregando(false);
        setConferindo(false);
      }
    },
    [proposta.id],
  );

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const doDou = evidencias.filter((e) => e.tipo === "dou");
  const daFicha = evidencias.filter((e) => e.tipo === "campo");
  // Divergência = o ato publicado e a declaração do sistema discordam. Não é
  // defeito nosso nem da fonte: o TransfereGov leva alguns dias para refletir a
  // publicação. O gestor precisa ver os dois para decidir.
  const veredito = doDou[0]?.rotulo;
  const divergem = veredito !== undefined && daFicha.some((e) => e.rotulo !== veredito);

  return (
    <section className="card p-5">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="label-mono">Publicação</h2>
          {publicacao && (
            <StatusBadge tone={TOM[publicacao.estado] ?? "neutral"}>
              {publicacao.rotulo}
            </StatusBadge>
          )}
        </div>
        {podeConsultarFonte && (
          <button
            onClick={() => void carregar(true)}
            disabled={conferindo}
            className="btn btn-ghost btn-sm"
          >
            {conferindo ? "Conferindo…" : "Conferir no Diário Oficial"}
          </button>
        )}
      </div>

      {divergem && (
        <p className="mb-3 text-sm text-ink-2">
          O extrato no Diário Oficial e a ficha da proposta estão diferentes. O
          Diário Oficial é o ato; a ficha costuma levar alguns dias para
          acompanhar.
        </p>
      )}

      {carregando ? (
        <p className="text-sm text-ink-3">Carregando…</p>
      ) : evidencias.length === 0 ? (
        <p className="text-sm text-ink-3">
          Nenhuma evidência de publicação até agora — nem na ficha da proposta,
          nem em documento anexado.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-hairline">
          {evidencias.map((e, i) => (
            <li
              key={`${e.tipo}-${i}`}
              className="flex flex-wrap items-center justify-between gap-3 py-3"
            >
              <span className="flex min-w-0 flex-col gap-1">
                <span className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={e.tipo === "dou" ? "success" : "neutral"}>
                    {TIPO_ROTULO[e.tipo] ?? "Evidência"}
                  </StatusBadge>
                  <span className="text-sm text-ink">{e.rotulo}</span>
                  {e.data && (
                    <span className="num text-xs text-ink-3">{formatDate(e.data)}</span>
                  )}
                </span>
                {e.detalhe && (
                  <span className="break-words text-xs text-ink-3">{e.detalhe}</span>
                )}
              </span>
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-ghost btn-sm shrink-0"
                >
                  Abrir ↗
                </a>
              )}
            </li>
          ))}
        </ul>
      )}

      {conferencia && conferencia.status !== "nao_consultado" && (
        <div className="mt-3 flex flex-col gap-1 border-t border-hairline pt-3">
          <p className="text-xs text-ink-3">
            {conferencia.confirmado
              ? "Publicação confirmada no Diário Oficial da União, Seção 3."
              : conferencia.status === "sem_termo"
                ? "Sem nota de empenho registrada nesta proposta — é por ela que a busca no Diário Oficial é feita. Consulte os empenhos primeiro."
                : conferencia.status === "erro"
                  ? "Não foi possível consultar o Diário Oficial agora — isso não quer dizer que a proposta não tenha sido publicada."
                  : "Nada encontrado no Diário Oficial para esta proposta. A busca é por texto, então não encontrar não significa que não tenha saído."}
          </p>
          {admin && (conferencia.termos?.length ?? 0) > 0 && (
            <p className="num text-xs text-ink-3">
              Procurado por: {conferencia.termos!.join(" · ")}
            </p>
          )}
          {admin && conferencia.erro && (
            <details className="text-xs text-ink-3">
              <summary className="cursor-pointer select-none">
                Detalhe técnico (para a administração)
              </summary>
              <p className="mt-1.5 break-words">{conferencia.erro}</p>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
