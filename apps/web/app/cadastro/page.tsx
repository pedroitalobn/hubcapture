"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
      <div className="glass-card animate-fade-up flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-gradient text-2xl font-bold">Criar conta</h1>
        <p className="text-sm text-gray-500">Hub Capture</p>
      </div>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          Nome
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          E-mail
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Senha
          <input
            type="password"
            required
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        {erro && <p className="text-sm text-red-400">{erro}</p>}
        <button
          type="submit"
          disabled={carregando}
          className="btn-primary px-5 py-2.5"
        >
          {carregando ? "Criando…" : "Criar conta"}
        </button>
      </form>
      <p className="text-sm text-gray-500">
        Já tem conta?{" "}
        <Link href="/login" className="text-brand underline">
          Entrar
        </Link>
      </p>
      </div>
    </main>
  );
}
