"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
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
      <p className="text-sm text-red-400">
        Link inválido. Solicite um novo em{" "}
        <Link href="/esqueci-senha" className="underline">
          recuperar senha
        </Link>
        .
      </p>
    );
  }

  if (ok) {
    return (
      <p className="text-sm text-green-400">
        Senha redefinida! Redirecionando para o login…
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        Nova senha
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
        {carregando ? "Salvando…" : "Redefinir senha"}
      </button>
    </form>
  );
}

export default function RedefinirSenhaPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
      <div className="glass-card animate-fade-up flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-gradient text-2xl font-bold">Redefinir senha</h1>
        <p className="text-sm text-gray-500">Hub Capture</p>
      </div>
      <Suspense fallback={<p className="text-sm text-gray-500">Carregando…</p>}>
        <RedefinirForm />
      </Suspense>
      </div>
    </main>
  );
}
