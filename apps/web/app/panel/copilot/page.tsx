"use client";

import { useEffect, useRef, useState } from "react";
import { ChatBubble, TypingDots } from "@/components/Chat";
import { chatStream } from "@/lib/api/client";

type Msg = { autor: "user" | "ia"; texto: string };

export default function ChatPage() {
  const [modo, setModo] = useState<"propostas" | "copiloto">("propostas");
  const [pergunta, setPergunta] = useState("");
  const [mensagens, setMensagens] = useState<Msg[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
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
    setErro(null);
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
    } catch (err) {
      // O `finally` sozinho engolia a falha: a bolha ficava vazia e o usuário
      // não sabia se era credencial, plano ou rede (ponto 20 do feedback).
      const texto =
        err instanceof Error && err.message
          ? err.message
          : "Não consegui falar com o Copiloto agora. Tente novamente.";
      setErro(texto);
      setMensagens((m) => {
        const copia = [...m];
        // remove a bolha vazia que ficaria girando para sempre
        if (copia[copia.length - 1]?.texto === "") copia.pop();
        return copia;
      });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">Copiloto</h1>
        <div className="segmented">
          {(["propostas", "copiloto"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setModo(m)}
              className={`segmented-item ${modo === m ? "segmented-item-active" : ""}`}
            >
              {m === "propostas" ? "Minhas propostas" : "Tutoriais"}
            </button>
          ))}
        </div>
      </header>

      {erro && (
        <p role="status" className="text-sm tone-danger">
          {erro}
        </p>
      )}

      <div className="card flex min-h-[50vh] flex-col gap-3 p-5">
        {mensagens.length === 0 && (
          <p className="m-auto max-w-sm text-center text-sm text-ink-3">
            Pergunte sobre suas propostas ou peça um tutorial do TransfereGov.
          </p>
        )}
        {mensagens.map((m, i) =>
          m.autor === "ia" && !m.texto ? (
            <TypingDots key={i} />
          ) : (
            <ChatBubble key={i} autor={m.autor === "user" ? "user" : "ai"}>
              {m.texto}
            </ChatBubble>
          ),
        )}
        <div ref={fimRef} />
      </div>

      <form onSubmit={enviar} className="glass flex gap-2 rounded-full p-1.5">
        <input
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Sua pergunta…"
          className="flex-1 rounded-full bg-transparent px-4 text-sm text-ink outline-none placeholder:text-ink-3"
        />
        <button type="submit" disabled={ocupado} className="btn btn-primary btn-sm">
          {ocupado ? "…" : "Enviar"}
        </button>
      </form>
    </>
  );
}
