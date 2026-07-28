"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/AuthShell";
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
      subtitle="Comece a acompanhar o ciclo do recurso público do seu município."
      footer={
        <span>
          Já tem conta?{" "}
          <Link href="/login" className="text-ink underline hover:no-underline">
            Entrar
          </Link>
        </span>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Nome</span>
          <input
            value={nome}
            autoComplete="name"
            onChange={(e) => setNome(e.target.value)}
            className="input"
            placeholder="Seu nome"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">E-mail</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
            placeholder="voce@exemplo.gov.br"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Senha</span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="input"
            placeholder="Mínimo de 8 caracteres"
          />
        </label>
        {erro && <p className="text-sm text-red-500">{erro}</p>}
        <button type="submit" disabled={carregando} className="btn btn-primary mt-2">
          {carregando ? "Criando…" : "Criar conta"}
        </button>
      </form>
    </AuthShell>
  );
}
