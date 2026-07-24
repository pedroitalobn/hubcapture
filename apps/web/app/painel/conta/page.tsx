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
        <h1 className="page-title">Minha conta</h1>
        <p className="mt-1 text-sm text-ink-2">{email}</p>
      </header>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <form onSubmit={salvarPerfil} className="card flex max-w-md flex-col gap-4 p-6">
        <h2 className="label-mono">
          Perfil
        </h2>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Nome</span>
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Telefone (WhatsApp)</span>
          <input
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
            placeholder="+5511999999999"
            className="input"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={optin}
            onChange={(e) => setOptin(e.target.checked)}
            className="accent-brand"
          />
          Receber alertas por WhatsApp
        </label>
        <button type="submit" disabled={salvando} className="btn btn-primary self-start">
          Salvar perfil
        </button>
      </form>

      <form onSubmit={trocarSenha} className="card flex max-w-md flex-col gap-4 p-6">
        <h2 className="label-mono">
          Trocar senha
        </h2>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Nova senha</span>
          <input
            type="password"
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="input"
          />
        </label>
        <button
          type="submit"
          disabled={salvando || !senha}
          className="btn btn-primary self-start"
        >
          Alterar senha
        </button>
      </form>
    </>
  );
}
