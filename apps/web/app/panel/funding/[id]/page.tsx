"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

type Prazo = { tipo?: string | null; data_limite?: string | null };
type Pendencia = { descricao?: string | null; prazo?: string | null };

type Proposta = {
  id: string;
  fonte: string;
  id_externo: string;
  numero_proposta?: string | null;
  titulo?: string | null;
  objeto?: string | null;
  orgao_superior?: string | null;
  modalidade?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  contrapartida?: string | null;
  situacao?: string | null;
  emenda?: string | null;
  prazos?: Prazo[] | null;
  pendencias?: Pendencia[] | null;
  movimentacao?: string | null;
  data_atualizacao_fonte?: string | null;
  url_origem?: string | null;
  proveniencia?: Record<string, string> | null;
  resumo_ia?: string | null;
  tipo?: string;
  execucao?: {
    valor_global?: string | null;
    valor_empenhado?: string | null;
    valor_liberado?: string | null;
    valor_pago?: string | null;
    saldo_conta?: string | null;
    ano?: string | number | null;
    ente_recebedor?: string | null;
    natureza_juridica?: string | null;
    data_assinatura?: string | null;
    data_inicio_vigencia?: string | null;
    data_fim_vigencia?: string | null;
    tipo_transferencia?: string | null;
  } | null;
  // registro-fonte COMPLETO (todos os campos do site de origem)
  dados_fonte?: Record<string, unknown> | null;
};

