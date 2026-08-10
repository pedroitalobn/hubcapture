"use client";

import { Lock, Mail, UserRound, UserRoundPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AUTH_INPUT, AuthShell } from "@/components/AuthShell";
import { Button } from "@/components/Button";
import { Callout } from "@/components/Callout";
import { registrar } from "@/lib/api/client";

export default function CadastroPage() {
  const router = useRouter();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      await registrar(email, senha, nome || undefined);
      router.push("/onboarding");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao criar conta");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <AuthShell
      title="Criar conta"
      subtitle="Comece a acompanhar o seu território em minutos."
      footer={
        <p>
          Já tem conta?{" "}
          <Link
            href="/login"
            className="font-medium text-brand-700 hover:underline dark:text-brand-400"
          >
            Entrar
          </Link>
        </p>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Nome
          <span className="relative">
            <UserRound
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              aria-hidden
            />
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              className={AUTH_INPUT}
            />
          </span>
        </label>
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
          icon={<UserRoundPlus className="h-4 w-4" aria-hidden />}
        >
          {carregando ? "Criando…" : "Criar conta"}
        </Button>
      </form>
    </AuthShell>
  );
}
