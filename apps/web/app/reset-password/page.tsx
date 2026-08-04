"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell } from "@/components/AuthShell";
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
      <p className="text-sm text-red-500">
        Link inválido. Solicite um novo em{" "}
        <Link href="/forgot-password" className="underline">
          recuperar senha
        </Link>
        .
      </p>
    );
  }

  if (ok) {
    return (
      <div className="card p-5 text-sm">
        <p className="text-green-500">Senha redefinida! Redirecionando para o login…</p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="field-label">Nova senha</span>
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
        {carregando ? "Salvando…" : "Redefinir senha"}
      </button>
    </form>
  );
}

export default function RedefinirSenhaPage() {
  return (
    <AuthShell title="Redefinir senha" subtitle="Escolha uma nova senha para a sua conta.">
      <Suspense fallback={<p className="text-sm text-ink-3">Carregando…</p>}>
        <RedefinirForm />
      </Suspense>
    </AuthShell>
  );
}
