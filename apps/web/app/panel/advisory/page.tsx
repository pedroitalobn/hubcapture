"use client";

import { useCallback, useEffect, useState } from "react";
import { ModuloGate } from "@/components/ModuloGate";
import { SkeletonCards } from "@/components/Skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import { useTerritorio } from "@/lib/territorio";

interface ContatoAssessoria {
  nome: string;
  telefone: string;
  descricao?: string | null;
  whatsapp_url: string;
}

/** Link wa.me com a mensagem de abertura já preenchida. */
function linkWhatsApp(c: ContatoAssessoria): string {
  const texto = `Olá, ${c.nome}! Vim do Hub Capture e tenho uma dúvida orçamentária.`;
  return `${c.whatsapp_url}?text=${encodeURIComponent(texto)}`;
}

function IconeWhatsApp() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden>
      <path d="M12.04 2c-5.46 0-9.9 4.44-9.9 9.9 0 1.75.46 3.45 1.32 4.95L2 22l5.3-1.39a9.87 9.87 0 0 0 4.74 1.21h.01c5.46 0 9.9-4.44 9.9-9.9 0-2.65-1.03-5.14-2.9-7.01A9.82 9.82 0 0 0 12.04 2Zm0 18.15a8.2 8.2 0 0 1-4.19-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.2 8.2 0 0 1-1.26-4.39c0-4.54 3.7-8.24 8.25-8.24 2.2 0 4.27.86 5.82 2.42a8.18 8.18 0 0 1 2.41 5.83c0 4.54-3.7 8.24-8.24 8.24Zm4.52-6.17c-.25-.12-1.47-.72-1.7-.8-.22-.09-.39-.13-.55.12-.17.25-.64.8-.78.97-.14.16-.29.18-.54.06-.24-.12-1.04-.38-1.99-1.23-.73-.65-1.23-1.45-1.37-1.7-.15-.24-.02-.38.1-.5.12-.11.25-.29.37-.43.13-.15.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.13-.55-1.34-.76-1.83-.2-.48-.4-.42-.55-.42h-.47c-.16 0-.43.06-.66.3-.22.25-.86.85-.86 2.07 0 1.21.89 2.39 1.01 2.55.12.17 1.75 2.67 4.23 3.74.59.26 1.05.41 1.41.52.6.19 1.13.16 1.56.1.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.07.15-1.18-.06-.1-.23-.16-.48-.29Z" />
    </svg>
  );
}

function ListaContatos() {
  const [contatos, setContatos] = useState<ContatoAssessoria[] | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    void (async () => {
      const { data, error } = await api.GET("/api/v1/advisory/contacts", {});
      if (error) {
        setErro(true);
        setContatos([]);
        return;
      }
      setContatos((data as ContatoAssessoria[]) ?? []);
    })();
  }, []);

  if (contatos === null) return <SkeletonCards count={3} />;

  return (
    <>
      <header>
        <h1 className="page-title">Assessoria</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Tire dúvidas orçamentárias direto com a assessoria. Escolha um
          contato e a conversa abre no WhatsApp.
        </p>
      </header>

      {erro && (
        <p className="text-sm text-warn">
          Não foi possível carregar os contatos agora. Tente novamente em
          instantes.
        </p>
      )}

      <section className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {contatos.map((c) => (
          <div key={`${c.nome}-${c.telefone}`} className="card flex flex-col gap-4 p-6">
            <div className="flex items-center gap-3">
              <span
                aria-hidden
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-hairline font-mono text-base text-ink"
              >
                {c.nome.charAt(0).toUpperCase()}
              </span>
              <div className="min-w-0">
                <p className="truncate text-base tracking-tight">{c.nome}</p>
                <p className="truncate text-xs text-ink-3">
                  {c.descricao || "Assessoria orçamentária"}
                </p>
              </div>
            </div>
            <p className="font-mono text-sm text-ink-2">{c.telefone}</p>
            <a
              href={linkWhatsApp(c)}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary mt-auto inline-flex items-center justify-center gap-2"
            >
              <IconeWhatsApp />
              Chamar no WhatsApp
            </a>
          </div>
        ))}
      </section>

      <CentralDeDemandas />
    </>
  );
}

/* ── Central de demandas (ponto 20) ─────────────────────────────────────────
   O WhatsApp resolve a conversa, não o acompanhamento: o pedido some no meio
   do chat e ninguém sabe o que ficou pendente. Aqui a demanda é registro —
   nasce aberta, anda, e termina resolvida, com histórico que o gestor relê. */
interface EventoDemanda {
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
  created_at: string;
  historico?: EventoDemanda[] | null;
}

const SITUACAO_TOM: Record<string, "success" | "warning" | "neutral"> = {
  aberta: "warning",
  em_andamento: "warning",
  resolvida: "success",
  cancelada: "neutral",
};

