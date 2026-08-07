"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api, getToken } from "@/lib/api/client";

/** Provedor embutido no `state` assinado pela API (campo "p"). */
function provedorDoState(state: string | null): string | null {
  if (!state) return null;
  const dados = state.split(".")[0] ?? "";
  try {
    const json = atob(dados.replace(/-/g, "+").replace(/_/g, "/"));
    return (JSON.parse(json) as { p?: string }).p ?? null;
  } catch {
    return null;
  }
}

function Callback() {
  const router = useRouter();
  const params = useSearchParams();
  const [erro, setErro] = useState<string | null>(null);
  const processado = useRef(false); // StrictMode monta 2x; o `code` só serve 1x

  useEffect(() => {
    if (processado.current) return;
    processado.current = true;

    const code = params.get("code");
    const state = params.get("state");
    const recusado = params.get("error");
    const provedor = provedorDoState(state);

    if (!getToken()) {
      router.replace("/login");
      return;
    }
    if (recusado || !code || !provedor) {
      const motivo = recusado ?? "autorização incompleta";
      router.replace(`/panel/contacts?erro=${encodeURIComponent(motivo)}`);
      return;
    }

    void (async () => {
      const { data, error } = await api.POST("/api/v1/integrations/contacts/callback", {
        body: {
          provedor,
          code,
          state,
          direcao: "bidirecional",
        },
      });
      if (error || !data) {
        const detalhe =
          (error as { detail?: string } | undefined)?.detail ?? "falha na conexão";
        setErro(detalhe);
        setTimeout(
          () => router.replace(`/panel/contacts?erro=${encodeURIComponent(detalhe)}`),
          2500,
        );
        return;
      }
      const conta = (data as { conta: string }).conta;
      router.replace(`/panel/contacts?conectado=${encodeURIComponent(conta)}`);
    })();
  }, [params, router]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-3 px-4 text-center">
      <h1 className="text-xl font-bold">Conectando sua agenda…</h1>
      <p className="text-sm text-ink-3">
        {erro ?? "Só um instante — estamos finalizando a autorização."}
      </p>
    </main>
  );
}

export default function CallbackPage() {
  return (
    <Suspense fallback={<main className="p-8 text-sm text-ink-3">Carregando…</main>}>
      <Callback />
    </Suspense>
  );
}
