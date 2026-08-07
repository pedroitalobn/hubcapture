"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken, excluirUsuario } from "@/lib/api/client";

interface Usuario {
  id: string;
  email: string;
  nome?: string | null;
  papel?: string | null;
  plano_id?: string | null;
  is_superuser: boolean;
  is_active: boolean;
  is_verified: boolean;
}
interface Plano {
  id: string;
  nome: string;
}

const PAPEIS = ["parlamentar", "executivo", "equipe"] as const;

export default function AdminUsuariosPage() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  // form de criação
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState<string>("");
  const [planoId, setPlanoId] = useState<string>("");
  const [superuser, setSuperuser] = useState(false);

  const carregar = useCallback(async () => {
    const [u, p] = await Promise.all([
      api.GET("/api/v1/admin/users", {}),
      api.GET("/api/v1/plans", {}),
    ]);
    if (!u.error) setUsuarios((u.data as Usuario[]) ?? []);
    if (!p.error) setPlanos((p.data as Plano[]) ?? []);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (!getToken()) {
      setMsg("Faça login como administrador.");
      return;
    }
    const { error } = await api.POST("/api/v1/admin/users", {
      body: {
        email,
        senha,
        nome: nome || null,
        papel,
        plano_id: planoId || null,
        is_superuser: superuser,
      },
    });
    if (error) {
      setMsg("Não foi possível criar (e-mail já existe? permissão?).");
      return;
    }
    setEmail("");
    setNome("");
    setSenha("");
    setPapel("");
    setPlanoId("");
    setSuperuser(false);
    setMsg("Usuário criado.");
    await carregar();
  }

  async function atualizar(
    id: string,
    patch: { papel?: string; is_superuser?: boolean; is_active?: boolean; plano_id?: string | null },
  ) {
    const { error } = await api.PATCH("/api/v1/admin/users/{usuario_id}", {
      params: { path: { usuario_id: id } },
      body: patch,
    });
    if (error) setMsg("Falha ao atualizar.");
    await carregar();
  }

  async function remover(id: string, email: string) {
    if (
      !window.confirm(
        `Excluir o usuário ${email}?\n\nApaga também favoritos, monitoramentos, ` +
          "pastas e alertas dele. Não dá para desfazer.",
      )
    )
      return;
    try {
      await excluirUsuario(id);
      await carregar();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Falha ao excluir usuário.");
    }
  }

  return (
    <>
      <header>
        <h1 className="page-title">Usuários & permissões</h1>
        <p className="mt-1 text-sm text-ink-2">
          Crie usuários, defina papel (role), atribua plano e conceda permissão
          de admin.
        </p>
      </header>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <form onSubmit={criar} className="card grid grid-cols-1 gap-4 p-6 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">E-mail</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Nome</span>
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Senha (mín. 8)</span>
          <input
            type="password"
            required
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Papel (opcional)</span>
          <select
            value={papel}
            onChange={(e) => setPapel(e.target.value)}
            className="input"
          >
            <option value="">— sem papel —</option>
            {PAPEIS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Plano</span>
          <select
            value={planoId}
            onChange={(e) => setPlanoId(e.target.value)}
            className="input"
          >
            <option value="">— sem plano —</option>
            {planos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 self-end text-sm text-ink-2">
          <input
            type="checkbox"
            checked={superuser}
            onChange={(e) => setSuperuser(e.target.checked)}
            className="accent-brand"
          />
          Permissão de admin (superuser)
        </label>
        <button type="submit" className="btn btn-primary col-span-full self-start">
          Criar usuário
        </button>
      </form>

      <section className="card overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-hairline text-left label-mono">
              <th className="px-5 py-3">Usuário</th>
              <th className="px-3 py-3">Papel</th>
              <th className="px-3 py-3">Plano</th>
              <th className="px-3 py-3">Admin</th>
              <th className="px-3 py-3">Ativo</th>
              <th className="px-3 py-3"></th>
              <th className="px-3 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr
                key={u.id}
                className="border-b border-hairline last:border-0 hover:bg-surface-2"
              >
                <td className="px-5 py-3">
                  <span className="block tracking-tight">
                    {u.nome ?? "—"}
                  </span>
                  <span className="text-xs text-ink-3">{u.email}</span>
                </td>
                <td className="px-3 py-3">
                  <select
                    value={u.papel ?? ""}
                    onChange={(e) => atualizar(u.id, { papel: e.target.value })}
                    className="input w-auto px-2 py-1 text-xs"
                  >
                    <option value="">—</option>
                    {PAPEIS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-3">
                  <select
                    value={u.plano_id ?? ""}
                    onChange={(e) =>
                      atualizar(u.id, { plano_id: e.target.value || null })
                    }
                    className="input w-auto px-2 py-1 text-xs"
                  >
                    <option value="">— sem plano —</option>
                    {planos.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.nome}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-3">
                  <button
                    onClick={() => atualizar(u.id, { is_superuser: !u.is_superuser })}
                    title="Alternar permissão de admin"
                  >
                    <StatusBadge tone={u.is_superuser ? "success" : "neutral"}>
                      {u.is_superuser ? "admin" : "não"}
                    </StatusBadge>
                  </button>
                </td>
                <td className="px-3 py-3">
                  <button
                    onClick={() => atualizar(u.id, { is_active: !u.is_active })}
                    title="Ativar/desativar"
                  >
                    <StatusBadge tone={u.is_active ? "success" : "danger"}>
                      {u.is_active ? "ativo" : "inativo"}
                    </StatusBadge>
                  </button>
                </td>
                <td className="px-3 py-3 text-xs text-ink-3">
                  {u.is_verified ? "verificado" : "—"}
                </td>
                <td className="px-3 py-3">
                  <button
                    onClick={() => void remover(u.id, u.email)}
                    className="text-xs text-danger hover:underline"
                    title="Excluir usuário"
                  >
                    excluir
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
