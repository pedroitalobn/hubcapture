"use client";

import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Button, Input, cx } from "@/components/ui";
import { chatStream } from "@/lib/api/client";

type Msg = { autor: "user" | "ia"; texto: string };

const MODOS = [
  { valor: "propostas", rotulo: "Minhas propostas" },
  { valor: "copiloto", rotulo: "Tutoriais" },
] as const;

const SUGESTOES: Record<string, string[]> = {
  propostas: [
    "Quais propostas estão com pendência?",
    "Qual o prazo mais próximo?",
    "Some o valor das propostas em análise.",
  ],
  copiloto: [
    "Como cadastrar um plano de trabalho no TransfereGov?",
    "O que é contrapartida e quando é obrigatória?",
    "Passo a passo para regularizar o CAUC.",
  ],
};

export default function ChatPage() {
  const [modo, setModo] = useState<"propostas" | "copiloto">("propostas");
  const [pergunta, setPergunta] = useState("");
  const [mensagens, setMensagens] = useState<Msg[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens]);

  async function perguntar(q: string) {
    if (!q || ocupado) return;
    setPergunta("");
    setMensagens((m) => [...m, { autor: "user", texto: q }, { autor: "ia", texto: "" }]);
    setOcupado(true);
    try {
      await chatStream(q, modo, (delta) => {
        setMensagens((m) => {
          const copia = [...m];
          const ultimo = copia[copia.length - 1];
          if (ultimo) copia[copia.length - 1] = { autor: "ia", texto: ultimo.texto + delta };
          return copia;
        });
      });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <PageHeader
        titulo="Copiloto"
        descricao="Pergunte sobre as suas propostas ou peça um tutorial das plataformas."
        acoes={
          <div
            className="inline-flex overflow-hidden rounded-md border border-line"
            role="group"
            aria-label="Modo do copiloto"
          >
            {MODOS.map((m) => (
              <button
                key={m.valor}
                type="button"
                onClick={() => setModo(m.valor)}
                aria-pressed={modo === m.valor}
                className={cx(
                  "px-3 py-1.5 text-sm transition",
                  modo === m.valor
                    ? "bg-brand font-medium text-brand-fg"
                    : "bg-bg text-ink-2 hover:bg-surface hover:text-ink",
                )}
              >
                {m.rotulo}
              </button>
            ))}
          </div>
        }
      />

      <div className="flex min-h-[46vh] flex-col gap-3 rounded-xl border border-line bg-bg p-4 shadow-card">
        {mensagens.length === 0 ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted">
              {modo === "propostas"
                ? "O copiloto responde com base nas propostas do seu território."
                : "O copiloto ensina o passo a passo das plataformas de transferência."}
            </p>
            <div className="flex flex-wrap gap-2">
              {(SUGESTOES[modo] ?? []).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void perguntar(s)}
                  className="rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-2 transition hover:border-brand hover:text-brand"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          mensagens.map((m, i) => (
            <div
              key={i}
              className={cx(
                "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
                m.autor === "user"
                  ? "self-end bg-brand text-brand-fg"
                  : "self-start bg-surface text-ink-2",
              )}
            >
              {m.texto || "…"}
            </div>
          ))
        )}
        <div ref={fimRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void perguntar(pergunta.trim());
        }}
        className="flex gap-2"
      >
        <Input
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Sua pergunta…"
          aria-label="Pergunta ao copiloto"
          className="flex-1"
        />
        <Button type="submit" disabled={ocupado || !pergunta.trim()}>
          {ocupado ? "…" : "Enviar"}
        </Button>
      </form>
    </>
  );
}
