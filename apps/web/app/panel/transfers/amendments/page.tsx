"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { IconeAcao } from "@/components/icons";
import { api, baixarCsv } from "@/lib/api/client";
import { formatBRL, formatBRLCompact, formatDate } from "@/lib/format";
import { paramFonte, useOrigem } from "@/lib/origem";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";
import { SeletorSimples } from "@/components/kit";

interface EmendaItem {
  id: string;
  codigo: string;
  numero?: string | null;
  parlamentar?: string | null;
  partido?: string | null;
  modalidade?: string | null;
  area?: string | null;
  orgao_superior?: string | null;
  ano?: string | null;
  empenhado: string;
  pago: string;
  percentual_executado: number;
  data_repasse?: string | null;
  descricao?: string | null;
}

interface ResumoEmendas {
  empenhado: string;
  pago: string;
  percentual_executado: number;
  emendas: number;
  por_ano: { ano: string; empenhado: string; pago: string }[];
  por_modalidade: { chave: string; valor: string; quantidade: number }[];
  por_area: { chave: string; valor: string; quantidade: number }[];
  ranking_parlamentares: {
    parlamentar: string;
    partido?: string | null;
    empenhado: string;
    pago: string;
    emendas: number;
  }[];
  itens: EmendaItem[];
  opcoes: {
    anos: string[];
    modalidades: string[];
    parlamentares: string[];
    orgaos: string[];
  };
}

type Filtros = {
  modalidade: string;
  ano: string;
  parlamentar: string;
  orgao: string;
  q: string;
};

const VAZIO: Filtros = { modalidade: "", ano: "", parlamentar: "", orgao: "", q: "" };

