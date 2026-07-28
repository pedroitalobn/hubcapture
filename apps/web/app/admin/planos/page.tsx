"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

interface Plano {
  id: string;
  nome: string;
  slug: string;
  preco_mensal?: string | null;
  ativo: boolean;
}

export default function AdminPlanosPage() {
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [nome, setNome] = useState("");
  const [slug, setSlug] = useState("");
  const [preco, setPreco] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/planos", {});
    if (!error) setPlanos((data as Plano[]) ?? []);
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
    const { error } = await api.POST("/api/v1/planos", {
      body: {
        nome,
        slug,
        preco_mensal: preco ? preco : null,
        ativo: true,
      },
    });
    if (error) {
      setMsg("Falha ao criar (é necessário ser administrador).");
    } else {
      setNome("");
      setSlug("");
      setPreco("");
      await carregar();
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-8">
      <h1 className="text-gradient text-2xl font-bold">Planos da plataforma</h1>

      <form onSubmit={criar} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Nome
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            required
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Slug
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            className="input-glass px-3.5 py-2.5"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Preço/mês
          <input
            value={preco}
            onChange={(e) => setPreco(e.target.value)}
            placeholder="99.90"
            className="input-glass w-28 px-3.5 py-2.5"
          />
        </label>
        <button type="submit" className="btn-primary px-5 py-2.5">
          Criar plano
        </button>
      </form>
      {msg && <p className="text-sm text-red-400">{msg}</p>}

      <ul className="flex flex-col divide-y divide-white/5">
        {planos.map((p) => (
          <li key={p.id} className="flex items-center justify-between py-3">
            <div>
              <span className="font-medium">{p.nome}</span>{" "}
              <span className="text-xs text-gray-500">/{p.slug}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="tabular-nums">{formatBRL(p.preco_mensal)}/mês</span>
              <StatusBadge tone={p.ativo ? "success" : "neutral"}>
                {p.ativo ? "ativo" : "inativo"}
              </StatusBadge>
            </div>
          </li>
        ))}
        {planos.length === 0 && (
          <li className="py-3 text-gray-500">Nenhum plano cadastrado ainda.</li>
        )}
      </ul>
    </main>
  );
}
