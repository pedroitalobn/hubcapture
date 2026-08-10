"use client";

import { BellRing, KeyRound, Phone, Save, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { Callout } from "@/components/Callout";
import { PageHeader } from "@/components/PageHeader";
import { atualizarPerfil, meProfile } from "@/lib/api/client";

const INPUT =
  "rounded-lg border border-gray-300 bg-white px-3 py-2 transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-950";

export default function ContaPage() {
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [optin, setOptin] = useState(false);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [msg, setMsg] = useState<{ tone: "success" | "error"; texto: string } | null>(
    null,
  );
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
        /* layout já trata sessão */
      }
    })();
  }, []);

  async function salvarPerfil(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSalvando(true);
    try {
      await atualizarPerfil({
        nome,
        telefone_wpp: telefone,
        optin_wpp: optin,
      });
      setMsg({ tone: "success", texto: "Perfil atualizado." });
    } catch (err) {
      setMsg({
        tone: "error",
        texto: err instanceof Error ? err.message : "Erro ao salvar",
      });
    } finally {
      setSalvando(false);
    }
  }

  async function trocarSenha(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (senha.length < 8) {
      setMsg({ tone: "error", texto: "A senha precisa ter ao menos 8 caracteres." });
      return;
    }
    setSalvando(true);
    try {
      await atualizarPerfil({ password: senha });
      setSenha("");
      setMsg({ tone: "success", texto: "Senha alterada." });
    } catch (err) {
      setMsg({
        tone: "error",
        texto: err instanceof Error ? err.message : "Erro ao alterar senha",
      });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <PageHeader icon={UserRound} title="Minha conta" subtitle={email} />

      {msg && <Callout tone={msg.tone}>{msg.texto}</Callout>}

      <form
        onSubmit={salvarPerfil}
        className="flex max-w-md flex-col gap-4 rounded-xl border border-gray-200 bg-white p-5 shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900"
      >
        <h2 className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
          <UserRound className="h-4 w-4" aria-hidden />
          Perfil
        </h2>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Nome
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Telefone (WhatsApp)
          <span className="relative">
            <Phone
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              aria-hidden
            />
            <input
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="+5511999999999"
              className={`${INPUT} w-full pl-9`}
            />
          </span>
        </label>
        <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-gray-200 px-3 py-2.5 text-sm transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50">
          <input
            type="checkbox"
            checked={optin}
            onChange={(e) => setOptin(e.target.checked)}
            className="h-4 w-4 accent-[var(--color-brand-600)]"
          />
          <BellRing className="h-4 w-4 text-gray-400" aria-hidden />
          Receber alertas por WhatsApp
        </label>
        <Button
          type="submit"
          loading={salvando}
          icon={<Save className="h-4 w-4" aria-hidden />}
          className="self-start"
        >
          Salvar perfil
        </Button>
      </form>

      <form
        onSubmit={trocarSenha}
        className="flex max-w-md flex-col gap-4 rounded-xl border border-gray-200 bg-white p-5 shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900"
      >
        <h2 className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
          <KeyRound className="h-4 w-4" aria-hidden />
          Trocar senha
        </h2>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Nova senha
          <input
            type="password"
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className={INPUT}
          />
        </label>
        <Button
          type="submit"
          loading={salvando}
          disabled={!senha}
          icon={<KeyRound className="h-4 w-4" aria-hidden />}
          className="self-start"
        >
          Alterar senha
        </Button>
      </form>
    </>
  );
}
