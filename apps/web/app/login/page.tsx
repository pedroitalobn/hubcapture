"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { api, login } from "@/lib/api/client";

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
      // Sem território configurado → a porta de entrada é o onboarding
      // conversacional (o perfil é o ponto de partida da navegação).
      const { data } = await api.GET("/api/v1/profile");
      const temTerritorio = ((data?.municipios as unknown[]) ?? []).length > 0;
      router.push(temTerritorio ? "/panel" : "/onboarding");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao entrar");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <AuthShell
      image
      title="Bem-vindo de volta"
      subtitle="Entre para acompanhar o seu território."
      footer={
        <div className="flex items-center justify-between">
          <span>
            Novo por aqui?{" "}
            <Link href="/signup" className="text-ink underline hover:no-underline">
              Criar conta
            </Link>
          </span>
          <Link href="/forgot-password" className="hover:text-ink">
            Esqueci a senha
          </Link>
        </div>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
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
            autoComplete="current-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="input"
            placeholder="••••••••"
          />
        </label>
        {erro && <p className="text-sm text-red-500">{erro}</p>}
        <button type="submit" disabled={carregando} className="btn btn-primary mt-2">
          {carregando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </AuthShell>
  );
}
