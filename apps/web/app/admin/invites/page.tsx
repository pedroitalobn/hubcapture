"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken, excluirConvite } from "@/lib/api/client";

interface Convite {
  id: string;
  email: string;
  token: string;
  papel?: string | null;
  plano_id?: string | null;
  status: string;
  expires_at?: string | null;
  created_at: string;
}
interface Plano {
  id: string;
  nome: string;
}

const PAPEIS = ["parlamentar", "executivo", "equipe"] as const;

function statusTone(s: string): "success" | "neutral" | "danger" {
  if (s === "aceito") return "success";
  if (s === "pendente") return "neutral";
  return "danger";
}

export default function AdminConvitesPage() {
  const [convites, setConvites] = useState<Convite[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<string>("");
  const [planoId, setPlanoId] = useState<string>("");
  const [dias, setDias] = useState(7);

  const carregar = useCallback(async () => {
    const [c, p] = await Promise.all([
      api.GET("/api/v1/admin/invites", {}),
      api.GET("/api/v1/plans", {}),
    ]);
    if (!c.error) setConvites((c.data as Convite[]) ?? []);
    if (!p.error) setPlanos((p.data as Plano[]) ?? []);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function convidar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (!getToken()) {
      setMsg("Faça login como administrador.");
      return;
    }
    const { error } = await api.POST("/api/v1/admin/invites", {
      body: {
        email,
        papel: papel || null,
        plano_id: planoId || null,
        expires_em_dias: dias,
      },
    });
    if (error) {
      setMsg("Não foi possível criar o convite.");
      return;
    }
    setEmail("");
    setMsg(
      "Convite criado. Se o SMTP estiver configurado, o e-mail já foi enviado — ou copie o link abaixo.",
    );
    await carregar();
  }

  function linkConvite(token: string): string {
    return `${window.location.origin}/accept-invite?token=${token}`;
  }

  async function copiar(token: string) {
    await navigator.clipboard.writeText(linkConvite(token));
    setCopiado(token);
    setTimeout(() => setCopiado(null), 2000);
  }

  async function removerConvite(id: string, email: string) {
    if (!window.confirm(`Excluir o convite de ${email}?`)) return;
    try {
      await excluirConvite(id);
      await carregar();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Falha ao excluir convite.");
    }
  }

  const planoNome = (id?: string | null) =>
    planos.find((p) => p.id === id)?.nome ?? "—";

  return (
    <>
      <header>
        <h1 className="page-title">Convites</h1>
        <p className="mt-1 text-sm text-ink-2">
          Convide alguém por e-mail já com papel e plano definidos. O convidado
          cria a própria senha no link e cai direto no onboarding.
        </p>
      </header>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <form onSubmit={convidar} className="card flex flex-wrap items-end gap-3 p-5">
        <label className="flex min-w-64 flex-1 flex-col gap-1.5">
          <span className="field-label">E-mail do convidado</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
            placeholder="pessoa@prefeitura.gov.br"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Papel (opcional)</span>
          <select
            value={papel}
            onChange={(e) => setPapel(e.target.value)}
            className="input w-40"
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
            className="input w-40"
          >
            <option value="">— sem plano —</option>
            {planos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Validade (dias)</span>
          <input
            type="number"
            min={1}
            max={90}
            value={dias}
            onChange={(e) => setDias(Number(e.target.value) || 7)}
            className="input w-24"
          />
        </label>
        <button type="submit" className="btn btn-primary">
          Convidar
        </button>
      </form>

      <section className="card overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-hairline text-left label-mono">
              <th className="px-5 py-3">Convidado</th>
              <th className="px-3 py-3">Papel</th>
              <th className="px-3 py-3">Plano</th>
              <th className="px-3 py-3">Status</th>
              <th className="px-3 py-3">Expira</th>
              <th className="px-3 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {convites.map((c) => (
              <tr
                key={c.id}
                className="border-b border-hairline last:border-0 hover:bg-surface-2"
              >
                <td className="px-5 py-3">{c.email}</td>
                <td className="px-3 py-3 text-ink-2">{c.papel ?? "—"}</td>
                <td className="px-3 py-3 text-ink-2">{planoNome(c.plano_id)}</td>
                <td className="px-3 py-3">
                  <StatusBadge tone={statusTone(c.status)}>{c.status}</StatusBadge>
                </td>
                <td className="px-3 py-3 font-mono text-[12px] text-ink-3">
                  {c.expires_at ? c.expires_at.slice(0, 10) : "—"}
                </td>
                <td className="px-3 py-3">
                  {c.status === "pendente" && (
                    <button
                      onClick={() => copiar(c.token)}
                      className="chip text-xs"
                      title="Copiar link do convite"
                    >
                      {copiado === c.token ? "Copiado ✓" : "Copiar link"}
                    </button>
                  )}
                  <button
                    onClick={() => void removerConvite(c.id, c.email)}
                    className="ml-2 text-xs text-red-500 hover:underline"
                    title="Excluir convite"
                  >
                    excluir
                  </button>
                </td>
              </tr>
            ))}
            {convites.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-4 text-ink-3">
                  Nenhum convite ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}
