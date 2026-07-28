"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { SkeletonCards } from "@/components/Skeleton";
import { api } from "@/lib/api/client";

interface Dimensao {
  chave: string;
  titulo: string;
  total: number;
  destaque?: string | null;
  href: string;
}
interface Municipio {
  ibge: string;
  nome?: string | null;
  uf?: string | null;
}
interface VisaoGeral {
  papel?: string | null;
  municipios: Municipio[];
  areas: string[];
  dimensoes: Dimensao[];
}
interface Novidade {
  tipo: string;
  titulo: string;
  descricao?: string | null;
  valor?: number | string | null;
  data?: string | null;
  fonte: string;
  municipio_nome?: string | null;
  href: string;
}
interface SyncRunStatus {
  fonte?: string | null;
  status?: string | null;
  registros?: number | null;
  finalizado_em?: string | null;
}
interface Novidades {
  itens: Novidade[];
  sync_runs: SyncRunStatus[];
}

const FONTE_LABEL: Record<string, string> = {
  transferegov_ff: "TransfereGov FF",
  transferegov_esp: "TransfereGov Especiais",
  transferegov_voluntarias: "TransfereGov Voluntárias",
  fpm: "FPM",
  emendas: "Emendas",
  fns: "FNS",
  fnde: "FNDE",
  siconfi: "Siconfi/CAUC",
  sismob: "SISMOB",
  simec: "SIMEC",
  caixa: "CAIXA",
};

function brl(v: number | string | null | undefined): string | null {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (n == null || Number.isNaN(n)) return null;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function dataBr(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

function MeuPainel() {
  const searchParams = useSearchParams();
  const sincronizando = searchParams.get("sync") === "1";

  const [data, setData] = useState<VisaoGeral | null>(null);
  const [novidades, setNovidades] = useState<Novidades | null>(null);
  const [loading, setLoading] = useState(true);
  const tentativas = useRef(0);

  async function carregar() {
    const [{ data: vg }, { data: nov }] = await Promise.all([
      api.GET("/api/v1/perfil/visao-geral"),
      api.GET("/api/v1/perfil/novidades"),
    ]);
    if (vg) setData(vg as VisaoGeral);
    if (nov) setNovidades(nov as Novidades);
    setLoading(false);
    return (nov as Novidades | undefined)?.itens.length ?? 0;
  }

  useEffect(() => {
    void carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recém-saído do onboarding: o 1º sync real roda em background na API —
  // re-consulta o feed a cada 8s (até ~2min) enquanto os dados chegam.
  useEffect(() => {
    if (!sincronizando) return;
    const timer = setInterval(async () => {
      tentativas.current += 1;
      const n = await carregar();
      if (n > 0 || tentativas.current >= 15) clearInterval(timer);
    }, 8000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sincronizando]);

  const semTerritorio = !loading && (data?.municipios.length ?? 0) === 0;
  const itens = novidades?.itens ?? [];
  const falhas = (novidades?.sync_runs ?? []).filter((r) => r.status === "erro");
  const aguardandoDados =
    sincronizando && itens.length === 0 && tentativas.current < 15;

  return (
    <>
      <header>
        <h1 className="page-title">Meu painel</h1>
        <p className="mt-1 text-sm text-ink-2">
          Tudo do seu território, por etapa do ciclo do recurso público.
        </p>
      </header>

      {loading ? (
        <SkeletonCards />
      ) : semTerritorio ? (
        <div className="card p-8 text-sm">
          <p className="mb-2 text-base tracking-tight">
            Você ainda não acompanha nenhum município.
          </p>
          <p className="mb-5 max-w-md leading-relaxed text-ink-2">
            O Hub Capture se organiza a partir do seu perfil — converse com o
            Copiloto para escolher municípios, áreas e fontes.
          </p>
          <Link href="/onboarding" className="btn btn-primary">
            Configurar meu perfil
          </Link>
        </div>
      ) : (
        <>
          <section className="stagger grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {(data?.dimensoes ?? []).map((d) => (
              <Link
                key={d.chave}
                href={d.href}
                className="card card-hover group flex flex-col justify-between p-6 min-h-44"
              >
                <div className="flex items-start justify-between">
                  <h2 className="tracking-tight">{d.titulo}</h2>
                  <span className="flex h-9 w-9 translate-y-1 items-center justify-center rounded-lg bg-lime text-abyss opacity-0 transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100">
                    →
                  </span>
                </div>
                <div>
                  <div
                    className={`text-[44px] font-medium leading-none tracking-[-0.03em] tabular-nums ${
                      d.total > 0 ? "text-gradient" : ""
                    }`}
                  >
                    {d.total}
                  </div>
                  <p className="mt-2 text-sm text-ink-2">{d.destaque ?? "—"}</p>
                </div>
              </Link>
            ))}
          </section>

          <section className="anim-fade-up flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="tracking-tight">Últimas novidades no seu território</h2>
              {aguardandoDados && (
                <span className="label-mono animate-pulse">
                  Sincronizando fontes…
                </span>
              )}
            </div>

            {itens.length === 0 ? (
              <div className="card p-6 text-sm text-ink-2">
                {aguardandoDados ? (
                  <p>
                    Estamos consultando as fontes oficiais do seu perfil agora —
                    as primeiras verbas e propostas aparecem aqui em instantes.
                  </p>
                ) : falhas.length > 0 ? (
                  <p>
                    Ainda sem dados no cache: {falhas.length}{" "}
                    {falhas.length === 1 ? "fonte falhou" : "fontes falharam"} na
                    última coleta (
                    {falhas
                      .map((f) => FONTE_LABEL[f.fonte ?? ""] ?? f.fonte)
                      .join(", ")}
                    ). Novas tentativas rodam no próximo ciclo; você também pode
                    disparar uma busca nas páginas de cada dimensão.
                  </p>
                ) : (
                  <p>
                    Nenhuma novidade ainda — os dados chegam após a primeira
                    coleta das fontes do seu perfil.
                  </p>
                )}
              </div>
            ) : (
              <ol className="card stagger divide-y divide-hairline p-0">
                {itens.map((n, i) => (
                  <li key={i}>
                    <Link
                      href={n.href}
                      className="flex flex-col gap-1 px-5 py-4 transition-colors hover:bg-surface-2 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm text-ink">{n.titulo}</p>
                        <p className="mt-0.5 flex flex-wrap gap-x-2 text-[12px] text-ink-3">
                          <span className="font-mono uppercase tracking-[0.04em]">
                            {n.tipo === "captacao" ? "Captação" : "Recebido"}
                          </span>
                          <span>{FONTE_LABEL[n.fonte] ?? n.fonte}</span>
                          {n.municipio_nome && <span>{n.municipio_nome}</span>}
                          {n.descricao && (
                            <span className="truncate">{n.descricao}</span>
                          )}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3 text-sm">
                        {brl(n.valor) && (
                          <span className="tabular-nums">{brl(n.valor)}</span>
                        )}
                        {dataBr(n.data) && (
                          <span className="font-mono text-[12px] text-ink-3">
                            {dataBr(n.data)}
                          </span>
                        )}
                      </div>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </>
  );
}

export default function MeuPainelPage() {
  return (
    <Suspense fallback={<SkeletonCards />}>
      <MeuPainel />
    </Suspense>
  );
}
