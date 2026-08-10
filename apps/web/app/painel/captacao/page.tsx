"use client";

import { FileDown, FileSearch, Target } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { SyncMunicipioForm } from "@/components/SyncMunicipioForm";
import { api, baixarPdfProposta } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

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
};

function situacaoTone(situacao?: string | null): BadgeTone {
  const s = (situacao ?? "").toLowerCase();
  if (/(aprovad|celebrad|assinad|empenhad)/.test(s)) return "success";
  if (/(anális|analis|complementa|pendente)/.test(s)) return "warning";
  if (/(rejeitad|cancelad|anulad)/.test(s)) return "danger";
  if (s) return "info";
  return "neutral";
}

export default function CaptacaoPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/propostas", {
      params: { query: {} },
    });
    if (error) {
      setErro("Falha ao carregar propostas.");
      return;
    }
    setPropostas((data as Proposta[]) ?? []);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function consultarAvulsa(ibge: string) {
    setErro(null);
    setOk(null);
    setCarregando(true);
    const { error } = await api.POST("/api/v1/consulta-avulsa", {
      body: { municipio_ibge: ibge, fonte: "transferegov_ff" },
    });
    if (error) {
      setErro(
        "A fonte oficial não respondeu agora (comum: API do TransfereGov instável). Tente novamente.",
      );
    } else {
      setOk("Consulta concluída.");
      await carregar();
    }
    setCarregando(false);
  }

  return (
    <>
      <PageHeader
        icon={Target}
        title="Captação"
        subtitle="Propostas e editais abertos para o seu território."
      />

      <SyncMunicipioForm
        onSync={consultarAvulsa}
        loading={carregando}
        buttonLabel="Buscar na fonte"
      />

      {erro && <Callout tone="error">{erro}</Callout>}
      {ok && <Callout tone="success">{ok}</Callout>}

      {propostas.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title="Nenhuma proposta no cache ainda"
          description="Faça uma consulta avulsa acima para trazer as propostas do seu município direto das fontes oficiais."
        />
      ) : (
        <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50/70 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:bg-gray-950/40">
                  <th className="px-4 py-3">Nº</th>
                  <th className="px-4 py-3">Título</th>
                  <th className="px-4 py-3">Município</th>
                  <th className="px-4 py-3 text-right">Valor</th>
                  <th className="px-4 py-3">Situação</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {propostas.map((p) => (
                  <tr
                    key={p.id}
                    className="transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      {p.id_externo}
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 font-medium">
                      {p.titulo ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                      {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                      {p.uf ? `/${p.uf}` : ""}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">
                      {formatBRL(p.valor_total)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge tone={situacaoTone(p.situacao)}>
                        {p.situacao ?? "—"}
                      </StatusBadge>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => baixarPdfProposta(p.id)}
                        title="Exportar PDF"
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-gray-500 transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-900/30 dark:hover:text-brand-300"
                      >
                        <FileDown className="h-3.5 w-3.5" aria-hidden />
                        PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
