"use client";

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
    return <p className="text-sm text-ink-3">Confirmando seu e-mail…</p>;
  if (estado === "ok")
    return (
      <div className="card p-5 text-sm">
        <p className="text-ok">E-mail confirmado! Sua conta está ativa.</p>
        <Link href="/login" className="btn btn-primary btn-sm mt-4">
          Entrar
        </Link>
      </div>
    );
  return (
    <div className="card p-5 text-sm">
      <p className="text-danger">Link inválido ou expirado.</p>
      <Link href="/login" className="btn btn-ghost btn-sm mt-4">
        Voltar para o login
      </Link>
    </div>
  );
}

export default function VerificarEmailPage() {
  return (
    <AuthShell title="Confirmar e-mail" subtitle="Validando o seu link de confirmação.">
      <Suspense fallback={<p className="text-sm text-ink-3">Carregando…</p>}>
        <VerificarConteudo />
      </Suspense>
    </AuthShell>
  );
}
