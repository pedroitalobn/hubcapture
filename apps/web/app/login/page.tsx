"use client";

import { LogIn, Lock, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AUTH_INPUT, AuthShell } from "@/components/AuthShell";
import { Button } from "@/components/Button";
import { Callout } from "@/components/Callout";
import { login } from "@/lib/api/client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      await login(email, senha);
      router.push("/painel");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao entrar");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <AuthShell
      title="Entrar"
      subtitle="Acesse o painel do seu território."
      footer={
        <p>
          Ainda não tem conta?{" "}
          <Link
            href="/cadastro"
            className="font-medium text-brand-700 hover:underline dark:text-brand-400"
          >
            Criar conta
          </Link>
        </p>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          E-mail
          <span className="relative">
            <Mail
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              aria-hidden
            />
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={AUTH_INPUT}
            />
          </span>
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Senha
          <span className="relative">
            <Lock
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              aria-hidden
            />
            <input
              type="password"
              required
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
          icon={<LogIn className="h-4 w-4" aria-hidden />}
        >
          {carregando ? "Entrando…" : "Entrar"}
        </Button>
        <Link
          href="/esqueci-senha"
          className="text-center text-sm text-gray-500 transition-colors hover:text-brand-700 dark:hover:text-brand-400"
        >
          Esqueci a senha
        </Link>
      </form>
    </AuthShell>
  );
}
