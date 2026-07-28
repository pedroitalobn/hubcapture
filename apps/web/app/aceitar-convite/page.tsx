"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { api, login } from "@/lib/api/client";

/**
 * Aceite de convite (página pública). O admin convida por e-mail já com papel e
 * plano; o convidado só escolhe nome e senha aqui. Depois do aceite, autentica
 * e cai no onboarding conversacional (o perfil ainda não tem território).
 */

function AceitarForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      const { data, error } = await api.POST("/api/v1/auth/aceitar-convite", {
        body: { token, senha, nome: nome || null },
      });
      if (error || !data) {
        throw new Error("Convite inválido, expirado ou já utilizado.");
      }
      const email = (data as { email: string }).email;
      await login(email, senha);
      router.push("/onboarding");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao aceitar o convite");
    } finally {
      setCarregando(false);
    }
  }

  if (!token) {
    return (
      <p className="text-sm text-red-500">
        Link de convite inválido. Peça um novo convite ao administrador ou{" "}
        <Link href="/cadastro" className="underline">
          crie uma conta
        </Link>
        .
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="field-label">Seu nome</span>
        <input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          autoComplete="name"
          className="input"
          placeholder="Como quer ser chamado"
        />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="field-label">Crie uma senha</span>
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
        {carregando ? "Entrando…" : "Aceitar convite e entrar"}
      </button>
    </form>
  );
}

export default function AceitarConvitePage() {
  return (
    <AuthShell
      title="Você foi convidado"
      subtitle="Crie sua senha para ativar a conta — papel e plano já vêm definidos pelo convite."
    >
      <Suspense fallback={<p className="text-sm text-ink-3">Carregando…</p>}>
        <AceitarForm />
      </Suspense>
    </AuthShell>
  );
}
