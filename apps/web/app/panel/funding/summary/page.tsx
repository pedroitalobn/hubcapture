"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api/client";
import { formatBRL, formatDate } from "@/lib/format";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";

type Opcao = { valor: string; rotulo: string; total: number };
type Facetas = Record<string, Opcao[]>;

interface ResumoCaptacao {
  cards: {
    valor_conveniado: string;
    valor_desembolsado: string;
    valor_empenhado: string;
    valor_a_utilizar: string;
    transferencias: number;
    convenios_iniciados: number;
    convenios_em_execucao: number;
    oportunidades_abertas: number;
  };
  por_ano: { ano: string; aprovado: string; desembolsado: string }[];
  pipeline: { situacao: string; quantidade: number; valor: string }[];
  convenios_vigentes: {
    id: string;
    titulo?: string | null;
    orgao_superior?: string | null;
    modalidade?: string | null;
    valor_global: string;
    desembolsado: string;
    percentual_desembolso: number;
    fim_vigencia?: string | null;
    dias_restantes?: number | null;
  }[];
}

type Filtros = {
  natureza_juridica: string;
  modalidade: string;
  orgao: string;
  qualificacao: string;
};

const VAZIO: Filtros = {
  natureza_juridica: "",
  modalidade: "",
  orgao: "",
  qualificacao: "",
};

const NATUREZAS: [string, string][] = [
  ["", "Todas"],
  ["estadual_df", "Estadual/DF"],
  ["municipal", "Municipal"],
  ["consorcio", "Consórcio"],
  ["empresa_publica", "Empresa pública"],
  ["osc", "OSC"],
];

