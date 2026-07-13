"use client";

import { useEffect, useRef, useState } from "react";
import { chatStream } from "@/lib/api/client";

type Msg = { autor: "user" | "ia"; texto: string };

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
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Copiloto</h1>
        <div className="inline-flex overflow-hidden rounded-md border border-gray-300 text-sm dark:border-gray-700">
          {(["propostas", "copiloto"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setModo(m)}
              className={`px-3 py-1.5 ${
                modo === m ? "bg-brand text-brand-fg" : ""
              }`}
            >
              {m === "propostas" ? "Minhas propostas" : "Tutoriais"}
            </button>
          ))}
        </div>
      </header>

      <div className="flex min-h-[50vh] flex-col gap-3 rounded-md border border-gray-200 p-4 dark:border-gray-800">
        {mensagens.length === 0 && (
          <p className="text-sm text-gray-500">
            Pergunte sobre suas propostas ou peça um tutorial do TransfereGov.
          </p>
        )}
        {mensagens.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
              m.autor === "user"
                ? "self-end bg-brand text-brand-fg"
                : "self-start bg-gray-100 dark:bg-gray-900"
            }`}
          >
            {m.texto || "…"}
          </div>
        ))}
        <div ref={fimRef} />
      </div>

      <form onSubmit={enviar} className="flex gap-2">
        <input
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Sua pergunta…"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
        />
        <button
          type="submit"
          disabled={ocupado}
          className="rounded-md bg-brand px-4 py-2 text-brand-fg disabled:opacity-60"
        >
          {ocupado ? "…" : "Enviar"}
        </button>
      </form>
    </>
  );
}
