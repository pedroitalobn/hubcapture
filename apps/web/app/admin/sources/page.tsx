"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/Skeleton";
import { api, zerarPropostas } from "@/lib/api/client";

interface UltimaColeta {
  status?: string | null;
  registros?: number | null;
  finalizado_em?: string | null;
  erro?: string | null;
}
interface FonteDiag {
  fonte: string;
  saudavel: boolean;
  ultima_coleta?: UltimaColeta | null;
}
interface Diagnostico {
  fontes: FonteDiag[];
  firecrawl_configurado: boolean;
  crawl4ai_configurado: boolean;
  llm_configurado: boolean;
  emendas_api_key_configurada: boolean;
}

const FONTE_LABEL: Record<string, string> = {
  transferegov_ff: "TransfereGov — Fundo a Fundo",
  transferegov_esp: "TransfereGov — Especiais",
  transferegov_voluntarias: "TransfereGov — Voluntárias",
  transferegov_disc: "TransfereGov — Discricionárias (CSV)",
  fpm: "FPM (Tesouro)",
  emendas: "Emendas (Portal da Transparência)",
  fns: "FNS — Fundo Nacional de Saúde (scraping)",
  fnde: "FNDE — Educação",
  serpro: "SERPRO (painel público)",
  siconfi: "Siconfi / CAUC (Tesouro)",
  sismob: "SISMOB — obras saúde",
  simec: "SIMEC — obras educação",
  caixa: "CAIXA / SIORB — obras infra",
};

function dataBr(iso?: string | null): string {
  if (!iso) return "nunca";
  return iso.slice(0, 16).replace("T", " ");
}

export default function AdminFontesPage() {
  const [diag, setDiag] = useState<Diagnostico | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [zerando, setZerando] = useState(false);
  const [msgLimpeza, setMsgLimpeza] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const { data } = await api.GET("/api/v1/admin/sources", {});
    if (data) setDiag(data as Diagnostico);
    setCarregando(false);
  }, []);

  const zerar = useCallback(async () => {
    if (
      !window.confirm(
        "Zerar TODAS as propostas do sistema?\n\nIsso apaga também favoritos, " +
          "pastas, monitoramentos e alertas ligados a elas. Use só para " +
          "recomeçar a coleta do zero durante a validação. Não dá para desfazer.",
      )
    )
      return;
    setZerando(true);
    setMsgLimpeza(null);
    try {
      const { removidas } = await zerarPropostas();
      setMsgLimpeza(`✓ ${removidas} proposta(s) removida(s). Recarregue a Captação para coletar de novo.`);
    } catch (e) {
      setMsgLimpeza(`Falha: ${e instanceof Error ? e.message : "erro desconhecido"}`);
    } finally {
      setZerando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const providers = diag
    ? [
        {
          nome: "Firecrawl (scraping SaaS)",
          ok: diag.firecrawl_configurado,
          dica: "Chave em Providers & Config → Firecrawl. Ativa FNS/SERPRO.",
        },
        {
          nome: "Crawl4AI (scraping self-hosted)",
          ok: diag.crawl4ai_configurado,
          dica: "URL do servidor Docker em Providers & Config → Crawl4AI.",
        },
        {
          nome: "LLM (resumo/chat IA)",
          ok: diag.llm_configurado,
          dica: "Chave em Providers & Config → LLM.",
        },
        {
          nome: "Portal da Transparência (emendas)",
          ok: diag.emendas_api_key_configurada,
          dica: "chave-api-dados obrigatória — cadastro gratuito no portal.",
        },
      ]
    : [];

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Fontes de dados</h1>
          <p className="mt-1 text-sm text-ink-2">
            Raio-X da ingestão: teste ao vivo de cada fonte oficial + estado dos
            providers. O que estiver vermelho aqui é o que segura os dados do
            painel.
          </p>
        </div>
        <button onClick={carregar} disabled={carregando} className="btn btn-ghost">
          {carregando ? "Testando…" : "Testar novamente"}
        </button>
      </header>

      {/* Zona de manutenção — ferramenta de VALIDAÇÃO (destrutiva) */}
      <section className="card anim-fade-up border border-red-500/30 bg-red-500/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-red-500">Zona de manutenção</h2>
            <p className="mt-0.5 text-xs text-ink-2">
              Zerar todas as propostas para recomeçar a coleta do zero durante a
              validação. Apaga também favoritos, pastas e monitoramentos ligados.
            </p>
          </div>
          <button
            onClick={zerar}
            disabled={zerando}
            className="btn border border-red-500/50 text-red-500 hover:bg-red-500/10"
          >
            {zerando ? "Zerando…" : "Zerar todas as propostas"}
          </button>
        </div>
        {msgLimpeza && (
          <p className="mt-3 text-xs text-ink-2">{msgLimpeza}</p>
        )}
      </section>

      {carregando && !diag ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-64" />
        </div>
      ) : diag ? (
        <>
          <section className="stagger grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {providers.map((p) => (
              <div key={p.nome} className="card flex flex-col gap-2 p-5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm tracking-tight">{p.nome}</span>
                  <StatusBadge tone={p.ok ? "success" : "danger"}>
                    {p.ok ? "configurado" : "faltando"}
                  </StatusBadge>
                </div>
                {!p.ok && <p className="text-xs leading-relaxed text-ink-3">{p.dica}</p>}
              </div>
            ))}
          </section>

          <section className="card anim-fade-up overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-hairline text-left label-mono">
                  <th className="px-5 py-3">Fonte</th>
                  <th className="px-3 py-3">Responde agora?</th>
                  <th className="px-3 py-3">Última coleta</th>
                  <th className="px-3 py-3">Registros</th>
                  <th className="px-3 py-3">Erro</th>
                </tr>
              </thead>
              <tbody>
                {diag.fontes.map((f) => (
                  <tr
                    key={f.fonte}
                    className="border-b border-hairline last:border-0 hover:bg-surface-2"
                  >
                    <td className="px-5 py-3">
                      <span className="block tracking-tight">
                        {FONTE_LABEL[f.fonte] ?? f.fonte}
                      </span>
                      <span className="font-mono text-[11px] text-ink-3">
                        {f.fonte}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge tone={f.saudavel ? "success" : "danger"}>
                        {f.saudavel ? "on-line" : "sem resposta"}
                      </StatusBadge>
                    </td>
                    <td className="px-3 py-3 font-mono text-[12px] text-ink-2">
                      {dataBr(f.ultima_coleta?.finalizado_em)}
                      {f.ultima_coleta?.status && (
                        <span
                          className={
                            f.ultima_coleta.status === "ok"
                              ? " text-ink-3"
                              : " text-red-500"
                          }
                        >
                          {" "}
                          · {f.ultima_coleta.status}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 tabular-nums">
                      {f.ultima_coleta?.registros ?? "—"}
                    </td>
                    <td className="max-w-72 px-3 py-3">
                      <span className="block truncate text-xs text-ink-3" title={f.ultima_coleta?.erro ?? ""}>
                        {f.ultima_coleta?.erro ?? "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : (
        <p className="text-sm text-red-500">Não foi possível carregar o diagnóstico.</p>
      )}
    </>
  );
}
