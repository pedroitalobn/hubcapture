"use client";

/**
 * Fila de demandas da Assessoria (ponto 20) — o outro lado da central que o
 * gestor usa em `/panel/advisory`.
 *
 * A demanda é do tenant que a abriu (RLS por `usuario_id`); esta tela lê pela
 * sessão de plataforma, que é a única que enxerga todas — é a administração que
 * responde. Por isso a fila mostra SEMPRE de quem é o pedido: sem isso, a
 * resposta certa iria para a conversa errada.
 */

import { useCallback, useEffect, useState } from "react";
import { Skeleton } from "@/components/Skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";

interface Evento {
  em?: string | null;
  autor?: string | null;
  texto?: string | null;
  situacao?: string | null;
}

interface Demanda {
  id: string;
  assunto: string;
  descricao?: string | null;
  situacao: string;
  municipio_ibge?: string | null;
  created_at: string;
  historico?: Evento[] | null;
  usuario_email?: string | null;
  usuario_nome?: string | null;
}

const SITUACOES = [
  ["", "Todas"],
  ["aberta", "Abertas"],
  ["em_andamento", "Em andamento"],
  ["resolvida", "Resolvidas"],
  ["cancelada", "Canceladas"],
] as const;

const TOM: Record<string, "success" | "warning" | "neutral"> = {
  aberta: "warning",
  em_andamento: "warning",
  resolvida: "success",
  cancelada: "neutral",
};

const ROTULO: Record<string, string> = {
  aberta: "Aberta",
  em_andamento: "Em andamento",
  resolvida: "Resolvida",
  cancelada: "Cancelada",
};

function quando(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("pt-BR");
}

export default function AdminDemandasPage() {
  const [itens, setItens] = useState<Demanda[] | null>(null);
  const [filtro, setFiltro] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [respostas, setRespostas] = useState<Record<string, string>>({});

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/admin/advisory/requests", {
      params: { query: { situacao: filtro || undefined } },
    } as never);
    if (error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      setItens([]);
      return;
    }
    setItens((data as Demanda[]) ?? []);
  }, [filtro]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function responder(id: string, situacao?: string) {
    const texto = (respostas[id] ?? "").trim();
    if (!texto && !situacao) return;
    setMsg(null);
    const { error } = await api.POST(
      "/api/v1/admin/advisory/requests/{demanda_id}/reply",
      {
        params: { path: { demanda_id: id } },
        body: { texto, situacao: situacao ?? null },
      },
    );
    if (error) {
      setMsg("Falha ao responder a demanda.");
      return;
    }
    setRespostas((r) => ({ ...r, [id]: "" }));
    await carregar();
  }

  return (
    <>
      <header>
        <h1 className="page-title">Demandas</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Pedidos abertos pelos gestores na aba Assessoria. Responder aqui
          aparece na tela do cliente, com o histórico inteiro — e mudar a
          situação avisa em que pé está.
        </p>
      </header>

      {msg && <p className="text-sm text-warn">{msg}</p>}

      <div className="flex flex-wrap gap-2">
        {SITUACOES.map(([chave, rotulo]) => (
          <button
            key={chave || "todas"}
            type="button"
            onClick={() => setFiltro(chave)}
            className={`chip ${filtro === chave ? "chip-active" : ""}`}
          >
            {rotulo}
          </button>
        ))}
      </div>

      {itens === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : itens.length === 0 ? (
        <p className="text-sm text-ink-3">
          {filtro ? "Nenhuma demanda nesta situação." : "Nenhuma demanda ainda."}
        </p>
      ) : (
        <section className="flex flex-col gap-3">
          {itens.map((d) => (
            <article key={d.id} className="card flex flex-col gap-3 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-ink">{d.assunto}</p>
                  <p className="mt-0.5 text-[12px] text-ink-3">
                    {[
                      d.usuario_nome || d.usuario_email || "usuário removido",
                      d.municipio_ibge ? `IBGE ${d.municipio_ibge}` : null,
                      quando(d.created_at),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <StatusBadge tone={TOM[d.situacao] ?? "neutral"}>
                  {ROTULO[d.situacao] ?? d.situacao}
                </StatusBadge>
              </div>

              {(d.historico ?? []).length > 0 && (
                <ol className="flex flex-col gap-2 border-l border-hairline pl-3">
                  {(d.historico ?? []).map((e, i) => (
                    <li key={i} className="text-sm">
                      <span className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                        {e.autor === "assessoria" ? "Assessoria" : "Gestor"} ·{" "}
                        {quando(e.em)}
                      </span>
                      {e.texto && (
                        <span className="mt-0.5 block text-ink-2">{e.texto}</span>
                      )}
                    </li>
                  ))}
                </ol>
              )}

              <textarea
                value={respostas[d.id] ?? ""}
                onChange={(e) =>
                  setRespostas((r) => ({ ...r, [d.id]: e.target.value }))
                }
                rows={2}
                placeholder="Resposta da assessoria"
                className="input"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void responder(d.id)}
                  disabled={!(respostas[d.id] ?? "").trim()}
                  className="btn btn-primary btn-sm"
                >
                  Responder
                </button>
                {d.situacao === "aberta" && (
                  <button
                    type="button"
                    onClick={() => void responder(d.id, "em_andamento")}
                    className="btn btn-ghost btn-sm"
                  >
                    Marcar em andamento
                  </button>
                )}
                {d.situacao !== "resolvida" && (
                  <button
                    type="button"
                    onClick={() => void responder(d.id, "resolvida")}
                    className="btn btn-ghost btn-sm"
                  >
                    Resolver
                  </button>
                )}
              </div>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
