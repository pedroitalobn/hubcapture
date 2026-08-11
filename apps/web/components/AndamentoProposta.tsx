"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { BadgeTone } from "@/components/StatusBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { TextoExpansivel } from "@/components/TextoExpansivel";
import { formatBRL, formatDate, humanizarCaixa } from "@/lib/format";

/**
 * Andamento da proposta — a tramitação em UMA linha do tempo.
 *
 * Construída SOBRE os pareceres: cada análise é um passo (com o veredito e quem
 * assinou), e junto entram os marcos que dão contexto — cadastro na fonte,
 * vigência, prazos e pendências. O gestor não pergunta "quais são os
 * pareceres?", pergunta "em que pé está isso?".
 *
 * Uma falha de fonte NÃO substitui a lista: os marcos vêm do cache e continuam
 * na tela; o incidente vira um aviso no topo. Antes, a seção de pareceres
 * trocava tudo por uma mensagem de erro e o gestor perdia o que já era sabido.
 */

type Evento = {
  data?: string | null;
  tipo: string;
  titulo: string;
  detalhe?: string | null;
  ator?: string | null;
  tom?: string | null;
  valor?: string | null;
  texto?: string | null;
  url?: string | null;
  futuro?: boolean | null;
};

type Coleta = {
  pareceres?: { status: string; total: number; erro?: string | null } | null;
};

const TOM_BADGE: Record<string, BadgeTone> = {
  ok: "success",
  warn: "warning",
  danger: "danger",
  neutral: "neutral",
};

const TOM_DOT: Record<string, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
  neutral: "bg-ink-3",
};

/** Rótulo do tipo — o que é este passo, em uma palavra. */
const TIPO_ROTULO: Record<string, string> = {
  proposta: "Proposta",
  parecer: "Parecer",
  vigencia: "Vigência",
  prazo: "Prazo",
  pendencia: "Pendência",
  atualizacao: "Movimentação",
};

function num(v?: string | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

interface Props {
  proposta: { id: string; numero_plano_trabalho?: string | null };
  /** Sem o módulo captação a consulta ao vivo não existe — só o cache (§40). */
  podeConsultarFonte?: boolean;
}

export function AndamentoProposta({ proposta, podeConsultarFonte = true }: Props) {
  const [itens, setItens] = useState<Evento[]>([]);
  const [coleta, setColeta] = useState<Coleta | null>(null);
  const [plano, setPlano] = useState<string | null>(
    proposta.numero_plano_trabalho ?? null,
  );
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);

  const carregar = useCallback(
    async (atualizar = false) => {
      atualizar ? setAtualizando(true) : setCarregando(true);
      const { data } = await api.GET("/api/v1/proposals/{proposta_id}/timeline", {
        params: { path: { proposta_id: proposta.id }, query: { atualizar } },
      });
      if (data) {
        setItens((data.itens ?? []) as Evento[]);
        setColeta((data.coleta ?? null) as Coleta);
        setPlano(data.numero_plano_trabalho ?? null);
      }
      setCarregando(false);
      setAtualizando(false);
    },
    [proposta.id],
  );

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const pareceres = coleta?.pareceres;
  const semPlano = pareceres?.status === "sem_plano_trabalho";
  const erroFonte = pareceres?.status === "erro";

  return (
    <section className="card p-5">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="label-mono">Andamento</h2>
          {plano && (
            <span className="text-xs text-ink-3">
              plano de trabalho <span className="num select-all text-ink-2">{plano}</span>
            </span>
          )}
        </div>
        {plano && podeConsultarFonte && (
          <button
            onClick={() => void carregar(true)}
            disabled={atualizando}
            className="btn btn-ghost btn-sm"
          >
            {atualizando ? "Consultando…" : "Consultar fonte"}
          </button>
        )}
      </div>

      {/* O incidente de fonte é um AVISO, não o conteúdo: o que já está no
          cache continua na tela. */}
      {erroFonte && (
        <p className="tone-warn mb-3 text-xs">
          Não consegui consultar os pareceres na fonte agora
          {pareceres?.erro ? ` (${pareceres.erro})` : ""}. A linha do tempo abaixo é
          o que já estava no cache.
        </p>
      )}
      {semPlano && (
        <p className="mb-3 text-xs text-ink-3">
          Esta proposta ainda não tem número de plano de trabalho no cache — sem ele
          não há como buscar os pareceres na fonte. Ele costuma chegar numa nova coleta.
        </p>
      )}

      {carregando ? (
        <p className="text-sm text-ink-3">Carregando…</p>
      ) : itens.length === 0 ? (
        <p className="text-sm text-ink-3">
          Nenhuma movimentação registrada nesta proposta até agora.
        </p>
      ) : (
        <ol className="relative flex flex-col border-l border-hairline pl-5">
          {itens.map((ev, i) => (
            <li key={`${ev.tipo}-${ev.data ?? "s"}-${i}`} className="relative py-3">
              <span
                className={`absolute -left-[23px] top-[18px] h-[7px] w-[7px] rounded-full ring-2 ring-[var(--surface)] ${
                  TOM_DOT[ev.tom ?? "neutral"] ?? "bg-ink-3"
                }`}
                aria-hidden
              />
              <div className="flex flex-wrap items-center gap-2">
                <span className="num text-sm text-ink">
                  {ev.data ? formatDate(ev.data) : "sem data"}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.04em] text-ink-3">
                  {TIPO_ROTULO[ev.tipo] ?? ev.tipo}
                </span>
                {ev.futuro && (
                  <span className="font-mono text-[10px] uppercase tracking-[0.04em] text-ink-3">
                    a vencer
                  </span>
                )}
              </div>

              <div className="mt-1 flex flex-wrap items-center gap-2">
                {ev.tipo === "parecer" ? (
                  <StatusBadge tone={TOM_BADGE[ev.tom ?? "neutral"] ?? "neutral"}>
                    {ev.titulo}
                  </StatusBadge>
                ) : (
                  <span className="text-sm text-ink">{humanizarCaixa(ev.titulo)}</span>
                )}
                {num(ev.valor) > 0 && (
                  <span className="num text-sm text-ink-2">{formatBRL(ev.valor)}</span>
                )}
              </div>

              {ev.ator && (
                <p className="mt-1 text-sm text-ink-2">{humanizarCaixa(ev.ator)}</p>
              )}
              {ev.detalhe && (
                <p className="text-xs text-ink-3">{humanizarCaixa(ev.detalhe)}</p>
              )}
              {ev.texto && (
                <div className="mt-1.5 max-w-2xl">
                  <TextoExpansivel texto={ev.texto} linhas={3} />
                </div>
              )}
              {ev.url && (
                <a
                  href={ev.url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-ghost btn-sm mt-2"
                >
                  Visualizar ↗
                </a>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
