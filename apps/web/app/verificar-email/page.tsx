"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
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
    return <p className="text-sm text-gray-500">Confirmando seu e-mail…</p>;
  if (estado === "ok")
    return (
      <div className="text-sm">
        <p className="text-green-400">E-mail confirmado! Sua conta está ativa.</p>
        <Link href="/login" className="mt-3 inline-block text-brand underline">
          Entrar
        </Link>
      </div>
    );
  return (
    <div className="text-sm">
      <p className="text-red-400">Link inválido ou expirado.</p>
      <Link href="/login" className="mt-3 inline-block text-brand underline">
        Voltar para o login
      </Link>
    </div>
  );
}

export default function VerificarEmailPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
      <div className="glass-card animate-fade-up flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-gradient text-2xl font-bold">Confirmar e-mail</h1>
        <p className="text-sm text-gray-500">Hub Capture</p>
      </div>
      <Suspense fallback={<p className="text-sm text-gray-500">Carregando…</p>}>
        <VerificarConteudo />
      </Suspense>
      </div>
    </main>
  );
}
