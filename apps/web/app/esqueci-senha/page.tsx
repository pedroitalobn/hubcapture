"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthShell } from "@/components/AuthShell";
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
    <AuthShell
      title="Recuperar senha"
      subtitle="Enviamos um link de redefinição para o seu e-mail."
      footer={
        <Link href="/login" className="hover:text-ink">
          ← Voltar para o login
        </Link>
      }
    >
      {enviado ? (
        <div className="card p-5 text-sm leading-relaxed">
          <p>
            Se existir uma conta com <b>{email}</b>, enviamos um link para
            redefinir a senha. Confira sua caixa de entrada.
          </p>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">E-mail da conta</span>
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
          <button type="submit" disabled={carregando} className="btn btn-primary mt-2">
            {carregando ? "Enviando…" : "Enviar link de recuperação"}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