const SITUACAO_ROTULO: Record<string, string> = {
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

function CentralDeDemandas() {
  const { municipios, selecionados } = useTerritorio();
  const [itens, setItens] = useState<Demanda[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [assunto, setAssunto] = useState("");
  const [descricao, setDescricao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aberta, setAberta] = useState<string | null>(null);
  const [resposta, setResposta] = useState("");

  const carregar = useCallback(async () => {
    const { data } = await api.GET("/api/v1/advisory/requests", {});
    if (data) setItens(data as Demanda[]);
    setCarregando(false);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrir(e: React.FormEvent) {
    e.preventDefault();
    if (!assunto.trim() || enviando) return;
    setEnviando(true);
    setErro(null);
    // o município do recorte ativo viaja junto: quase toda demanda é sobre um
    const municipio = selecionados[0] ?? municipios[0]?.ibge ?? null;
    const { error } = await api.POST("/api/v1/advisory/requests", {
      body: {
        assunto: assunto.trim(),
        descricao: descricao.trim() || null,
        municipio_ibge: municipio,
      },
    });
    setEnviando(false);
    if (error) {
      setErro("Não foi possível registrar a demanda agora. Tente novamente.");
      return;
    }
    setAssunto("");
    setDescricao("");
    await carregar();
  }

  async function responder(id: string, situacao?: string) {
    const texto = resposta.trim();
    if (!texto && !situacao) return;
    const { error } = await api.POST(
      "/api/v1/advisory/requests/{demanda_id}/messages",
      {
        params: { path: { demanda_id: id } },
        body: { texto, situacao: situacao ?? null },
      },
    );
    if (error) {
      setErro("Não foi possível enviar a mensagem agora.");
      return;
    }
    setResposta("");
    await carregar();
  }

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="tracking-tight">Central de demandas</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Registre o pedido aqui e ele fica com prazo, estado e histórico — em vez
          de se perder na conversa. A assessoria responde por esta mesma tela.
        </p>
      </div>

      <form onSubmit={abrir} className="card flex flex-col gap-3 p-5">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Assunto</span>
          <input
            value={assunto}
            onChange={(e) => setAssunto(e.target.value)}
            placeholder="Ex.: revisar plano de trabalho da proposta 30011/2026"
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Descrição (opcional)</span>
          <textarea
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            rows={3}
            placeholder="Conte o que precisa, com o número da proposta ou do processo."
            className="input"
          />
        </label>
        <button
          type="submit"
          disabled={enviando || !assunto.trim()}
          className="btn btn-primary self-start"
        >
          {enviando ? "Registrando…" : "Abrir demanda"}
        </button>
      </form>

      {erro && (
        <p role="status" className="text-sm tone-danger">
          {erro}
        </p>
      )}

      {carregando ? (
        <p className="text-sm text-ink-3">Carregando suas demandas…</p>
      ) : itens.length === 0 ? (
        <p className="text-sm text-ink-3">
          Nenhuma demanda registrada ainda.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {itens.map((d) => (
            <li key={d.id} className="card flex flex-col gap-3 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-ink">{d.assunto}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-ink-3">
                    aberta em {quando(d.created_at)}
                  </p>
                </div>
                <StatusBadge tone={SITUACAO_TOM[d.situacao] ?? "neutral"}>
                  {SITUACAO_ROTULO[d.situacao] ?? d.situacao}
                </StatusBadge>
              </div>

              {(d.historico ?? []).length > 0 && (
                <ol className="flex flex-col gap-2 border-l border-hairline pl-3">
                  {(d.historico ?? []).map((e, i) => (
                    <li key={i} className="text-sm">
                      <span className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                        {e.autor === "assessoria" ? "Assessoria" : "Você"} ·{" "}
                        {quando(e.em)}
                      </span>
                      {e.texto && (
                        <span className="mt-0.5 block text-ink-2">{e.texto}</span>
                      )}
                      {e.situacao && (
                        <span className="mt-0.5 block text-[12px] text-ink-3">
                          situação: {SITUACAO_ROTULO[e.situacao] ?? e.situacao}
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              )}

              {aberta === d.id ? (
                <div className="flex flex-col gap-2">
                  <textarea
                    value={resposta}
                    onChange={(e) => setResposta(e.target.value)}
                    rows={2}
                    placeholder="Escreva sua mensagem"
                    className="input"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => void responder(d.id)}
                      disabled={!resposta.trim()}
                      className="btn btn-primary btn-sm"
                    >
                      Enviar
                    </button>
                    {d.situacao !== "resolvida" && (
                      <button
                        onClick={() => void responder(d.id, "resolvida")}
                        className="btn btn-ghost btn-sm"
                      >
                        Marcar como resolvida
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setAberta(null);
                        setResposta("");
                      }}
                      className="btn btn-ghost btn-sm"
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setAberta(d.id)}
                  className="btn btn-ghost btn-sm self-start"
                >
                  Responder / acompanhar
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function AssessoriaPage() {
  return (
    <ModuloGate modulo="assessoria" titulo="Assessoria">
      <ListaContatos />
    </ModuloGate>
  );
}
