"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Aviso, Button, Card, Field, Input } from "@/components/ui";
import { atualizarPerfil, meProfile } from "@/lib/api/client";

export default function ContaPage() {
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [optin, setOptin] = useState(false);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [aviso, setAviso] = useState<{ tom: "ok" | "erro"; texto: string } | null>(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const me = (await meProfile()) as {
          nome?: string | null;
          telefone_wpp?: string | null;
          optin_wpp?: boolean;
          email: string;
        };
        setNome(me.nome ?? "");
        setTelefone(me.telefone_wpp ?? "");
        setOptin(Boolean(me.optin_wpp));
        setEmail(me.email);
      } catch {
        /* o layout já trata sessão expirada */
      }
    })();
  }, []);

  async function salvarPerfil(e: React.FormEvent) {
    e.preventDefault();
    setAviso(null);
    setSalvando(true);
    try {
      await atualizarPerfil({ nome, telefone_wpp: telefone, optin_wpp: optin });
      setAviso({ tom: "ok", texto: "Perfil atualizado." });
    } catch (err) {
      setAviso({
        tom: "erro",
        texto: err instanceof Error ? err.message : "Não foi possível salvar.",
      });
    } finally {
      setSalvando(false);
    }
  }

  async function trocarSenha(e: React.FormEvent) {
    e.preventDefault();
    setAviso(null);
    if (senha.length < 8) {
      setAviso({ tom: "erro", texto: "A senha precisa ter ao menos 8 caracteres." });
      return;
    }
    setSalvando(true);
    try {
      await atualizarPerfil({ password: senha });
      setSenha("");
      setAviso({ tom: "ok", texto: "Senha alterada." });
    } catch (err) {
      setAviso({
        tom: "erro",
        texto: err instanceof Error ? err.message : "Não foi possível alterar a senha.",
      });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <PageHeader titulo="Minha conta" descricao={email} />

      {aviso && <Aviso tom={aviso.tom}>{aviso.texto}</Aviso>}

      <Card className="max-w-lg p-5">
        <form onSubmit={salvarPerfil} className="flex flex-col gap-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Perfil
          </h2>
          <Field label="Nome">
            <Input value={nome} onChange={(e) => setNome(e.target.value)} />
          </Field>
          <Field label="Telefone (WhatsApp)" hint="Use o formato internacional, com DDI.">
            <Input
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="+5511999999999"
              inputMode="tel"
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-ink-2">
            <input
              type="checkbox"
              checked={optin}
              onChange={(e) => setOptin(e.target.checked)}
              className="accent-brand"
            />
            Receber alertas por WhatsApp
          </label>
          <Button type="submit" disabled={salvando} className="self-start">
            Salvar perfil
          </Button>
        </form>
      </Card>

      <Card className="max-w-lg p-5">
        <form onSubmit={trocarSenha} className="flex flex-col gap-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Trocar senha
          </h2>
          <Field label="Nova senha" hint="Mínimo de 8 caracteres.">
            <Input
              type="password"
              minLength={8}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              autoComplete="new-password"
            />
          </Field>
          <Button type="submit" disabled={salvando || !senha} className="self-start">
            Alterar senha
          </Button>
        </form>
      </Card>
    </>
  );
}
