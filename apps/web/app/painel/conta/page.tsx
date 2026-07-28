"use client";

import { useEffect, useState } from "react";
import { atualizarPerfil, meProfile } from "@/lib/api/client";

export default function ContaPage() {
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [optin, setOptin] = useState(false);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
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
      setMsg("Perfil atualizado.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function trocarSenha(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (senha.length < 8) {
      setMsg("A senha precisa ter ao menos 8 caracteres.");
      return;
    }
    setSalvando(true);
    try {
      await atualizarPerfil({ password: senha });
      setSenha("");
      setMsg("Senha alterada.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Erro ao alterar senha");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <header>
        <h1 className="text-gradient text-2xl font-bold">Minha conta</h1>
        <p className="text-sm text-gray-500">{email}</p>
      </header>

      {msg && <p className="text-sm text-gray-600 dark:text-gray-400">{msg}</p>}

      <form onSubmit={salvarPerfil} className="flex max-w-md flex-col gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Perfil
        </h2>
        <label className="flex flex-col gap-1 text-sm">
          Nome
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Telefone (WhatsApp)
          <input
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
            placeholder="+5511999999999"
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={optin}
            onChange={(e) => setOptin(e.target.checked)}
          />
          Receber alertas por WhatsApp
        </label>
        <button
          type="submit"
          disabled={salvando}
          className="btn-primary self-start px-5 py-2.5"
        >
          Salvar perfil
        </button>
      </form>

      <form onSubmit={trocarSenha} className="flex max-w-md flex-col gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Trocar senha
        </h2>
        <label className="flex flex-col gap-1 text-sm">
          Nova senha
          <input
            type="password"
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        <button
          type="submit"
          disabled={salvando || !senha}
          className="btn-primary self-start px-5 py-2.5"
        >
          Alterar senha
        </button>
      </form>
    </>
  );
}
