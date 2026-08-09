"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { StatusBadge } from "@/components/StatusBadge";
import { TextoExpansivel } from "@/components/TextoExpansivel";
import { formatBRL, formatDate, humanizarCaixa } from "@/lib/format";

function num(v?: string | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/**
 * Pareceres do PLANO DE TRABALHO vinculado à proposta.
 *
 * O parecer não é emitido sobre a proposta: é emitido sobre o plano de trabalho
 * dela, e a mesma proposta acumula vários ao longo da análise. Por isso a
 * consulta é pelo número do plano — mostrado no cabeçalho da seção, porque é o
 * que o gestor usa para conferir na fonte.
 *
 * A seção distingue três estados que NÃO podem virar a mesma tela vazia:
 * proposta sem plano de trabalho · fonte não consultável · plano sem parecer.
 */

type Parecer = {
  id: string;
  numero_plano_trabalho: string;
  data_parecer?: string | null;
  esfera?: string | null;
  responsavel?: string | null;
  papel?: string | null;
  cargo?: string | null;
  /** veredito: Aprovar/Reprovar/Solicitar Complementação/Não se aplica */
  situacao?: string | null;
  situacao_analise?: string | null;
  situacao_planejamento?: string | null;
  orgao_analise?: string | null;
  valor_reprovado?: string | null;
  texto?: string | null;
  url_parecer?: string | null;
};

/** Tom do veredito — aprovado é bom, reprovado é ruim, complementação exige ação. */
function tomVeredito(situacao?: string | null): "success" | "warning" | "danger" | "neutral" {
  const s = (situacao ?? "").toLowerCase();
  if (s.includes("aprovar")) return "success";
  if (s.includes("reprovar")) return "danger";
  if (s.includes("complementa")) return "warning";
  return "neutral";
}

type Coleta = {
  numero_plano_trabalho?: string | null;
  status: string;
  total: number;
  erro?: string | null;
};

interface Props {
  proposta: { id: string; numero_plano_trabalho?: string | null };
}

const ESFERA_ROTULO: Record<string, string> = {
  concedente: "Concedente",
  convenente: "Convenente",
};

export function PareceresSecao({ proposta }: Props) {
  const [itens, setItens] = useState<Parecer[]>([]);
  const [coleta, setColeta] = useState<Coleta | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);

  const carregar = useCallback(
    async (atualizar = false) => {
      atualizar ? setAtualizando(true) : setCarregando(true);
      const { data } = await api.GET("/api/v1/proposals/{proposta_id}/opinions", {
        params: { path: { proposta_id: proposta.id }, query: { atualizar } },
      });
      if (data) {
        setItens((data.itens ?? []) as Parecer[]);
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

  const numeroPlano = coleta?.numero_plano_trabalho ?? proposta.numero_plano_trabalho;

  return (
    <section className="card p-5">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="label-mono">Pareceres</h2>
          {numeroPlano && (
            <span className="text-xs text-ink-3">
              plano de trabalho{" "}
              <span className="num select-all text-ink-2">{numeroPlano}</span>
            </span>
          )}
        </div>
        {numeroPlano && (
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
      ) : coleta?.status === "sem_plano_trabalho" ? (
        <p className="text-sm text-ink-3">
          Esta proposta não tem número de plano de trabalho no cache — sem ele não
          há como consultar o parecer na fonte. Ele costuma chegar numa nova coleta.
        </p>
      ) : coleta?.status === "erro" ? (
        <div className="flex flex-col gap-1">
          <p className="tone-warn text-sm">Não consegui consultar os pareceres na fonte.</p>
          <p className="text-xs text-ink-3">
            {coleta.erro ?? "Fonte indisponível."} Um administrador pode calibrar a
            rota em Administração → Configuração → Fontes.
          </p>
        </div>
      ) : itens.length === 0 ? (
        <p className="text-sm text-ink-3">
          Nenhum parecer registrado neste plano de trabalho até agora.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-hairline">
          {itens.map((x) => (
            <li key={x.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
              <span className="min-w-0">
                {/* data + VEREDITO lideram: é o que responde "em que pé está".
                    Quem assinou vem logo abaixo. */}
                <span className="flex flex-wrap items-center gap-2">
                  <span className="num text-sm text-ink">{formatDate(x.data_parecer)}</span>
                  {x.situacao && (
                    <StatusBadge tone={tomVeredito(x.situacao)}>{x.situacao}</StatusBadge>
                  )}
                  {x.situacao_analise && (
                    <span className="text-[11px] text-ink-3">
                      análise {humanizarCaixa(x.situacao_analise).toLowerCase()}
                    </span>
                  )}
                </span>
                <span className="mt-1 block text-sm text-ink-2">
                  {humanizarCaixa(x.responsavel) ||
                    humanizarCaixa(x.orgao_analise) ||
                    "Responsável não informado"}
                </span>
                <span className="block text-xs text-ink-3">
                  {[
                    x.esfera ? (ESFERA_ROTULO[x.esfera] ?? humanizarCaixa(x.esfera)) : "",
                    humanizarCaixa(x.papel),
                    humanizarCaixa(x.cargo),
                    x.responsavel ? humanizarCaixa(x.orgao_analise) : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {num(x.valor_reprovado) > 0 && (
                  <span className="tone-danger mt-1 block text-xs">
                    Valor reprovado {formatBRL(x.valor_reprovado)}
                  </span>
                )}
                {x.texto && (
                  <span className="mt-1.5 block max-w-2xl">
                    <TextoExpansivel texto={x.texto} linhas={3} />
                  </span>
                )}
              </span>
              {x.url_parecer && (
                <a
                  href={x.url_parecer}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-ghost btn-sm shrink-0"
                >
                  Visualizar ↗
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
