"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken } from "@/lib/api/client";

interface ConfigItem {
  chave: string;
  label: string;
  categoria: string;
  secreto: boolean;
  configurado: boolean;
  origem: string;
  valor?: string | null;
}

const CATEGORIA_LABEL: Record<string, string> = {
  scraping: "Scraping (Firecrawl)",
  ia: "IA (LLM)",
  fonte: "Fontes de dados",
};

export default function AdminConfigPage() {
  const [itens, setItens] = useState<ConfigItem[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/admin/config", {});
    if (error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      return;
    }
    setItens((data as ConfigItem[]) ?? []);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      setMsg("Faça login como administrador.");
      return;
    }
    void carregar();
  }, [carregar]);

  async function salvar(chave: string) {
    const valor = edits[chave] ?? "";
    setMsg(null);
    const { error } = await api.PUT("/api/v1/admin/config", {
      body: { chave, valor },
    });
    if (error) {
      setMsg("Falha ao salvar (é necessário ser administrador).");
    } else {
      setEdits((e) => ({ ...e, [chave]: "" }));
      await carregar();
    }
  }

  const categorias = Array.from(new Set(itens.map((i) => i.categoria)));

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-8">
      <header>
        <h1 className="text-2xl font-bold">Configuração de providers</h1>
        <p className="text-sm text-gray-500">
          Credenciais e URLs das fontes. Segredos ficam cifrados e mascarados.
        </p>
      </header>
      {msg && <p className="text-sm text-amber-600">{msg}</p>}

      {categorias.map((cat) => (
        <section key={cat} className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            {CATEGORIA_LABEL[cat] ?? cat}
          </h2>
          {itens
            .filter((i) => i.categoria === cat)
            .map((i) => (
              <div
                key={i.chave}
                className="flex flex-wrap items-center gap-3 rounded-md border border-gray-200 p-3 dark:border-gray-800"
              >
                <div className="min-w-40 flex-1">
                  <div className="text-sm font-medium">{i.label}</div>
                  <div className="text-xs text-gray-500">
                    {i.chave}
                    {i.valor ? ` · ${i.valor}` : ""}
                  </div>
                </div>
                <StatusBadge tone={i.configurado ? "success" : "neutral"}>
                  {i.configurado ? i.origem : "não definido"}
                </StatusBadge>
                <input
                  type={i.secreto ? "password" : "text"}
                  placeholder={i.secreto ? "nova credencial" : "novo valor"}
                  value={edits[i.chave] ?? ""}
                  onChange={(e) =>
                    setEdits((s) => ({ ...s, [i.chave]: e.target.value }))
                  }
                  className="w-48 rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
                />
                <button
                  onClick={() => salvar(i.chave)}
                  disabled={!(edits[i.chave] ?? "").length}
                  className="rounded-md bg-brand px-3 py-1.5 text-sm text-brand-fg disabled:opacity-50"
                >
                  Salvar
                </button>
              </div>
            ))}
        </section>
      ))}
    </main>
  );
}
