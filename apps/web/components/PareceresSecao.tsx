"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { formatDate, humanizarCaixa } from "@/lib/format";
import { cx } from "@/components/ui";

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
  situacao?: string | null;
  url_parecer?: string | null;
};

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
                {/* data e quem assinou lideram — é o que responde "em que pé está" */}
                <span className="flex flex-wrap items-baseline gap-2">
                  <span className="num text-sm text-ink">{formatDate(x.data_parecer)}</span>
                  {x.esfera && (
                    <span
                      className={cx(
                        "rounded-full border border-hairline px-2 py-0.5 text-[11px]",
                        "text-ink-2",
                      )}
                    >
                      {ESFERA_ROTULO[x.esfera] ?? humanizarCaixa(x.esfera)}
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-sm text-ink-2">
                  {humanizarCaixa(x.responsavel) || "Responsável não informado"}
                </span>
                <span className="block text-xs text-ink-3">
                  {[humanizarCaixa(x.papel), humanizarCaixa(x.cargo)]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {x.situacao && (
                  <span className="block text-xs text-ink-3">
                    {humanizarCaixa(x.situacao)}
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