function num(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

// rótulo legível a partir da chave crua da fonte (ex.: valor_total_repasse_plano_acao
// → "Valor total repasse"). Remove os sufixos de tabela e capitaliza.
function humanizar(chave: string): string {
  const limpa = chave
    .replace(/_(plano_acao|programa|especial|convenio|beneficiario|proposta)$/g, "")
    .replace(/_/g, " ")
    .trim();
  return limpa.charAt(0).toUpperCase() + limpa.slice(1);
}

function valorLegivel(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// Renderiza TODOS os campos do registro-fonte. `dados_fonte` costuma vir agrupado
// ({plano_acao:{...}, programa:{...}}); se um valor for objeto, vira subgrupo.
function DadosCompletos({ dados }: { dados: Record<string, unknown> }) {
  const grupos = Object.entries(dados).filter(
    ([, v]) => v && typeof v === "object" && !Array.isArray(v),
  );
  const soltos = Object.entries(dados).filter(
    ([, v]) => !(v && typeof v === "object" && !Array.isArray(v)),
  );
  const bloco = (titulo: string | null, obj: Record<string, unknown>) => {
    const entradas = Object.entries(obj).filter(([, v]) => v !== null && v !== "");
    if (entradas.length === 0) return null;
    return (
      <div key={titulo ?? "raiz"} className="mb-4 last:mb-0">
        {titulo && <p className="field-label mb-2 font-medium">{humanizar(titulo)}</p>}
        <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {entradas.map(([k, v]) => (
            <Campo key={k} rotulo={humanizar(k)} valor={valorLegivel(v)} />
          ))}
        </div>
      </div>
    );
  };
  return (
    <>
      {soltos.length > 0 && bloco(null, Object.fromEntries(soltos))}
      {grupos.map(([g, obj]) => bloco(g, obj as Record<string, unknown>))}
    </>
  );
}

function formatBRL(v?: string | null): string {
  if (!v) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function Secao({
  titulo,
  children,
}: {
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-5">
      <h2 className="label-mono mb-3">{titulo}</h2>
      {children}
    </section>
  );
}

function Campo({ rotulo, valor }: { rotulo: string; valor?: string | null }) {
  return (
    <div>
      <p className="field-label">{rotulo}</p>
      <p className="text-sm">{valor || "—"}</p>
    </div>
  );
}

const CANAIS = [
  ["painel", "Painel"],
  ["email", "E-mail"],
  ["wpp", "WhatsApp"],
] as const;

export default function PropostaDetalhePage() {
  const params = useParams<{ id: string }>();
  const [p, setP] = useState<Proposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [favorita, setFavorita] = useState(false);
  const [monitorando, setMonitorando] = useState(false);
  const [canais, setCanais] = useState<string[]>(["painel"]);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const { data, error } = await api.GET("/api/v1/proposals/{proposta_id}", {
        params: { path: { proposta_id: params.id } },
      });
      if (error) {
        setErro("Proposta não encontrada (ou fora do seu território).");
        return;
      }
      setP(data as Proposta);
      const [fav, mon] = await Promise.all([
        api.GET("/api/v1/favorites"),
        api.GET("/api/v1/monitors"),
      ]);
      if (fav.data)
        setFavorita(
          (fav.data as { proposta_id: string }[]).some(
            (f) => f.proposta_id === params.id,
          ),
        );
      if (mon.data)
        setMonitorando(
          (mon.data as { proposta_id: string; ativo: boolean }[]).some(
            (m) => m.proposta_id === params.id && m.ativo,
          ),
        );
    })();
  }, [params.id]);

  async function alternarFavorito() {
    if (favorita) {
      await api.DELETE("/api/v1/favorites/{proposta_id}", {
        params: { path: { proposta_id: params.id } },
      });
    } else {
      await api.POST("/api/v1/favorites", { body: { proposta_id: params.id } });
    }
    setFavorita(!favorita);
  }

  async function monitorar() {
    const { error } = await api.POST("/api/v1/monitors", {
      body: { proposta_id: params.id, canais },
    });
    if (!error) {
      setMonitorando(true);
      setMsg(
        "Monitorando: você recebe aviso quando a situação ou o prazo mudar.",
      );
    }
  }

  if (erro) {
    return (
      <>
        <p className="text-ink-2">{erro}</p>
        <Link href="/panel/funding" className="btn btn-ghost btn-sm">
          ← Voltar à captação
        </Link>
      </>
    );
  }
  if (!p) return <p className="text-ink-3">Carregando…</p>;

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            href="/panel/funding"
            className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
          >
            ← Captação
          </Link>
          <h1 className="page-title mt-1">
            {p.titulo ?? p.objeto ?? p.id_externo}
          </h1>
          <p className="mt-1 text-sm text-ink-2">
            {p.municipio_nome ?? p.municipio_ibge}
            {p.uf ? `/${p.uf}` : ""} · {p.fonte} ·{" "}
            <span
              className={
                p.tipo === "disponivel" ? "text-emerald-600" : "text-ink-2"
              }
            >
              {p.tipo === "disponivel" ? "oportunidade disponível" : "cadastrada"}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={alternarFavorito} className="btn btn-ghost">
            {favorita ? "★ Favorita" : "☆ Favoritar"}
          </button>
        </div>
      </header>

      {msg && <p className="text-sm text-emerald-600">{msg}</p>}

      {p.resumo_ia && (
        <Secao titulo="Resumo inteligente">
          <p className="text-sm leading-relaxed">{p.resumo_ia}</p>
        </Secao>
      )}

      <div className="grid gap-5 md:grid-cols-2">
        <Secao titulo="Dados gerais">
          <div className="grid grid-cols-2 gap-3">
            <Campo rotulo="Nº da proposta" valor={p.numero_proposta ?? p.id_externo} />
            <Campo rotulo="Órgão superior" valor={p.orgao_superior} />
            <Campo rotulo="Modalidade" valor={p.modalidade} />
            <Campo rotulo="Emenda" valor={p.emenda} />
            <Campo rotulo="Atualizado na fonte" valor={p.data_atualizacao_fonte} />
            {p.url_origem && (
              <div>
                <p className="field-label">Origem</p>
                <a
                  href={p.url_origem}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm underline"
                >
                  abrir na fonte oficial ↗
                </a>
              </div>
            )}
          </div>
          {p.objeto && (
            <p className="mt-3 text-sm text-ink-2">{p.objeto}</p>
          )}
        </Secao>

        <Secao titulo="Valores">
          <div className="grid grid-cols-2 gap-3">
            <Campo rotulo="Valor total" valor={formatBRL(p.valor_total)} />
            <Campo rotulo="Contrapartida" valor={formatBRL(p.contrapartida)} />
          </div>
        </Secao>

        {p.execucao && (
          <Secao titulo={`Execução financeira — TransfereGov${p.execucao.ano ? ` (${p.execucao.ano})` : ""}`}>
            {(() => {
              const global = num(p.execucao!.valor_global ?? p.valor_total);
              const empenhado = num(p.execucao!.valor_empenhado);
              const liberado = num(p.execucao!.valor_liberado);
              const pago = num(p.execucao!.valor_pago);
              const pct = (v: number) =>
                global > 0 ? `${Math.min(100, (v / global) * 100)}%` : "0%";
              return (
                <div className="flex flex-col gap-3">
                  {/* barra: global (trilho) ▸ empenhado ▸ liberado ▸ pago */}
                  <div
                    className="relative h-3 overflow-hidden rounded-full bg-surface-2"
                    title="Barra sobre o valor global: empenhado, liberado e pago"
                  >
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-lime/30"
                      style={{ width: pct(empenhado) }}
                    />
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-lime/60"
                      style={{ width: pct(liberado) }}
                    />
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-lime"
                      style={{ width: pct(pago) }}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <Campo rotulo="Valor global" valor={formatBRL(p.execucao!.valor_global)} />
                    <Campo rotulo="Empenhado" valor={formatBRL(p.execucao!.valor_empenhado)} />
                    <Campo rotulo="Liberado" valor={formatBRL(p.execucao!.valor_liberado)} />
                    <Campo rotulo="Pago" valor={formatBRL(p.execucao!.valor_pago)} />
                    <Campo rotulo="Saldo em conta" valor={formatBRL(p.execucao!.saldo_conta)} />
                    <div>
                      <p className="field-label">Empenhado a utilizar</p>
                      <p className="text-sm font-medium text-lime">
                        {formatBRL(String(Math.max(0, empenhado - pago)))}
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <Campo rotulo="Tipo" valor={p.execucao!.tipo_transferencia} />
                    <Campo rotulo="Ente recebedor" valor={p.execucao!.ente_recebedor} />
                    <Campo rotulo="Assinatura" valor={p.execucao!.data_assinatura} />
                    <Campo rotulo="Início da vigência" valor={p.execucao!.data_inicio_vigencia} />
                    <Campo rotulo="Fim da vigência" valor={p.execucao!.data_fim_vigencia} />
                    <Campo rotulo="Natureza jurídica" valor={p.execucao!.natureza_juridica} />
                  </div>
                </div>
              );
            })()}
          </Secao>
        )}

        <Secao titulo="Situação e movimentação">
          <div className="grid gap-3">
            <Campo rotulo="Situação" valor={p.situacao} />
            <Campo rotulo="Última movimentação" valor={p.movimentacao} />
          </div>
        </Secao>

        <Secao titulo="Prazos">
          {(p.prazos ?? []).length === 0 ? (
            <p className="text-sm text-ink-3">Sem prazos registrados.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {p.prazos!.map((pr, i) => (
                <li key={i} className="flex justify-between gap-3">
                  <span>{pr.tipo ?? "prazo"}</span>
                  <span className="font-mono">{pr.data_limite ?? "—"}</span>
                </li>
              ))}
            </ul>
          )}
        </Secao>

        <Secao titulo="Pendências">
          {(p.pendencias ?? []).length === 0 ? (
            <p className="text-sm text-ink-3">Sem pendências.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {p.pendencias!.map((pe, i) => (
                <li key={i} className="flex justify-between gap-3">
                  <span>{pe.descricao ?? "—"}</span>
                  <span className="font-mono">{pe.prazo ?? ""}</span>
                </li>
              ))}
            </ul>
          )}
        </Secao>

        <Secao titulo="Acompanhar e ser avisado">
          {monitorando ? (
            <p className="text-sm text-emerald-600">
              ✓ Você monitora esta proposta — aviso quando mudar status ou prazo.
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap gap-3 text-sm">
                {CANAIS.map(([valor, rotulo]) => (
                  <label key={valor} className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={canais.includes(valor)}
                      disabled={valor === "painel"}
                      onChange={(e) =>
                        setCanais((prev) =>
                          e.target.checked
                            ? [...prev, valor]
                            : prev.filter((c) => c !== valor),
                        )
                      }
                    />
                    {rotulo}
                  </label>
                ))}
              </div>
              <button onClick={monitorar} className="btn btn-primary self-start">
                Monitorar proposta-chave
              </button>
            </div>
          )}
        </Secao>

        {p.dados_fonte && Object.keys(p.dados_fonte).length > 0 && (
          <Secao titulo="Dados completos da fonte">
            <p className="field-label mb-3 text-ink-3">
              Todos os campos como vêm da origem — a mesma informação que você veria
              direto no site oficial.
            </p>
            <DadosCompletos dados={p.dados_fonte} />
          </Secao>
        )}
      </div>

      {p.proveniencia && Object.keys(p.proveniencia).length > 0 && (
        <Secao titulo="Proveniência dos dados (API × painel)">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(p.proveniencia).map(([campo, origem]) => (
              <span
                key={campo}
                className="rounded-full border border-hairline px-2 py-0.5 font-mono text-[11px] text-ink-2"
              >
                {campo}: {origem}
              </span>
            ))}
          </div>
        </Secao>
      )}
    </>
  );
}
