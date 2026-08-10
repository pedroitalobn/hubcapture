"use client";

import { ShieldCheck, UserRoundPlus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { Callout } from "@/components/Callout";
import { PageHeader } from "@/components/PageHeader";
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

const INPUT =
  "rounded-lg border border-gray-300 bg-white px-3 py-2 transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-950";

export default function AdminUsuariosPage() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; texto: string } | null>(
    null,
  );

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
      setMsg({ tone: "error", texto: "Faça login como administrador." });
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
      setMsg({
        tone: "error",
        texto: "Não foi possível criar (e-mail já existe? permissão?).",
      });
      return;
    }
    setEmail("");
    setNome("");
    setSenha("");
    setPapel("equipe");
    setPlanoId("");
    setSuperuser(false);
    setMsg({ tone: "success", texto: "Usuário criado." });
    await carregar();
  }

  async function atualizar(id: string, patch: Partial<Usuario>) {
    const { error } = await api.PATCH("/api/v1/admin/usuarios/{usuario_id}", {
      params: { path: { usuario_id: id } },
      body: patch,
    });
    if (error) setMsg({ tone: "error", texto: "Falha ao atualizar." });
    await carregar();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-6 py-8">
      <PageHeader
        icon={Users}
        title="Usuários & permissões"
        subtitle="Crie usuários, defina o papel (role) e conceda permissão de admin."
      />

      {msg && <Callout tone={msg.tone}>{msg.texto}</Callout>}

      <form
        onSubmit={criar}
        className="grid grid-cols-1 gap-4 rounded-xl border border-gray-200 bg-white p-5 shadow-card animate-fade-up sm:grid-cols-2 dark:border-gray-800 dark:bg-gray-900"
      >
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          E-mail
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Nome
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Senha (mín. 8)
          <input
            type="password"
            required
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Papel (role)
          <select
            value={papel}
            onChange={(e) => setPapel(e.target.value)}
            className={INPUT}
          >
            {PAPEIS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Plano
          <select
            value={planoId}
            onChange={(e) => setPlanoId(e.target.value)}
            className={INPUT}
          >
            <option value="">— sem plano —</option>
            {planos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </label>
        <label className="flex cursor-pointer items-center gap-2.5 self-end rounded-lg border border-gray-200 px-3 py-2.5 text-sm transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50">
          <input
            type="checkbox"
            checked={superuser}
            onChange={(e) => setSuperuser(e.target.checked)}
            className="h-4 w-4 accent-[var(--color-brand-600)]"
          />
          <ShieldCheck className="h-4 w-4 text-gray-400" aria-hidden />
          Permissão de admin (superuser)
        </label>
        <Button
          type="submit"
          icon={<UserRoundPlus className="h-4 w-4" aria-hidden />}
          className="col-span-full self-start"
        >
          Criar usuário
        </Button>
      </form>

      <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50/70 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:bg-gray-950/40">
                <th className="px-4 py-3">Usuário</th>
                <th className="px-4 py-3">Papel</th>
                <th className="px-4 py-3">Admin</th>
                <th className="px-4 py-3">Ativo</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {usuarios.map((u) => (
                <tr
                  key={u.id}
                  className="transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
                >
                  <td className="px-4 py-3">
                    <span className="block font-medium">{u.nome ?? "—"}</span>
                    <span className="text-xs text-gray-400">{u.email}</span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={u.papel ?? ""}
                      onChange={(e) => atualizar(u.id, { papel: e.target.value })}
                      className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-xs transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-950"
                    >
                      <option value="">—</option>
                      {PAPEIS.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => atualizar(u.id, { is_superuser: !u.is_superuser })}
                      title="Alternar permissão de admin"
                      className="transition-transform active:scale-95"
                    >
                      <StatusBadge tone={u.is_superuser ? "success" : "neutral"}>
                        {u.is_superuser ? "admin" : "não"}
                      </StatusBadge>
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => atualizar(u.id, { is_active: !u.is_active })}
                      title="Ativar/desativar"
                      className="transition-transform active:scale-95"
                    >
                      <StatusBadge tone={u.is_active ? "success" : "danger"}>
                        {u.is_active ? "ativo" : "inativo"}
                      </StatusBadge>
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {u.is_verified ? "verificado" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
