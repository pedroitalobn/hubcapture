"use client";

import { useEffect, useRef, useState } from "react";
import { islandStream } from "@/lib/api/client";

/**
 * Dynamic Island do Copiloto — pill flutuante que PERSISTE em todas as telas do
 * painel (montada no layout, pós-onboarding). Fechada, é uma cápsula discreta;
 * expandida, vira um chat com o agente de tool calling do backend, mostrando em
 * tempo real qual ferramenta (repasses, fundos, prazos, obras…) está sendo
 * consultada. Histórico em sessionStorage — sobrevive à navegação entre telas.
 */

type Msg = { autor: "user" | "copiloto"; texto: string; tools?: string[] };

const HISTORICO_KEY = "hub_island_msgs";

const TOOL_LABEL: Record<string, string> = {
  repasses_visao_geral: "consultando repasses…",
  propostas_listar: "consultando fundos e propostas…",
  propostas_prazos: "verificando prazos…",
  conformidade_resumo: "checando conformidade fiscal…",
  obras_resumo: "consultando obras…",
  noticias_transferegov: "lendo notícias do TransfereGov…",
  pesquisar_propostas: "pesquisando propostas…",
};

const TOOL_CHIP: Record<string, string> = {
  repasses_visao_geral: "repasses",
  propostas_listar: "fundos/propostas",
  propostas_prazos: "prazos",
  conformidade_resumo: "conformidade",
  obras_resumo: "obras",
  noticias_transferegov: "notícias",
  pesquisar_propostas: "pesquisa",
};

const SUGESTOES = [
  "Quanto meu município recebeu?",
  "Quais propostas vencem este mês?",
  "Há oportunidades disponíveis?",
];

function historicoInicial(): Msg[] {
  if (typeof window !== "undefined") {
    try {
      const salvo = window.sessionStorage.getItem(HISTORICO_KEY);
      if (salvo) return JSON.parse(salvo) as Msg[];
    } catch {
      /* histórico corrompido → recomeça */
    }
  }
  return [];
}

export default function DynamicIsland() {
  const [aberta, setAberta] = useState(false);
  const [mensagens, setMensagens] = useState<Msg[]>(historicoInicial);
  const [pergunta, setPergunta] = useState("");
  const [pensando, setPensando] = useState(false);
  const [statusTool, setStatusTool] = useState<string | null>(null);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    window.sessionStorage.setItem(HISTORICO_KEY, JSON.stringify(mensagens));
  }, [mensagens]);

  useEffect(() => {
    if (aberta) fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, statusTool, aberta]);

  async function perguntar(texto: string) {
    const q = texto.trim();
    if (!q || pensando) return;
    setPergunta("");
    setPensando(true);
    setMensagens((m) => [...m, { autor: "user", texto: q }]);
    const tools: string[] = [];
    let resposta = "";
    try {
      await islandStream(q, (ev) => {
        if (ev.tool) {
          tools.push(ev.tool);
          setStatusTool(ev.tool);
        }
        if (ev.delta) resposta += ev.delta;
      });
      setMensagens((m) => [
        ...m,
        {
          autor: "copiloto",
          texto: resposta || "Não consegui responder agora — tente de novo.",
          tools: [...new Set(tools)],
        },
      ]);
    } catch {
      setMensagens((m) => [
        ...m,
        { autor: "copiloto", texto: "Falha ao falar com o Copiloto. Tente de novo." },
      ]);
    } finally {
      setStatusTool(null);
      setPensando(false);
    }
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-50 flex justify-center px-3">
      <div
        className={`pointer-events-auto overflow-hidden bg-abyss text-white shadow-2xl ring-1 ring-white/10 transition-all duration-300 ease-out ${
          aberta
            ? "w-full max-w-md rounded-3xl"
            : "w-auto cursor-pointer rounded-full hover:ring-white/25"
        }`}
      >
        {!aberta ? (
          <button
            onClick={() => setAberta(true)}
            className="flex items-center gap-2.5 px-4 py-2 text-sm"
            aria-label="Abrir Copiloto"
          >
            <span className="relative flex h-2 w-2">
              <span
                className={`absolute inline-flex h-full w-full rounded-full bg-lime opacity-75 ${
                  pensando ? "animate-ping" : ""
                }`}
              />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-lime" />
            </span>
            <span className="font-medium">Copiloto</span>
            {pensando && statusTool && (
              <span className="text-xs text-white/60">
                {TOOL_LABEL[statusTool] ?? "consultando…"}
              </span>
            )}
          </button>
        ) : (
          <div className="flex max-h-[70vh] flex-col">
            <div className="flex items-center justify-between px-4 py-2.5">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2 w-2">
                  <span
                    className={`absolute inline-flex h-full w-full rounded-full bg-lime opacity-75 ${
                      pensando ? "animate-ping" : ""
                    }`}
                  />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-lime" />
                </span>
                <span className="text-sm font-medium">Copiloto</span>
                <span className="font-mono text-[10px] uppercase tracking-wider text-white/40">
                  seu território, ao vivo
                </span>
              </div>
              <button
                onClick={() => setAberta(false)}
                className="rounded-full px-2 py-0.5 text-white/60 hover:bg-white/10 hover:text-white"
                aria-label="Recolher Copiloto"
              >
                —
              </button>
            </div>

            <div className="flex-1 space-y-2.5 overflow-y-auto px-4 pb-2">
              {mensagens.length === 0 && (
                <div className="space-y-1.5 pb-1">
                  <p className="text-xs text-white/50">
                    Pergunte sobre repasses, fundos, prazos, obras ou
                    conformidade — eu consulto os dados reais do seu território.
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {SUGESTOES.map((s) => (
                      <button
                        key={s}
                        onClick={() => void perguntar(s)}
                        className="rounded-full border border-white/15 px-2.5 py-1 text-xs text-white/80 hover:bg-white/10"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {mensagens.map((m, i) => (
                <div
                  key={i}
                  className={`max-w-[90%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                    m.autor === "user"
                      ? "ml-auto rounded-br-md bg-lime text-abyss"
                      : "rounded-bl-md bg-white/10"
                  }`}
                >
                  {m.texto}
                  {m.autor === "copiloto" && (m.tools ?? []).length > 0 && (
                    <span className="mt-1.5 flex flex-wrap gap-1">
                      {m.tools!.map((t) => (
                        <span
                          key={t}
                          className="rounded-full bg-white/10 px-1.5 py-px font-mono text-[9px] uppercase tracking-wider text-white/50"
                        >
                          {TOOL_CHIP[t] ?? t}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
              ))}
              {pensando && (
                <div className="max-w-[90%] rounded-2xl rounded-bl-md bg-white/10 px-3 py-2 text-sm text-white/60">
                  {statusTool
                    ? TOOL_LABEL[statusTool] ?? "consultando…"
                    : "pensando…"}
                </div>
              )}
              <div ref={fimRef} />
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void perguntar(pergunta);
              }}
              className="flex items-center gap-2 border-t border-white/10 px-3 py-2.5"
            >
              <input
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                placeholder="Pergunte ao Copiloto…"
                className="flex-1 bg-transparent text-sm text-white placeholder-white/40 outline-none"
                autoFocus
              />
              <button
                type="submit"
                disabled={pensando || !pergunta.trim()}
                className="rounded-full bg-lime px-3 py-1 text-sm font-medium text-abyss disabled:opacity-40"
              >
                →
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
