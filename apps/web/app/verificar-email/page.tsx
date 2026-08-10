"use client";

import { ArrowLeft, CircleCheck, CircleX, LoaderCircle, LogIn } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { verificarEmail } from "@/lib/api/client";

function VerificarConteudo() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [estado, setEstado] = useState<"loading" | "ok" | "erro">("loading");

  useEffect(() => {
    if (!token) {
      setEstado("erro");
      return;
    }
    void (async () => {
      try {
        await verificarEmail(token);
        setEstado("ok");
      } catch {
        setEstado("erro");
      }
    })();
  }, [token]);

  if (estado === "loading")
    return (
      <div className="flex items-center justify-center gap-2 py-4 text-sm text-gray-500">
        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
        Confirmando seu e-mail…
      </div>
    );

  if (estado === "ok")
    return (
      <div className="flex flex-col items-center gap-3 text-center animate-scale-in">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-green-50 text-green-600 dark:bg-green-900/40 dark:text-green-400">
          <CircleCheck className="h-6 w-6" aria-hidden />
        </span>
        <p className="text-sm">E-mail confirmado! Sua conta está ativa.</p>
        <Link
          href="/login"
          className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline dark:text-brand-400"
        >
          <LogIn className="h-4 w-4" aria-hidden />
          Entrar
        </Link>
      </div>
    );

  return (
    <div className="flex flex-col items-center gap-3 text-center animate-scale-in">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-red-50 text-red-600 dark:bg-red-900/40 dark:text-red-400">
        <CircleX className="h-6 w-6" aria-hidden />
      </span>
      <p className="text-sm">Link inválido ou expirado.</p>
      <Link
        href="/login"
        className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline dark:text-brand-400"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Voltar para o login
      </Link>
    </div>
  );
}

export default function VerificarEmailPage() {
  return (
    <AuthShell title="Confirmar e-mail" subtitle="Validando o seu link de confirmação.">
      <Suspense fallback={<p className="text-sm text-gray-500">Carregando…</p>}>
        <VerificarConteudo />
      </Suspense>
    </AuthShell>
  );
}