function num(v?: string | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

export default function ResumoCaptacaoPage() {
  const { selecionados } = useTerritorio();
  const [resumo, setResumo] = useState<ResumoCaptacao | null>(null);
  const [facetas, setFacetas] = useState<Facetas>({});
  const [filtros, setFiltros] = useState<Filtros>(VAZIO);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const query = {
      ...Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== "")),
      municipio: paramMunicipio(selecionados), // recorte de território do painel
    };
    const [r, f] = await Promise.all([
      api.GET("/api/v1/proposals/summary", { params: { query } as never }),
      api.GET("/api/v1/proposals/facets", { params: { query } as never }),
    ]);
    if (r.data) setResumo(r.data as ResumoCaptacao);
    if (f.data) setFacetas(f.data as Facetas);
    setCarregando(false);
  }, [filtros, selecionados]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // escala das barras do gráfico aprovado × desembolsado
  const maxAno = useMemo(() => {
    const valores = (resumo?.por_ano ?? []).flatMap((a) => [
      num(a.aprovado),
      num(a.desembolsado),
    ]);
    return Math.max(1, ...valores);
  }, [resumo]);

  const maxPipeline = useMemo(
    () => Math.max(1, ...(resumo?.pipeline ?? []).map((p) => p.quantidade)),
    [resumo],
  );

  function select(chave: keyof Filtros, rotulo: string, dim: string, largura: string) {
    const opcoes = facetas[dim] ?? [];
    return (
      <label className="flex flex-col gap-1">
        <span className="field-label">{rotulo}</span>
        <select
          value={filtros[chave]}
          onChange={(e) => setFiltros({ ...filtros, [chave]: e.target.value })}
          className={`input ${largura}`}
        >
          <option value="">todas</option>
          {opcoes.map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.rotulo} ({o.total})
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Resumo da captação</h1>
          <p className="mt-1 text-sm text-ink-2">
            Consolidado do que o seu território já conveniou, o que foi
            desembolsado e o que ainda está aberto.
          </p>
        </div>
        <Link href="/panel/funding" className="btn btn-ghost btn-sm">
          ← Voltar à captação
        </Link>
      </header>

      <div className="card flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="field-label mr-1">Natureza jurídica</span>
          {NATUREZAS.map(([valor, rotulo]) => (
            <button
              key={rotulo}
              onClick={() => setFiltros({ ...filtros, natureza_juridica: valor })}
              className={`rounded-full border px-3 py-1 text-sm ${
                filtros.natureza_juridica === valor
                  ? "border-ink bg-ink text-surface"
                  : "border-hairline text-ink-2 hover:text-ink"
              }`}
            >
              {rotulo}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {select("modalidade", "Modalidade", "modalidade", "w-44")}
          {select("orgao", "Órgão", "orgao", "w-56")}
          {select("qualificacao", "Qualificação", "qualificacao", "w-44")}
          <button onClick={() => setFiltros(VAZIO)} className="btn btn-ghost btn-sm mb-1">
            Limpar
          </button>
        </div>
      </div>

      {carregando || !resumo ? (
        <SkeletonCards />
      ) : (
        <>
          <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              label="Valor conveniado"
              value={formatBRL(resumo.cards.valor_conveniado)}
              context={`${resumo.cards.transferencias} transferências`}
            />
            <StatCard
              label="Valor desembolsado"
              value={formatBRL(resumo.cards.valor_desembolsado)}
              context="liberado ao ente"
            />
            <StatCard
              label="Convênios iniciados"
              value={String(resumo.cards.convenios_iniciados)}
              context="com assinatura/vigência"
            />
            <StatCard
              label="Convênios em execução"
              value={String(resumo.cards.convenios_em_execucao)}
              context="vigência em aberto"
            />
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            {/* aprovado × desembolsado por ano */}
            <div className="card p-5">
              <h2 className="label-mono">Aprovado × desembolsado por ano</h2>
              {resumo.por_ano.length === 0 ? (
                <p className="mt-3 text-sm text-ink-3">
                  Sem série anual nas fontes consultadas.
                </p>
              ) : (
                <div className="mt-4 flex items-end gap-2 overflow-x-auto">
                  {resumo.por_ano.map((a) => (
                    <div key={a.ano} className="flex min-w-[42px] flex-col items-center gap-1">
                      <div className="flex h-32 items-end gap-0.5">
                        <div
                          title={`Aprovado: ${formatBRL(a.aprovado)}`}
                          className="w-3 rounded-t bg-ink/70"
                          style={{ height: `${(num(a.aprovado) / maxAno) * 100}%` }}
                        />
                        <div
                          title={`Desembolsado: ${formatBRL(a.desembolsado)}`}
                          className="w-3 rounded-t bg-lime"
                          style={{ height: `${(num(a.desembolsado) / maxAno) * 100}%` }}
                        />
                      </div>
                      <span className="font-mono text-[10px] text-ink-3">{a.ano}</span>
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-3 font-mono text-[11px] text-ink-3">
                <span className="mr-3">▊ aprovado</span>
                <span className="text-lime">▊ desembolsado</span>
              </p>
            </div>

            {/* pipeline de propostas por situação */}
            <div className="card p-5">
              <h2 className="label-mono">Pipeline de propostas</h2>
              <p className="mt-1 font-mono text-[11px] text-ink-3">
                {resumo.cards.oportunidades_abertas} oportunidades abertas ·{" "}
                {formatBRL(resumo.cards.valor_a_utilizar)} de empenho
              </p>
              <ul className="mt-4 flex flex-col gap-2">
                {resumo.pipeline.slice(0, 8).map((p) => (
                  <li key={p.situacao} className="flex items-center gap-3 text-sm">
                    <span className="w-40 shrink-0 truncate text-ink-2" title={p.situacao}>
                      {p.situacao}
                    </span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                      <span
                        className="block h-full rounded-full bg-ink/60"
                        style={{ width: `${(p.quantidade / maxPipeline) * 100}%` }}
                      />
                    </span>
                    <span className="w-10 shrink-0 text-right tabular-nums">
                      {p.quantidade}
                    </span>
                  </li>
                ))}
                {resumo.pipeline.length === 0 && (
                  <li className="text-sm text-ink-3">Sem propostas no recorte.</li>
                )}
              </ul>
            </div>
          </section>

          <section className="card overflow-hidden">
            <h2 className="label-mono px-5 pt-5">Convênios vigentes</h2>
            {resumo.convenios_vigentes.length === 0 ? (
              <p className="p-5 text-sm text-ink-3">
                Nenhum convênio com vigência em aberto no recorte atual.
              </p>
            ) : (
              <table className="mt-3 w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-hairline text-left label-mono">
                    <th className="px-5 py-3">Convênio</th>
                    <th className="px-3 py-3">Vigência</th>
                    <th className="px-3 py-3">Valor global</th>
                    <th className="px-3 py-3">Desembolsado</th>
                    <th className="px-3 py-3 w-40">% desembolso</th>
                  </tr>
                </thead>
                <tbody>
                  {resumo.convenios_vigentes.map((c) => (
                    <tr key={c.id} className="border-b border-hairline last:border-0">
                      <td className="px-5 py-3">
                        <Link
                          href={`/panel/funding/${c.id}`}
                          className="font-medium hover:underline"
                        >
                          {c.titulo ?? "—"}
                        </Link>
                        <p className="mt-0.5 text-xs text-ink-3">
                          {[c.orgao_superior, c.modalidade].filter(Boolean).join(" · ")}
                        </p>
                      </td>
                      <td className="px-3 py-3 text-ink-2">
                        {formatDate(c.fim_vigencia)}
                        <span className="ml-1.5 font-mono text-[10px] text-ink-3">
                          {c.dias_restantes}d
                        </span>
                      </td>
                      <td className="px-3 py-3 tabular-nums">{formatBRL(c.valor_global)}</td>
                      <td className="px-3 py-3 tabular-nums">{formatBRL(c.desembolsado)}</td>
                      <td className="px-3 py-3">
                        <span className="flex items-center gap-2">
                          <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                            <span
                              className="block h-full rounded-full bg-lime"
                              style={{
                                width: `${Math.min(100, c.percentual_desembolso)}%`,
                              }}
                            />
                          </span>
                          <span className="w-10 text-right tabular-nums text-xs">
                            {c.percentual_desembolso.toFixed(0)}%
                          </span>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </>
  );
}
