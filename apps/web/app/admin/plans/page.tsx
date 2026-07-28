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
    const { data, error } = await api.GET("/api/v1/plans", {});
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
    const { error } = await api.POST("/api/v1/plans", {
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
    <>
      <header>
        <h1 className="page-title">Planos da plataforma</h1>
        <p className="mt-1 text-sm text-ink-2">
          Catálogo de planos atribuíveis aos usuários (em Usuários ou no convite).
        </p>
      </header>

      <form onSubmit={criar} className="card flex flex-wrap items-end gap-3 p-5">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Nome</span>
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            required
            className="input w-44"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Slug</span>
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            className="input w-36"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Preço/mês</span>
          <input
            value={preco}
            onChange={(e) => setPreco(e.target.value)}
            placeholder="99.90"
            className="input w-28"
          />
        </label>
        <button type="submit" className="btn btn-primary">
          Criar plano
        </button>
      </form>
      {msg && <p className="text-sm text-red-500">{msg}</p>}

      <ul className="card flex flex-col divide-y divide-hairline px-5">
        {planos.map((p) => (
          <li key={p.id} className="flex items-center justify-between py-3.5">
            <div>
              <span className="tracking-tight">{p.nome}</span>{" "}
              <span className="text-xs text-ink-3">/{p.slug}</span>
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
          <li className="py-3.5 text-ink-3">Nenhum plano cadastrado ainda.</li>
        )}
      </ul>
    </>
  );
}
