"use client";

import { CreditCard, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { Callout } from "@/components/Callout";
import { PageHeader } from "@/components/PageHeader";
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

const INPUT =
  "rounded-lg border border-gray-300 bg-white px-3 py-2 transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-950";

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
      <PageHeader
        icon={CreditCard}
        title="Planos da plataforma"
        subtitle="Catálogo de assinaturas disponíveis para os usuários."
      />

      <form
        onSubmit={criar}
        className="flex flex-wrap items-end gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900"
      >
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Nome
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            required
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Slug
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Preço/mês
          <input
            value={preco}
            onChange={(e) => setPreco(e.target.value)}
            placeholder="99.90"
            className={`${INPUT} w-28 tabular-nums`}
          />
        </label>
        <Button type="submit" icon={<Plus className="h-4 w-4" aria-hidden />}>
          Criar plano
        </Button>
      </form>
      {msg && <Callout tone="error">{msg}</Callout>}

      <ul className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900">
        {planos.map((p) => (
          <li
            key={p.id}
            className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3 transition-colors last:border-b-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50"
          >
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">
                <CreditCard className="h-4 w-4" aria-hidden />
              </span>
              <div>
                <span className="font-medium">{p.nome}</span>{" "}
                <span className="text-xs text-gray-500">/{p.slug}</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="font-semibold tabular-nums">
                {formatBRL(p.preco_mensal)}
                <span className="text-xs font-normal text-gray-500">/mês</span>
              </span>
              <StatusBadge tone={p.ativo ? "success" : "neutral"}>
                {p.ativo ? "ativo" : "inativo"}
              </StatusBadge>
            </div>
          </li>
        ))}
        {planos.length === 0 && (
          <li className="px-4 py-6 text-center text-sm text-gray-500">
            Nenhum plano cadastrado ainda.
          </li>
        )}
      </ul>
    </main>
  );
}
