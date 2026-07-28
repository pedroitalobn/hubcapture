"use client";

import Link from "next/link";
import { useState } from "react";
import { esqueciSenha } from "@/lib/api/client";

export default function EsqueciSenhaPage() {
  const [email, setEmail] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [carregando, setCarregando] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCarregando(true);
    await esqueciSenha(email);
    setEnviado(true);
    setCarregando(false);
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
      <div className="glass-card animate-fade-up flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-gradient text-2xl font-bold">Recuperar senha</h1>
        <p className="text-sm text-gray-500">Hub Capture</p>
      </div>
      {enviado ? (
        <div className="glass-card p-4 text-sm">
          <p>
            Se existir uma conta com <b>{email}</b>, enviamos um link para redefinir
            a senha. Confira sua caixa de entrada.
          </p>
          <Link href="/login" className="mt-3 inline-block text-brand underline">
            Voltar para o login
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            E-mail da conta
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-glass px-3.5 py-2.5"
            />
          </label>
          <button
            type="submit"
            disabled={carregando}
            className="btn-primary px-5 py-2.5"
          >
            {carregando ? "Enviando…" : "Enviar link de recuperação"}
          </button>
          <Link href="/login" className="text-sm text-gray-500 underline">
            Voltar para o login
          </Link>
        </form>
      )}
      </div>
    </main>
  );
}
