"use client";

import {
  type EscopoCriterio,
  padroesDe,
  useCriteriosAlerta,
} from "@/lib/alertas";

/**
 * Multi-select dos CRITÉRIOS de alerta (§53) — "quais alterações eu quero
 * receber". As opções vêm do catálogo da API, então critério novo no backend
 * aparece aqui sem tocar nesta tela.
 *
 * `valor = null` significa "os padrões" (é o estado dos monitoramentos criados
 * antes desta escolha existir): os chips já aparecem marcados nos padrões, e a
 * primeira interação materializa a lista. Desmarcar TUDO é escolha legítima —
 * monitoramento em silêncio —, por isso a tela avisa em vez de "consertar".
 */
export function CriteriosAlerta({
  escopo,
  valor,
  onChange,
  titulo = "Quais alterações avisar",
  descricao,
  compacto = false,
}: {
  escopo: EscopoCriterio;
  valor: string[] | null;
  onChange: (criterios: string[]) => void;
  titulo?: string;
  descricao?: string;
  compacto?: boolean;
}) {
  const { criterios } = useCriteriosAlerta(escopo);
  if (criterios.length === 0) return null;

  const marcados = valor ?? padroesDe(criterios);
  const todos = criterios.map((c) => c.chave);
  const tudoMarcado = todos.every((c) => marcados.includes(c));

  function alternar(chave: string) {
    onChange(
      marcados.includes(chave)
        ? marcados.filter((c) => c !== chave)
        : [...marcados, chave],
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="field-label">{titulo}</span>
        <button
          type="button"
          onClick={() => onChange(tudoMarcado ? [] : todos)}
          className="text-xs text-ink-3 underline underline-offset-2 hover:text-ink-2"
        >
          {tudoMarcado ? "desmarcar todas" : "marcar todas"}
        </button>
      </div>
      {descricao && !compacto && (
        <p className="text-xs text-ink-3">{descricao}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {criterios.map((c) => {
          const ativo = marcados.includes(c.chave);
          return (
            <button
              key={c.chave}
              type="button"
              title={c.descricao}
              aria-pressed={ativo}
              onClick={() => alternar(c.chave)}
              className={`chip ${ativo ? "chip-active" : ""}`}
            >
              {c.rotulo}
            </button>
          );
        })}
      </div>
      {marcados.length === 0 && (
        <p className="text-xs text-warn">
          Nenhuma alteração marcada: o monitoramento fica em silêncio.
        </p>
      )}
    </div>
  );
}

/** Resumo em texto do que está ligado (listas de monitoramentos). */
export function ResumoCriterios({
  escopo,
  valor,
}: {
  escopo: EscopoCriterio;
  valor?: string[] | null;
}) {
  const { criterios, rotulo } = useCriteriosAlerta(escopo);
  if (valor === null || valor === undefined)
    return <span className="text-ink-3">todas as alterações</span>;
  if (valor.length === 0) return <span className="text-warn">sem avisos</span>;
  if (criterios.length > 0 && valor.length === criterios.length)
    return <span className="text-ink-3">todas as alterações</span>;
  return <span className="text-ink-3">{valor.map(rotulo).join(" · ")}</span>;
}
