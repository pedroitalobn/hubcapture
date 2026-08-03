"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { Aviso, Button, Field, Input } from "@/components/ui";
import { login } from "@/lib/api/client";

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
      router.push("/painel");
    } catch {
      setErro("E-mail ou senha incorretos.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <AuthShell titulo="Entrar" descricao="Acesse o painel do seu território.">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="E-mail">
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Senha">
          <Input
            type="password"
            required
            autoComplete="current-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
        </Field>
        {erro && <Aviso tom="erro">{erro}</Aviso>}
        <Button type="submit" disabled={carregando}>
          {carregando ? "Entrando…" : "Entrar"}
        </Button>
      </form>

      <div className="flex items-center justify-between text-sm">
        <Link href="/cadastro" className="text-brand underline underline-offset-2">
          Criar conta
        </Link>
        <Link href="/esqueci-senha" className="text-muted underline underline-offset-2">
          Esqueci a senha
        </Link>
      </div>
    </AuthShell>
  );
}
