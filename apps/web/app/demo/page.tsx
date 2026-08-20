"use client";

/**
 * /demo — o link compartilhável do acesso de DEMONSTRAÇÃO.
 *
 * É a porta de vendas: quem recebe o link cai direto no painel, logado na
 * conta demo (sandbox sobre dados reais do cache; escrita destrutiva
 * bloqueada no backend). Sem tela intermediária — a página só mostra estado
 * enquanto autentica e redireciona.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { entrarDemo } from "@/lib/api/client";

export default function DemoPage() {
  const router = useRouter();
  const [erro, setErro] = useState<string | null>(null);
  // StrictMode monta o effect duas vezes em dev — sem a trava, dois logins
  const emCurso = useRef(false);

  useEffect(() => {
    if (emCurso.current) return;
    emCurso.current = true;
    void (async () => {
      try {
        await entrarDemo();
        router.replace("/panel");
      } catch (e) {
        setErro(
          e instanceof Error ? e.message : "A demonstração está indisponível",
        );
      }
    })();
  }, [router]);

  return (
    <AuthShell
      title="Demonstração"
      subtitle={
        erro ??
        "Preparando o ambiente de demonstração com dados reais de captação…"
      }
      footer={
        <span>
          Já tem conta?{" "}
          <Link href="/login" className="text-ink underline hover:no-underline">
            Entrar
          </Link>
        </span>
      }
    >
      {erro ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-danger">{erro}</p>
          <Link href="/login" className="btn btn-primary">
            Ir para o login
          </Link>
        </div>
      ) : (
        <p className="text-sm text-ink-2">Entrando…</p>
      )}
    </AuthShell>
  );
}
