"use client";

import { useCallback, useEffect, useState } from "react";
import { BrandMark } from "@/components/AuthShell";
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
      <BrandMark />
      <header>
        <h1 className="page-title">Configuração de providers</h1>
        <p className="mt-1 text-sm text-ink-2">
          Credenciais e URLs das fontes. Segredos ficam cifrados e mascarados.
        </p>
      </header>
      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      {categorias.map((cat) => (
        <section key={cat} className="flex flex-col gap-3">
          <h2 className="label-mono">
            {CATEGORIA_LABEL[cat] ?? cat}
          </h2>
          {itens
            .filter((i) => i.categoria === cat)
            .map((i) => (
              <div
                key={i.chave}
                className="card flex flex-wrap items-center gap-3 p-4"
              >
                <div className="min-w-40 flex-1">
                  <div className="text-sm tracking-tight">{i.label}</div>
                  <div className="text-xs text-ink-3">
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
                  className="input w-48 text-sm"
                />
                <button
                  onClick={() => salvar(i.chave)}
                  disabled={!(edits[i.chave] ?? "").length}
                  className="btn btn-primary btn-sm"
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
