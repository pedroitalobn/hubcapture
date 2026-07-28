"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, baixarPdfProposta } from "@/lib/api/client";

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
};

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
      const { data, error } = await api.GET("/api/v1/propostas/{proposta_id}", {
        params: { path: { proposta_id: params.id } },
      });
      if (error) {
        setErro("Proposta não encontrada (ou fora do seu território).");
        return;
      }
      setP(data as Proposta);
      const [fav, mon] = await Promise.all([
        api.GET("/api/v1/favoritos"),
        api.GET("/api/v1/monitoramentos"),
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
      await api.DELETE("/api/v1/favoritos/{proposta_id}", {
        params: { path: { proposta_id: params.id } },
      });
    } else {
      await api.POST("/api/v1/favoritos", { body: { proposta_id: params.id } });
    }
    setFavorita(!favorita);
  }

  async function monitorar() {
    const { error } = await api.POST("/api/v1/monitoramentos", {
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
        <Link href="/painel/captacao" className="btn btn-ghost btn-sm">
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
            href="/painel/captacao"
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
          <button onClick={() => baixarPdfProposta(p.id)} className="btn btn-primary">
            Exportar PDF
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
