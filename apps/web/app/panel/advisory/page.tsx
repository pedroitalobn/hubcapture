"use client";

import { useEffect, useState } from "react";
import { ModuloGate } from "@/components/ModuloGate";
import { SkeletonCards } from "@/components/Skeleton";
import { api } from "@/lib/api/client";

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
    </>
  );
}

export default function AssessoriaPage() {
  return (
    <ModuloGate modulo="assessoria" titulo="Assessoria">
      <ListaContatos />
    </ModuloGate>
  );
}
