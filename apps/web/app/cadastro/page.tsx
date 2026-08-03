"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { Aviso, Button, Field, Input } from "@/components/ui";
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
      setErro(err instanceof Error ? err.message : "Não foi possível criar a conta.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <AuthShell
      titulo="Criar conta"
      descricao="Depois do cadastro você escolhe o território que quer acompanhar."
      rodape={
        <>
          Já tem conta?{" "}
          <Link href="/login" className="text-brand underline underline-offset-2">
            Entrar
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Nome">
          <Input value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="name" />
        </Field>
        <Field label="E-mail">
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Senha" hint="Mínimo de 8 caracteres.">
          <Input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
        </Field>
        {erro && <Aviso tom="erro">{erro}</Aviso>}
        <Button type="submit" disabled={carregando}>
          {carregando ? "Criando…" : "Criar conta"}
        </Button>
      </form>
    </AuthShell>
  );
}
