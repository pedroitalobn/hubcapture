"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  MultiSelectChips,
  type MultiChipOption,
} from "@/components/MultiSelectChips";
import { api, baixarPdfProposta } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

export type Proposta = {
  id: string;
  id_externo: string;
  numero_proposta?: string | null;
  titulo?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  natureza_juridica?: string | null;
  fonte: string;
};

type OpcaoFiltro = { valor: string; label: string; total: number };
type Filtros = {
  total: number;
  municipios: OpcaoFiltro[];
  naturezas_juridicas: OpcaoFiltro[];
  fontes: OpcaoFiltro[];
  situacoes: OpcaoFiltro[];
  valor_min?: string | null;
  valor_max?: string | null;
};

/**
 * Rótulos das naturezas jurídicas para exibição fora da busca (a fonte de
 * verdade é `models/proposta.NATUREZAS_JURIDICAS` na API — aqui só se traduz o
 * slug que já veio na proposta; slug desconhecido cai no próprio slug).
 */
export const NATUREZA_LABEL: Record<string, string> = {
  administracao_publica_municipal: "Administração pública municipal",
  administracao_publica_estadual: "Administração pública estadual/distrital",
  administracao_publica_federal: "Administração pública federal",
  consorcio_publico: "Consórcio público",
  organizacao_sociedade_civil: "Organização da sociedade civil",
  empresa_publica: "Empresa pública / sociedade de economia mista",
  outros: "Outros",
};

const VAZIO: Filtros = {
  total: 0,
  municipios: [],
  naturezas_juridicas: [],
  fontes: [],
  situacoes: [],
};

/** Opção da API (valor/label/total) → chip do design system (value/count). */
function paraChips(opcoes: OpcaoFiltro[]): MultiChipOption[] {
  return opcoes.map((o) => ({ value: o.valor, label: o.label, count: o.total }));
}

/** Só envia o valor se for um número válido (campo em branco = sem corte). */
function numeroOuNulo(v: string): string | undefined {
  const limpo = v.replace(/\./g, "").replace(",", ".").trim();
  if (limpo === "") return undefined;
  const n = Number(limpo);
  return Number.isFinite(n) && n >= 0 ? String(n) : undefined;
}

/**
 * Busca de propostas do painel: número, município, natureza jurídica e faixa de
 * valor. Roda toda sobre o cache (RLS) — nunca chama fonte de governo; o fetch
 * ao vivo é a consulta avulsa, na lente de Captação.
 *
 * `recarregarEm` é um contador: mudou → refaz a busca (ex.: depois de um sync).
 */