function num(v?: string | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

export default function EmendasPage() {
  const { selecionados } = useTerritorio();
  // origem do recurso: recorte global do trilho, como o território
  const { selecionadas: origens } = useOrigem();
  const [resumo, setResumo] = useState<ResumoEmendas | null>(null);
  const [filtros, setFiltros] = useState<Filtros>(VAZIO);
  const [carregando, setCarregando] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  // os recortes globais do painel (território e origem do recurso) entram
  // junto dos filtros da tela
  const query = useMemo(
    () => ({
      ...Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== "")),
      municipio: paramMunicipio(selecionados),
      fonte: paramFonte(origens),
    }),
    [filtros, selecionados, origens],
  );

  const carregar = useCallback(async () => {
    setCarregando(true);
    const { data, error } = await api.GET("/api/v1/transfers/amendments/summary", {
      params: { query } as never,
    });
    if (error) setMsg("Falha ao carregar as emendas.");
    else if (data) {
      setResumo(data as ResumoEmendas);
      setMsg(null);
    }
    setCarregando(false);
  }, [query]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function exportar() {
    try {
      await baixarCsv(
        "/api/v1/transfers/amendments/report.csv",
        { ...filtros, municipio: selecionados, fonte: origens },
        "emendas.csv",
      );
    } catch {
      setMsg("Não consegui gerar o relatório agora.");
    }
  }

  const maxAno = useMemo(
    () =>
      Math.max(
        1,
        ...(resumo?.por_ano ?? []).flatMap((a) => [num(a.empenhado), num(a.pago)]),
      ),
    [resumo],
  );

  const ativos = Object.entries(filtros).filter(([, v]) => v !== "");

  /** Filtro de uma dimensão, no seletor do kit (mesma forma da barra de
   *  recorte do painel). As opções vêm do universo do território — escolher um
   *  parlamentar não esvazia a lista dos demais. */
  function select(chave: keyof Filtros, rotulo: string, opcoes: string[], largura: string) {
    return (
      <SeletorSimples
        rotulo={rotulo}
        valor={filtros[chave]}
        opcoes={opcoes.map((o) => ({ valor: o, rotulo: o }))}
        largura={largura}
        aoMudar={(v) => setFiltros({ ...filtros, [chave]: v })}
      />
    );
  }

  return (
    <>
      <PageHeader
        voltar={{ href: "/panel/transfers", rotulo: "Recursos recebidos" }}
        titulo="Emendas parlamentares"
        descricao="O que os parlamentares destinaram ao seu território — empenhado, pago e a execução por modalidade, área e autor."
      />

      <div className="card flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[14rem] flex-1 flex-col gap-1">
            <span className="field-label">Buscar</span>
            <input
              value={filtros.q}
              onChange={(e) => setFiltros({ ...filtros, q: e.target.value })}
              placeholder="objeto, área, órgão ou código"
              className="input w-full"
            />
          </label>
          {select("modalidade", "Modalidade", resumo?.opcoes.modalidades ?? [], "16rem")}
          {select("ano", "Ano", resumo?.opcoes.anos ?? [], "13rem")}
          {select("parlamentar", "Parlamentar", resumo?.opcoes.parlamentares ?? [], "20rem")}
          {select("orgao", "Órgão", resumo?.opcoes.orgaos ?? [], "20rem")}
          <button onClick={() => void exportar()} className="btn btn-ghost btn-sm mb-1">
            <IconeAcao nome="exportar" />
            Exportar
          </button>
        </div>
        {ativos.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline pt-3">
            <span className="field-label mr-1">Filtros ativos</span>
            {ativos.map(([chave, valor]) => (
              <button
                key={chave}
                onClick={() => setFiltros({ ...filtros, [chave]: "" })}
                className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink-2 hover:text-ink"
              >
                {valor}
                <span className="text-ink-3">×</span>
              </button>
            ))}
            <button onClick={() => setFiltros(VAZIO)} className="btn btn-ghost btn-sm">
              Limpar tudo
            </button>
          </div>
        )}
      </div>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      {carregando || !resumo ? (
        <SkeletonCards />
      ) : resumo.emendas === 0 ? (
        <p className="text-ink-3">
          Nenhuma emenda encontrada para o território com esses filtros. Sincronize
          os recebidos em{" "}
          <Link href="/panel/transfers" className="underline">
            Recursos recebidos
          </Link>{" "}
          para buscar nas fontes oficiais.
        </p>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {/* BRL compacto no KPI: por extenso não cabe no card estreito e o
                .card corta o que estoura; o valor cheio fica no tooltip */}
            <StatCard
              label="Empenhado"
              value={formatBRLCompact(resumo.empenhado)}
              title={formatBRL(resumo.empenhado)}
              context={`${resumo.emendas} emendas`}
            />
            <StatCard
              label="Pago"
              value={formatBRLCompact(resumo.pago)}
              title={formatBRL(resumo.pago)}
              context={`${resumo.percentual_executado.toFixed(0)}% executado`}
            />
            <StatCard
              label="Parlamentares"
              value={String(resumo.ranking_parlamentares.length)}
              context="destinaram recursos"
            />
            <StatCard
              label="Áreas atendidas"
              value={String(resumo.por_area.length)}
              context="por função orçamentária"
            />
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="card p-5">
              <h2 className="label-mono">Evolução anual (pago × empenhado)</h2>
              <div className="mt-4 flex items-end gap-2 overflow-x-auto">
                {resumo.por_ano.map((a) => (
                  <div key={a.ano} className="flex min-w-[42px] flex-col items-center gap-1">
                    <div className="flex h-32 items-end gap-0.5">
                      <div
                        title={`Empenhado: ${formatBRL(a.empenhado)}`}
                        className="w-3 rounded-t bg-ink/70"
                        style={{ height: `${(num(a.empenhado) / maxAno) * 100}%` }}
                      />
                      <div
                        title={`Pago: ${formatBRL(a.pago)}`}
                        className="w-3 rounded-t bg-lime"
                        style={{ height: `${(num(a.pago) / maxAno) * 100}%` }}
                      />
                    </div>
                    <span className="font-mono text-[10px] text-ink-3">{a.ano}</span>
                  </div>
                ))}
              </div>
              <p className="mt-3 font-mono text-[11px] text-ink-3">
                <span className="mr-3">▊ empenhado</span>
                <span>
                  <span className="text-accent">▊</span> pago
                </span>
              </p>
            </div>

            <div className="card p-5">
              <h2 className="label-mono">Ranking de parlamentares</h2>
              <ul className="mt-4 flex flex-col gap-2">
                {resumo.ranking_parlamentares.slice(0, 8).map((p) => (
                  <li key={p.parlamentar} className="flex items-center gap-3 text-sm">
                    <span className="w-44 shrink-0 truncate" title={p.parlamentar}>
                      {p.parlamentar}
                      {p.partido && (
                        <span className="ml-1 text-xs text-ink-3">({p.partido})</span>
                      )}
                    </span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                      <span
                        className="block h-full rounded-full bg-ink/60"
                        style={{
                          width: `${
                            (num(p.pago) /
                              Math.max(
                                1,
                                ...resumo.ranking_parlamentares.map((x) => num(x.pago)),
                              )) *
                            100
                          }%`,
                        }}
                      />
                    </span>
                    <span className="shrink-0 text-right tabular-nums text-xs">
                      {formatBRL(p.pago)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <Distribuicao titulo="Distribuição por modalidade" itens={resumo.por_modalidade} />
            <Distribuicao titulo="Distribuição por área" itens={resumo.por_area} />
          </section>

          <section className="card overflow-x-auto">
            <h2 className="label-mono px-5 pt-5">Emendas que beneficiaram o município</h2>
            <table className="mt-3 tbl">
              <thead>
                <tr>
                  <th>Parlamentar</th>
                  <th>Código / ano</th>
                  <th>Modalidade</th>
                  <th>Área</th>
                  <th>Empenhado</th>
                  <th>Pago</th>
                  <th>% exec.</th>
                  <th>Última mov.</th>
                </tr>
              </thead>
              <tbody>
                {resumo.itens.map((e) => (
                  <tr key={e.id} className="border-b border-hairline last:border-0">
                    <td>
                      {e.parlamentar ?? "—"}
                      {e.partido && (
                        <span className="ml-1 text-xs text-ink-3">({e.partido})</span>
                      )}
                      {e.descricao && (
                        <p className="mt-0.5 line-clamp-1 max-w-xs text-xs text-ink-3">
                          {e.descricao}
                        </p>
                      )}
                    </td>
                    <td className="font-mono text-xs text-ink-2">
                      {e.numero ?? e.codigo}
                      {e.ano ? ` / ${e.ano}` : ""}
                    </td>
                    <td className="text-ink-2">{e.modalidade ?? "—"}</td>
                    <td className="text-ink-2">{e.area ?? "—"}</td>
                    <td className="tabular-nums">{formatBRL(e.empenhado)}</td>
                    <td className="tabular-nums">{formatBRL(e.pago)}</td>
                    <td className="tabular-nums">
                      {e.percentual_executado.toFixed(0)}%
                    </td>
                    <td className="text-ink-2">{formatDate(e.data_repasse)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}

function Distribuicao({
  titulo,
  itens,
}: {
  titulo: string;
  itens: { chave: string; valor: string; quantidade: number }[];
}) {
  const max = Math.max(1, ...itens.map((i) => num(i.valor)));
  return (
    <div className="card p-5">
      <h2 className="label-mono">{titulo}</h2>
      <ul className="mt-4 flex flex-col gap-2">
        {itens.slice(0, 8).map((i) => (
          <li key={i.chave} className="flex items-center gap-3 text-sm">
            <span className="w-40 shrink-0 truncate text-ink-2" title={i.chave}>
              {i.chave}
            </span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
              <span
                className="block h-full rounded-full bg-lime"
                style={{ width: `${(num(i.valor) / max) * 100}%` }}
              />
            </span>
            <span className="shrink-0 text-right tabular-nums text-xs">
              {formatBRL(i.valor)}
            </span>
          </li>
        ))}
        {itens.length === 0 && <li className="text-sm text-ink-3">Sem dados.</li>}
      </ul>
    </div>
  );
}
