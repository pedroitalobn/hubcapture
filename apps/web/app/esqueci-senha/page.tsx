"use client";

import { ArrowLeft, Mail, MailCheck, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AUTH_INPUT, AuthShell } from "@/components/AuthShell";
import { Button } from "@/components/Button";
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
      subtitle="Enviaremos um link de redefinição para o seu e-mail."
    >
      {enviado ? (
        <div className="flex flex-col items-center gap-3 text-center animate-scale-in">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-green-50 text-green-600 dark:bg-green-900/40 dark:text-green-400">
            <MailCheck className="h-6 w-6" aria-hidden />
          </span>
          <p className="text-sm">
            Se existir uma conta com <b>{email}</b>, enviamos um link para
            redefinir a senha. Confira sua caixa de entrada.
          </p>
          <Link
            href="/login"
            className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline dark:text-brand-400"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Voltar para o login
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            E-mail da conta
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
          <Button
            type="submit"
            loading={carregando}
            icon={<Send className="h-4 w-4" aria-hidden />}
          >
            {carregando ? "Enviando…" : "Enviar link de recuperação"}
          </Button>
          <Link
            href="/login"
            className="inline-flex items-center justify-center gap-1 text-sm text-gray-500 transition-colors hover:text-brand-700 dark:hover:text-brand-400"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Voltar para o login
          </Link>
        </form>
      )}
    </AuthShell>
  );
}
