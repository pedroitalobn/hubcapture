"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { formatBRL, humanizarCaixa } from "@/lib/format";

/**
 * De quem é o dinheiro desta proposta — a emenda parlamentar e o AUTOR.
 *
 * É informação de ação, não de arquivo: é com o gabinete do autor que o gestor
 * negocia o empenho. Por isso o parlamentar lidera o card e o número da emenda
 * (o que se digita no portal para conferir) vem logo abaixo; identificadores
 * internos não aparecem (§35).
 *
 * A resposta diz de onde veio: `registro_fonte` significa que a rota específica
 * da emenda não respondeu e o que está na tela é o que o próprio plano de ação
 * já trazia — menos campos, mesmo autor. Sem isso, "não consegui consultar" e
 * "esta proposta não tem emenda" virariam a mesma tela vazia.
 */

type Emenda = {
  id: string;
  codigo_emenda?: string | null;
  numero_emenda?: string | null;
  ano?: number | null;
  tipo_emenda?: string | null;
  parlamentar?: string | null;
  partido?: string | null;
  uf_parlamentar?: string | null;
  cargo_parlamentar?: string | null;
  valor?: string | null;
  valor_empenhado?: string | null;
  valor_pago?: string | null;
  funcao?: string | null;
  url_origem?: string | null;
};

type Coleta = {
  status: string;
  total: number;
  origem?: string | null;
  erro?: string | null;
};

function num(v?: string | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/** "FULANA DE TAL" + "XYZ" + "CE" → "Fulana de Tal (XYZ/CE)" */
function autorCompleto(e: Emenda): string {
  const nome = humanizarCaixa(e.parlamentar) || "Autor não informado na fonte";
  const sigla = [e.partido, e.uf_parlamentar].filter(Boolean).join("/");
  return sigla ? `${nome} (${sigla})` : nome;
}

interface Props {
  proposta: { id: string };
  podeConsultarFonte?: boolean;
}

export function EmendasProposta({ proposta, podeConsultarFonte = true }: Props) {
  const [itens, setItens] = useState<Emenda[]>([]);
  const [coleta, setColeta] = useState<Coleta | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);

  const carregar = useCallback(
    async (atualizar = false) => {
      atualizar ? setAtualizando(true) : setCarregando(true);
      const { data } = await api.GET("/api/v1/proposals/{proposta_id}/amendments", {
        params: { path: { proposta_id: proposta.id }, query: { atualizar } },
      });
      if (data) {
        setItens((data.itens ?? []) as Emenda[]);
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

  // Sem emenda e sem incidente: esta proposta simplesmente não é de emenda —
  // não vale ocupar uma seção do detalhe dizendo isso.
  if (!carregando && itens.length === 0 && coleta?.status === "ok") return null;

  return (
    <section className="card p-5">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="label-mono">Emenda parlamentar</h2>
          {coleta?.origem === "registro_fonte" && (
            <span className="text-xs text-ink-3">dados do plano de ação</span>
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
        <div className="flex flex-col gap-1.5">
          <p className="tone-warn text-sm">
            Não consegui consultar a emenda desta proposta na fonte — e o
            registro que temos não traz emenda. Pode ser que esta proposta não
            seja de emenda parlamentar.
          </p>
          {/* O texto cru do connector (rota, parâmetro, exceção) é para quem
              vai calibrar, não para o gestor: fica atrás de um clique em vez
              de ocupar a seção com um parágrafo técnico. */}
          {coleta.erro && (
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
        <p className="text-sm text-ink-3">
          Esta proposta não tem, no cache, um identificador que a fonte aceite para
          consultar a emenda. Ele costuma chegar numa nova coleta.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-hairline">
          {itens.map((e) => (
            <li key={e.id} className="flex flex-wrap items-start justify-between gap-4 py-3">
              <span className="min-w-0">
                {/* o AUTOR lidera: é com ele que o gestor fala */}
                <span className="block text-sm text-ink">{autorCompleto(e)}</span>
                <span className="mt-0.5 block text-xs text-ink-3">
                  {[
                    e.numero_emenda && `emenda ${e.numero_emenda}`,
                    e.ano && `${e.ano}`,
                    humanizarCaixa(e.tipo_emenda),
                    humanizarCaixa(e.cargo_parlamentar),
                    humanizarCaixa(e.funcao),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
              <span className="flex shrink-0 flex-wrap gap-x-5 gap-y-1">
                {num(e.valor) > 0 && (
                  <span className="field">
                    <span className="field-label">Valor</span>
                    <span className="num text-sm text-ink">{formatBRL(e.valor)}</span>
                  </span>
                )}
                {num(e.valor_empenhado) > 0 && (
                  <span className="field">
                    <span className="field-label">Empenhado</span>
                    <span className="num text-sm text-ink">
                      {formatBRL(e.valor_empenhado)}
                    </span>
                  </span>
                )}
                {num(e.valor_pago) > 0 && (
                  <span className="field">
                    <span className="field-label">Pago</span>
                    <span className="num text-sm text-ink">{formatBRL(e.valor_pago)}</span>
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
