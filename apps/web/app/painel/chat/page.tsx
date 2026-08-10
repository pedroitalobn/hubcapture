"use client";

import { BookOpen, FileText, Send, Sparkles, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/Button";
import { Tabs } from "@/components/Tabs";
import { chatStream } from "@/lib/api/client";

type Msg = { autor: "user" | "ia"; texto: string };

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1" aria-label="Digitando…">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-typing"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </span>
  );
}

export default function ChatPage() {
  const [modo, setModo] = useState<"propostas" | "copiloto">("propostas");
  const [pergunta, setPergunta] = useState("");
  const [mensagens, setMensagens] = useState<Msg[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    const q = pergunta.trim();
    if (!q || ocupado) return;
    setPergunta("");
    setMensagens((m) => [...m, { autor: "user", texto: q }, { autor: "ia", texto: "" }]);
    setOcupado(true);
    try {
      await chatStream(q, modo, (delta) => {
        setMensagens((m) => {
          const copia = [...m];
          const ultimo = copia[copia.length - 1];
          if (ultimo) {
            copia[copia.length - 1] = { autor: "ia", texto: ultimo.texto + delta };
          }
          return copia;
        });
      });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 animate-fade-up">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 ring-1 ring-brand-100 dark:bg-brand-900/30 dark:text-brand-300 dark:ring-brand-900/50">
            <Sparkles className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Copiloto</h1>
            <p className="text-sm text-gray-500">
              IA sobre as suas propostas e tutoriais das plataformas.
            </p>
          </div>
        </div>
        <Tabs
          options={[
            { value: "propostas", label: "Minhas propostas", icon: FileText },
            { value: "copiloto", label: "Tutoriais", icon: BookOpen },
          ]}
          value={modo}
          onChange={setModo}
        />
      </header>

      <div className="flex min-h-[50vh] flex-col gap-4 overflow-y-auto rounded-xl border border-gray-200 bg-white p-4 shadow-card dark:border-gray-800 dark:bg-gray-900">
        {mensagens.length === 0 && (
          <div className="m-auto flex flex-col items-center gap-2 py-10 text-center animate-fade-up">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400">
              <Sparkles className="h-6 w-6" aria-hidden />
            </span>
            <p className="text-sm font-medium">Como posso ajudar?</p>
            <p className="max-w-sm text-sm text-gray-500">
              Pergunte sobre suas propostas ou peça um tutorial do TransfereGov.
            </p>
          </div>
        )}
        {mensagens.map((m, i) => (
          <div
            key={i}
            className={`flex max-w-[85%] items-end gap-2 animate-fade-up ${
              m.autor === "user" ? "self-end flex-row-reverse" : "self-start"
            }`}
          >
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                m.autor === "user"
                  ? "bg-brand text-brand-fg"
                  : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
              }`}
              aria-hidden
            >
              {m.autor === "user" ? (
                <UserRound className="h-3.5 w-3.5" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
            </span>
            <div
              className={`whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm shadow-sm ${
                m.autor === "user"
                  ? "rounded-br-sm bg-brand text-brand-fg"
                  : "rounded-bl-sm bg-gray-100 dark:bg-gray-800"
              }`}
            >
              {m.texto || (m.autor === "ia" && ocupado ? <TypingDots /> : "…")}
            </div>
          </div>
        ))}
        <div ref={fimRef} />
      </div>

      <form onSubmit={enviar} className="flex gap-2">
        <input
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Sua pergunta…"
          className="flex-1 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm shadow-sm transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-900"
        />
        <Button
          type="submit"
          loading={ocupado}
          disabled={!pergunta.trim()}
          icon={<Send className="h-4 w-4" aria-hidden />}
          className="rounded-xl"
        >
          Enviar
        </Button>
      </form>
    </>
  );
}
