"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { FilterChips } from "@/components/FilterChips";
import { api, baixarPdfProposta } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

type Natureza = "entes_municipais" | "outros";

const NATUREZA_LABEL: Record<Natureza, string> = {
  entes_municipais: "Entes municipais",
  outros: "Outros",
};
const NATUREZAS: Natureza[] = ["entes_municipais", "outros"];

/** Só aceita as duas lentes conhecidas (o resto vira "todas"). */
function parseNatureza(valor: string | null): Natureza | null {
  return NATUREZAS.includes(valor as Natureza) ? (valor as Natureza) : null;
}

type Proposta = {
  id: string;
  id_externo: string;
  titulo?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  fonte: string;
  natureza_juridica?: string | null;
  natureza_juridica_descricao?: string | null;
};

function CaptacaoConteudo() {
  const router = useRouter();
  const params = useSearchParams();
  // a natureza vive na URL: o card do painel já chega filtrado e o link é compartilhável
  const natureza = parseNatureza(params.get("natureza"));

  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/propostas", {
      params: { query: natureza ? { natureza_juridica: natureza } : {} },
    });
    if (error) {
      setMsg("Falha ao carregar propostas.");
      return;
    }
    setPropostas((data as Proposta[]) ?? []);
  }, [natureza]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  function selecionarNatureza(valor: string | null) {
    const qs = new URLSearchParams(params.toString());
    if (valor) qs.set("natureza", valor);
    else qs.delete("natureza");
    const query = qs.toString();
    router.replace(query ? `/painel/captacao?${query}` : "/painel/captacao");
  }

  // contadores das lentes: sempre sobre o total carregado quando não há filtro
  const contagem = useMemo(() => {
    if (natureza) return undefined;
    return propostas.reduce<Record<string, number>>((acc, p) => {
      const chave = (p.natureza_juridica as Natureza) ?? "outros";
      acc[chave] = (acc[chave] ?? 0) + 1;
      return acc;
    }, {});
  }, [propostas, natureza]);

  async function consultarAvulsa(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setCarregando(true);
    const { error } = await api.POST("/api/v1/consulta-avulsa", {
      body: { municipio_ibge: ibge, fonte: "transferegov_ff" },
    });
    if (error) {
      setMsg(
        "A fonte oficial não respondeu agora (comum: API do TransfereGov instável). Tente novamente.",
      );
    } else {
      setMsg("Consulta concluída.");
      await carregar();
    }
    setCarregando(false);
  }

  return (
    <>
      <header>
        <h1 className="text-2xl font-bold">Captação</h1>
        <p className="text-sm text-gray-500">
          Propostas e editais abertos para o seu território.
        </p>
      </header>

      <section className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Natureza jurídica do proponente
        </p>
        <FilterChips
          options={NATUREZAS.map((n) => ({
            value: n,
            label: NATUREZA_LABEL[n],
            count: contagem?.[n],
          }))}
          selected={natureza}
          onSelect={selecionarNatureza}
        />
        <p className="text-xs text-gray-500">
          Entes municipais: prefeitura, secretaria, câmara, fundo ou autarquia do
          município. Outros: organizações da sociedade civil, entes estaduais e
          federais, empresas.
        </p>
      </section>

      <form onSubmit={consultarAvulsa} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Consulta avulsa (IBGE, 7 dígitos)
          <input
            value={ibge}
            onChange={(e) => setIbge(e.target.value)}
            placeholder="3550308"
            maxLength={7}
            className="rounded-md border border-gray-300 px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
          />
        </label>
        <button
          type="submit"
          disabled={carregando || ibge.length !== 7}
          className="rounded-md bg-brand px-4 py-2 text-brand-fg disabled:opacity-60"
        >
          {carregando ? "Consultando…" : "Buscar na fonte"}
        </button>
      </form>

      {msg && <p className="text-sm text-gray-600 dark:text-gray-400">{msg}</p>}

      <section className="overflow-x-auto">
        {propostas.length === 0 ? (
          <p className="text-gray-500">
            {natureza
              ? `Nenhuma proposta de ${NATUREZA_LABEL[natureza].toLowerCase()} no seu território.`
              : "Nenhuma proposta no cache ainda. Faça uma consulta avulsa acima."}
          </p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left dark:border-gray-800">
                <th className="py-2 pr-4">Nº</th>
                <th className="py-2 pr-4">Título</th>
                <th className="py-2 pr-4">Município</th>
                <th className="py-2 pr-4">Natureza</th>
                <th className="py-2 pr-4">Valor</th>
                <th className="py-2 pr-4">Situação</th>
                <th className="py-2 pr-4"></th>
              </tr>
            </thead>
            <tbody>
              {propostas.map((p) => (
                <tr
                  key={p.id}
                  className="border-b border-gray-100 dark:border-gray-900"
                >
                  <td className="py-2 pr-4 font-mono text-xs">{p.id_externo}</td>
                  <td className="py-2 pr-4">{p.titulo ?? "—"}</td>
                  <td className="py-2 pr-4">
                    {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                    {p.uf ? `/${p.uf}` : ""}
                  </td>
                  <td className="py-2 pr-4">
                    {NATUREZA_LABEL[(p.natureza_juridica as Natureza) ?? "outros"]}
                    {p.natureza_juridica_descricao && (
                      <span className="block text-xs text-gray-500">
                        {p.natureza_juridica_descricao}
                      </span>
                    )}
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
        )}
      </section>
    </>
  );
}

export default function CaptacaoPage() {
  // useSearchParams exige boundary de Suspense na build do Next 15
  return (
    <Suspense fallback={<p className="text-sm text-gray-500">Carregando…</p>}>
      <CaptacaoConteudo />
    </Suspense>
  );
}
