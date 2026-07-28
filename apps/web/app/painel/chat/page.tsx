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
        <h1 className="text-gradient text-2xl font-bold">Copiloto</h1>
        <div className="glass-card inline-flex gap-1 rounded-full! p-1 text-sm">
          {(["propostas", "copiloto"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setModo(m)}
              className={`pressable rounded-full px-3 py-1.5 transition ${
                modo === m
                  ? "bg-white/12 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,.12),0_2px_10px_rgba(99,102,241,.25)]"
                  : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
              }`}
            >
              {m === "propostas" ? "Minhas propostas" : "Tutoriais"}
            </button>
          ))}
        </div>
      </header>

      <div className="glass-card flex min-h-[50vh] flex-col gap-3 p-4">
        {mensagens.length === 0 && (
          <p className="text-sm text-gray-500">
            Pergunte sobre suas propostas ou peça um tutorial do TransfereGov.
          </p>
        )}
        {mensagens.map((m, i) => (
          <div
            key={i}
            className={`animate-fade-up max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm backdrop-blur-md ${
              m.autor === "user"
                ? "self-end bg-gradient-to-br from-indigo-500/90 to-violet-500/90 text-white shadow-[0_4px_18px_rgba(99,102,241,.35)]"
                : "self-start border border-white/10 bg-white/6 text-gray-200 shadow-[inset_0_1px_0_rgba(255,255,255,.08)]"
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
          className="flex-1 input-glass px-3.5 py-2.5"
        />
        <button
          type="submit"
          disabled={ocupado}
          className="btn-primary px-5 py-2.5"
        >
          {ocupado ? "…" : "Enviar"}
        </button>
      </form>
    </>
  );
}
