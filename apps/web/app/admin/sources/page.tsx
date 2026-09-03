"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/Skeleton";
import Link from "next/link";
import { api, carregarSiconv, restaurarPropostas, zerarPropostas } from "@/lib/api/client";

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
  /** pausa: fonte pausada continua sondável, mas sai das rodadas de coleta */
  ativa?: boolean;
  pausavel?: boolean;
  label?: string | null;
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
  const [carregandoPacote, setCarregandoPacote] = useState(false);
  const [msgPacote, setMsgPacote] = useState<string | null>(null);
  const [salvandoFonte, setSalvandoFonte] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const { data } = await api.GET("/api/v1/admin/sources", {});
    if (data) setDiag(data as Diagnostico);
    setCarregando(false);
  }, []);

  /** Pausa/religa a fonte. A resposta do PUT já é o diagnóstico novo — sem
      recarregar a página, e sem estado local divergindo do servidor. */
  async function alternarFonte(fonte: string, ativa: boolean) {
    setSalvandoFonte(fonte);
    const { data, error } = await api.PUT("/api/v1/admin/sources/state", {
      body: { fonte, ativa },
    });
    if (!error && data) setDiag(data as Diagnostico);
    setSalvandoFonte(null);
  }

  const restaurar = useCallback(async () => {
    setZerando(true);
    setMsgLimpeza(null);
    try {
      const { removidas } = await restaurarPropostas();
      setMsgLimpeza(`✓ ${removidas} proposta(s) restaurada(s) — voltaram ao painel.`);
    } catch (e) {
      setMsgLimpeza(`Falha: ${e instanceof Error ? e.message : "erro desconhecido"}`);
    } finally {
      setZerando(false);
    }
  }, []);

  const zerar = useCallback(async () => {
    if (
      !window.confirm(
        "Zerar TODAS as propostas do sistema?\n\nElas somem do painel de todos " +
          "os usuários e a coleta recomeça do zero. É soft delete: favoritos, " +
          "pastas e monitoramentos ficam intactos e dá para restaurar.",
      )
    )
      return;
    setZerando(true);
    setMsgLimpeza(null);
    try {
      const { removidas } = await zerarPropostas();
      setMsgLimpeza(
        `✓ ${removidas} proposta(s) zerada(s). Recarregue a Captação para coletar de novo — ` +
          "ou restaure, se foi engano.",
      );
    } catch (e) {
      setMsgLimpeza(`Falha: ${e instanceof Error ? e.message : "erro desconhecido"}`);
    } finally {
      setZerando(false);
    }
  }, []);

  // As discricionárias e legais não têm consulta por município: a fonte publica
  // a base inteira em ZIPs nacionais. Este é o gatilho da carga que enche o
  // painel com elas — o mesmo que o worker roda de madrugada.
  const carregarPacote = useCallback(async () => {
    setCarregandoPacote(true);
    setMsgPacote(null);
    try {
      const r = await carregarSiconv();
      setMsgPacote(`✓ ${r.detalhe} — tabelas: ${r.tabelas.join(", ")}`);
    } catch (e) {
      setMsgPacote(`Falha: ${e instanceof Error ? e.message : "erro desconhecido"}`);
    } finally {
      setCarregandoPacote(false);
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

      {/* Pacote SIconv — a única via das discricionárias e legais */}
      <section className="card anim-fade-up p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium">
              Pacote SIconv — discricionárias e legais
            </h2>
            <p className="mt-0.5 max-w-2xl text-xs text-ink-2">
              A fonte não publica consulta por município para este eixo: a base sai
              inteira, um arquivo por tabela. A carga baixa o pacote e grava as
              propostas, emendas e empenhos direto na tabela que a Captação lê.
              Roda em segundo plano (leva minutos).
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={carregarPacote}
              disabled={carregandoPacote}
              className="btn btn-primary"
            >
              {carregandoPacote ? "Solicitando…" : "Carregar pacote agora"}
            </button>
            <Link href="/admin/siconv" className="btn btn-ghost">
              Ver arquivos
            </Link>
          </div>
        </div>
        {msgPacote && <p className="mt-3 text-xs text-ink-2">{msgPacote}</p>}
      </section>

      {/* Zona de manutenção — ferramenta de VALIDAÇÃO (destrutiva) */}
      <section className="card anim-fade-up border border-danger/30 bg-danger/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-danger">Zona de manutenção</h2>
            <p className="mt-0.5 text-xs text-ink-2">
              Zerar todas as propostas para recomeçar a coleta do zero durante a
              validação. É soft delete: elas somem do painel, mas favoritos,
              pastas e monitoramentos ficam — e dá para restaurar.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={zerar}
              disabled={zerando}
              className="btn border border-danger/50 text-danger hover:bg-danger/10"
            >
              {zerando ? "Zerando…" : "Zerar todas as propostas"}
            </button>
            <button onClick={restaurar} disabled={zerando} className="btn btn-ghost">
              Restaurar
            </button>
          </div>
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
            <table className="tbl">
              <thead>
                <tr>
                  <th>Fonte</th>
                  <th>Responde agora?</th>
                  <th>Última coleta</th>
                  <th>Registros</th>
                  <th>Erro</th>
                  <th className="text-right">Coleta</th>
                </tr>
              </thead>
              <tbody>
                {diag.fontes.map((f) => (
                  <tr
                    key={f.fonte}
                    className="border-b border-hairline last:border-0 row-interactive"
                  >
                    <td>
                      <span className="block tracking-tight">
                        {FONTE_LABEL[f.fonte] ?? f.fonte}
                      </span>
                      <span className="font-mono text-[11px] text-ink-3">
                        {f.fonte}
                      </span>
                    </td>
                    <td>
                      <StatusBadge tone={f.saudavel ? "success" : "danger"}>
                        {f.saudavel ? "on-line" : "sem resposta"}
                      </StatusBadge>
                    </td>
                    <td className="font-mono text-[12px] text-ink-2">
                      {dataBr(f.ultima_coleta?.finalizado_em)}
                      {f.ultima_coleta?.status && (
                        <span
                          className={
                            f.ultima_coleta.status === "ok"
                              ? " text-ink-3"
                              : " text-danger"
                          }
                        >
                          {" "}
                          · {f.ultima_coleta.status}
                        </span>
                      )}
                    </td>
                    <td className="tabular-nums">
                      {f.ultima_coleta?.registros ?? "—"}
                    </td>
                    <td className="max-w-72">
                      <span className="block truncate text-xs text-ink-3" title={f.ultima_coleta?.erro ?? ""}>
                        {f.ultima_coleta?.erro ?? "—"}
                      </span>
                    </td>
                                      <td className="text-right">
                      {f.pausavel ? (
                        <button
                          type="button"
                          onClick={() => void alternarFonte(f.fonte, !(f.ativa ?? true))}
                          disabled={salvandoFonte === f.fonte}
                          className={`chip ${f.ativa ?? true ? "chip-active" : ""}`}
                          aria-pressed={f.ativa ?? true}
                          title={
                            f.ativa ?? true
                              ? "Pausar: a fonte sai das rodadas de coleta"
                              : "Religar: a fonte volta às rodadas de coleta"
                          }
                        >
                          {salvandoFonte === f.fonte
                            ? "…"
                            : f.ativa ?? true
                              ? "ativa"
                              : "pausada"}
                        </button>
                      ) : (
                        <span className="text-xs text-ink-3">—</span>
                      )}
                    </td>
</tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : (
        <p className="text-sm text-danger">Não foi possível carregar o diagnóstico.</p>
      )}
    </>
  );
}
