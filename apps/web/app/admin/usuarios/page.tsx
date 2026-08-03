"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken } from "@/lib/api/client";

interface Usuario {
  id: string;
  email: string;
  nome?: string | null;
  papel?: string | null;
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
  const [papel, setPapel] = useState<string>("equipe");
  const [planoId, setPlanoId] = useState<string>("");
  const [superuser, setSuperuser] = useState(false);

  const carregar = useCallback(async () => {
    const [u, p] = await Promise.all([
      api.GET("/api/v1/admin/usuarios", {}),
      api.GET("/api/v1/planos", {}),
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
    const { error } = await api.POST("/api/v1/admin/usuarios", {
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
    setPapel("equipe");
    setPlanoId("");
    setSuperuser(false);
    setMsg("Usuário criado.");
    await carregar();
  }

  async function atualizar(id: string, patch: Partial<Usuario>) {
    const { error } = await api.PATCH("/api/v1/admin/usuarios/{usuario_id}", {
      params: { path: { usuario_id: id } },
      body: patch,
    });
    if (error) setMsg("Falha ao atualizar.");
    await carregar();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-8 px-6 py-8">
      <header>
        <h1 className="text-2xl font-bold">Usuários & permissões</h1>
        <p className="text-sm text-muted">
          Crie usuários, defina o papel (role) e conceda permissão de admin.
        </p>
      </header>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <form
        onSubmit={criar}
        className="grid grid-cols-1 gap-3 rounded-lg border border-line p-4 sm:grid-cols-2"
      >
        <label className="flex flex-col gap-1 text-sm">
          E-mail
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-md border border-line px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Nome
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="rounded-md border border-line px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Senha (mín. 8)
          <input
            type="password"
            required
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="rounded-md border border-line px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Papel (role)
          <select
            value={papel}
            onChange={(e) => setPapel(e.target.value)}
            className="rounded-md border border-line px-3 py-2"
          >
            {PAPEIS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Plano
          <select
            value={planoId}
            onChange={(e) => setPlanoId(e.target.value)}
            className="rounded-md border border-line px-3 py-2"
          >
            <option value="">— sem plano —</option>
            {planos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 self-end text-sm">
          <input
            type="checkbox"
            checked={superuser}
            onChange={(e) => setSuperuser(e.target.checked)}
          />
          Permissão de admin (superuser)
        </label>
        <button
          type="submit"
          className="col-span-full self-start rounded-md bg-brand px-4 py-2 text-brand-fg"
        >
          Criar usuário
        </button>
      </form>

      <section className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              <th className="py-2 pr-4">Usuário</th>
              <th className="py-2 pr-4">Papel</th>
              <th className="py-2 pr-4">Admin</th>
              <th className="py-2 pr-4">Ativo</th>
              <th className="py-2 pr-4"></th>
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.id} className="border-b border-line">
                <td className="py-2 pr-4">
                  <span className="block">{u.nome ?? "—"}</span>
                  <span className="text-xs text-muted">{u.email}</span>
                </td>
                <td className="py-2 pr-4">
                  <select
                    value={u.papel ?? ""}
                    onChange={(e) => atualizar(u.id, { papel: e.target.value })}
                    className="rounded-md border border-line px-2 py-1 text-xs"
                  >
                    <option value="">—</option>
                    {PAPEIS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pr-4">
                  <button
                    onClick={() => atualizar(u.id, { is_superuser: !u.is_superuser })}
                    title="Alternar permissão de admin"
                  >
                    <StatusBadge tone={u.is_superuser ? "success" : "neutral"}>
                      {u.is_superuser ? "admin" : "não"}
                    </StatusBadge>
                  </button>
                </td>
                <td className="py-2 pr-4">
                  <button
                    onClick={() => atualizar(u.id, { is_active: !u.is_active })}
                    title="Ativar/desativar"
                  >
                    <StatusBadge tone={u.is_active ? "success" : "danger"}>
                      {u.is_active ? "ativo" : "inativo"}
                    </StatusBadge>
                  </button>
                </td>
                <td className="py-2 pr-4 text-xs text-muted">
                  {u.is_verified ? "verificado" : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
