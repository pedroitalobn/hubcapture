"use client";

import { CircleCheck, KeyRound, Lock } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AUTH_INPUT, AuthShell } from "@/components/AuthShell";
import { Button } from "@/components/Button";
import { Callout } from "@/components/Callout";
import { redefinirSenha } from "@/lib/api/client";

function RedefinirForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [carregando, setCarregando] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      await redefinirSenha(token, senha);
      setOk(true);
      setTimeout(() => router.push("/login"), 1500);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao redefinir");
    } finally {
      setCarregando(false);
    }
  }

  if (!token) {
    return (
      <Callout tone="error">
        Link inválido. Solicite um novo em{" "}
        <Link href="/esqueci-senha" className="font-medium underline">
          recuperar senha
        </Link>
        .
      </Callout>
    );
  }

  if (ok) {
    return (
      <div className="flex flex-col items-center gap-3 text-center animate-scale-in">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-green-50 text-green-600 dark:bg-green-900/40 dark:text-green-400">
          <CircleCheck className="h-6 w-6" aria-hidden />
        </span>
        <p className="text-sm">Senha redefinida! Redirecionando para o login…</p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Nova senha
        <span className="relative">
          <Lock
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
            aria-hidden
          />
          <input
            type="password"
            required
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className={AUTH_INPUT}
          />
        </span>
      </label>
      {erro && <Callout tone="error">{erro}</Callout>}
      <Button
        type="submit"
        loading={carregando}
        icon={<KeyRound className="h-4 w-4" aria-hidden />}
      >
        {carregando ? "Salvando…" : "Redefinir senha"}
      </Button>
    </form>
  );
}

export default function RedefinirSenhaPage() {
  return (
    <AuthShell title="Redefinir senha" subtitle="Escolha uma nova senha para a sua conta.">
      <Suspense fallback={<p className="text-sm text-gray-500">Carregando…</p>}>
        <RedefinirForm />
      </Suspense>
    </AuthShell>
  );
}
