"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-6 px-6">
      <div className="glass-card animate-fade-up p-8">
        <div className="mb-6">
          <p className="mb-1 text-xs font-medium uppercase tracking-widest text-brand">
            Hub Capture
          </p>
          <h1 className="text-gradient text-3xl font-bold">Entrar</h1>
        </div>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm text-gray-300">
            E-mail
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-glass px-3.5 py-2.5"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm text-gray-300">
            Senha
            <input
              type="password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              className="input-glass px-3.5 py-2.5"
            />
          </label>
          {erro && <p className="text-sm text-red-400">{erro}</p>}
          <button
            type="submit"
            disabled={carregando}
            className="btn-primary mt-2 px-4 py-2.5"
          >
            {carregando ? "Entrando…" : "Entrar"}
          </button>
        </form>
        <div className="mt-6 flex items-center justify-between text-sm text-gray-400">
          <Link href="/cadastro" className="text-brand transition hover:brightness-125">
            Criar conta
          </Link>
          <Link href="/esqueci-senha" className="transition hover:text-gray-200">
            Esqueci a senha
          </Link>
        </div>
      </div>
    </main>
  );
}