export function BuscaPropostas({
  recarregarEm = 0,
}: {
  recarregarEm?: number;
}) {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [filtros, setFiltros] = useState<Filtros>(VAZIO);
  const [erro, setErro] = useState<string | null>(null);

  const [numero, setNumero] = useState("");
  const [municipios, setMunicipios] = useState<string[]>([]);
  const [naturezas, setNaturezas] = useState<string[]>([]);
  const [valorMin, setValorMin] = useState("");
  const [valorMax, setValorMax] = useState("");
  const [buscando, setBuscando] = useState(false);

  // busca por número é debounced: não dispara request a cada tecla
  const [numeroDebounced, setNumeroDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setNumeroDebounced(numero), 300);
    return () => clearTimeout(t);
  }, [numero]);

  // descarta resposta de busca antiga que chegue depois de uma mais nova
  const buscaSeq = useRef(0);

  const carregar = useCallback(async () => {
    const min = numeroOuNulo(valorMin);
    const max = numeroOuNulo(valorMax);
    // range invertido: a API recusaria (400) — mantém o resultado atual e a
    // mensagem de validação abaixo do formulário.
    if (min !== undefined && max !== undefined && Number(min) > Number(max)) return;

    const seq = ++buscaSeq.current;
    setBuscando(true);
    const { data, error } = await api.GET("/api/v1/propostas", {
      params: {
        query: {
          numero: numeroDebounced.trim() || undefined,
          municipio: municipios.length ? municipios : undefined,
          natureza_juridica: naturezas.length ? naturezas : undefined,
          valor_min: min,
          valor_max: max,
        },
      },
    });
    if (seq !== buscaSeq.current) return; // resposta obsoleta
    if (error) {
      setErro("Falha ao carregar propostas.");
    } else {
      setErro(null);
      setPropostas((data as Proposta[]) ?? []);
    }
    setBuscando(false);
  }, [numeroDebounced, municipios, naturezas, valorMin, valorMax]);

  const carregarFiltros = useCallback(async () => {
    const { data } = await api.GET("/api/v1/propostas/filtros");
    if (data) setFiltros(data as Filtros);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar, recarregarEm]);

  useEffect(() => {
    void carregarFiltros();
  }, [carregarFiltros, recarregarEm]);

  const rangeInvalido = useMemo(() => {
    const min = numeroOuNulo(valorMin);
    const max = numeroOuNulo(valorMax);
    return min !== undefined && max !== undefined && Number(min) > Number(max);
  }, [valorMin, valorMax]);

  const temFiltro =
    numero.trim() !== "" ||
    municipios.length > 0 ||
    naturezas.length > 0 ||
    valorMin !== "" ||
    valorMax !== "";

  function limpar() {
    setNumero("");
    setMunicipios([]);
    setNaturezas([]);
    setValorMin("");
    setValorMax("");
  }

  const naturezaLabel = useMemo(
    () => ({
      ...NATUREZA_LABEL,
      ...Object.fromEntries(filtros.naturezas_juridicas.map((n) => [n.valor, n.label])),
    }),
    [filtros.naturezas_juridicas],
  );

  return (
    <>
      <section className="flex flex-col gap-4 rounded-lg border border-gray-200 p-4 dark:border-gray-800">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
            Número da proposta
            <input
              value={numero}
              onChange={(e) => setNumero(e.target.value)}
              placeholder="nº da proposta, nº interno ou emenda"
              className="rounded-md border border-gray-300 px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Valor mínimo (R$)
            <input
              inputMode="decimal"
              value={valorMin}
              onChange={(e) => setValorMin(e.target.value)}
              placeholder={filtros.valor_min ?? "0"}
              className="w-40 rounded-md border border-gray-300 px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Valor máximo (R$)
            <input
              inputMode="decimal"
              value={valorMax}
              onChange={(e) => setValorMax(e.target.value)}
              placeholder={filtros.valor_max ?? "sem limite"}
              className="w-40 rounded-md border border-gray-300 px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
            />
          </label>
          {temFiltro && (
            <button
              type="button"
              onClick={limpar}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-700"
            >
              Limpar filtros
            </button>
          )}
        </div>

        {rangeInvalido && (
          <p className="text-sm text-red-600">
            O valor mínimo está maior que o máximo.
          </p>
        )}

        {filtros.municipios.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              Município
            </p>
            <MultiSelectChips
              options={paraChips(filtros.municipios)}
              selected={municipios}
              onChange={setMunicipios}
            />
          </div>
        )}

        {filtros.naturezas_juridicas.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              Natureza jurídica
            </p>
            <MultiSelectChips
              options={paraChips(filtros.naturezas_juridicas)}
              selected={naturezas}
              onChange={setNaturezas}
            />
          </div>
        )}
      </section>

      {erro && <p className="text-sm text-red-600">{erro}</p>}

      <section className="overflow-x-auto">
        <p className="mb-2 text-sm text-gray-500">
          {buscando
            ? "Buscando…"
            : `${propostas.length} de ${filtros.total} proposta${
                filtros.total === 1 ? "" : "s"
              }`}
        </p>

        {propostas.length === 0 ? (
          <p className="text-gray-500">
            {temFiltro
              ? "Nenhuma proposta com esses filtros. Ajuste a busca ou limpe os filtros."
              : "Nenhuma proposta no cache ainda. Faça uma consulta avulsa em Captação."}
          </p>
        ) : (
          <PropostasTable propostas={propostas} naturezaLabel={naturezaLabel} />
        )}
      </section>
    </>
  );
}

/** Tabela de propostas — compartilhada entre a busca e a lente de Captação. */
export function PropostasTable({
  propostas,
  naturezaLabel = NATUREZA_LABEL,
}: {
  propostas: Proposta[];
  naturezaLabel?: Record<string, string>;
}) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-gray-200 text-left dark:border-gray-800">
          <th className="py-2 pr-4">Nº</th>
          <th className="py-2 pr-4">Título</th>
          <th className="py-2 pr-4">Município</th>
          <th className="py-2 pr-4">Natureza jurídica</th>
          <th className="py-2 pr-4">Valor</th>
          <th className="py-2 pr-4">Situação</th>
          <th className="py-2 pr-4"></th>
        </tr>
      </thead>
      <tbody>
        {propostas.map((p) => (
          <tr key={p.id} className="border-b border-gray-100 dark:border-gray-900">
            <td className="py-2 pr-4 font-mono text-xs">
              {p.numero_proposta ?? p.id_externo}
            </td>
            <td className="py-2 pr-4">{p.titulo ?? "—"}</td>
            <td className="py-2 pr-4">
              {p.municipio_nome ?? p.municipio_ibge ?? "—"}
              {p.uf ? `/${p.uf}` : ""}
            </td>
            <td className="py-2 pr-4">
              {p.natureza_juridica
                ? naturezaLabel[p.natureza_juridica] ?? p.natureza_juridica
                : "—"}
            </td>
            <td className="py-2 pr-4">{formatBRL(p.valor_total)}</td>
            <td className="py-2 pr-4">{p.situacao ?? "—"}</td>
            <td className="py-2 pr-4">
              <button
                onClick={() => baixarPdfProposta(p.id)}
                className="text-xs text-brand underline"
              >
                PDF
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
