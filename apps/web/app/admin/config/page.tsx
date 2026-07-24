"use client";

import { useCallback, useEffect, useState } from "react";
import { BrandMark } from "@/components/AuthShell";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken } from "@/lib/api/client";

interface ConfigItem {
  chave: string;
  label: string;
  categoria: string;
  provider?: string | null;
  secreto: boolean;
  configurado: boolean;
  origem: string; // 'banco' (painel) | 'env' (fallback .env) | 'padrao'
  valor?: string | null;
}

// Seções por PROVIDER (scraping/IA) e depois pelas demais categorias.
// A ordem aqui é a ordem de exibição.
const GRUPOS: { id: string; titulo: string; descricao?: string }[] = [
  { id: "firecrawl", titulo: "Firecrawl", descricao: "Scraping gerenciado (SaaS)" },
  { id: "crawl4ai", titulo: "Crawl4AI", descricao: "Scraping self-hosted (Docker)" },
  { id: "scraping", titulo: "Scraping — preferência", descricao: "Qual provider tentar primeiro" },
  { id: "llm", titulo: "LLM", descricao: "Resumo por IA, chat e copiloto (via LiteLLM)" },
  { id: "embeddings", titulo: "Embeddings", descricao: "Busca semântica / RAG (pgvector)" },
  { id: "fonte", titulo: "Fontes de dados", descricao: "URLs e tokens das fontes de governo" },
  { id: "whatsapp", titulo: "WhatsApp (Uniq)" },
  { id: "email", titulo: "E-mail (SMTP)" },
];

const ORIGEM_LABEL: Record<string, string> = {
  banco: "painel",
  env: ".env (fallback)",
};

function grupoDe(item: ConfigItem): string {
  return item.provider ?? item.categoria;
}

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

  // grupos conhecidos na ordem definida + eventuais grupos novos no fim
  const idsConhecidos = new Set(GRUPOS.map((g) => g.id));
  const extras: typeof GRUPOS = Array.from(
    new Set(itens.map(grupoDe).filter((g) => !idsConhecidos.has(g))),
  ).map((id) => ({ id, titulo: id }));
  const grupos = [...GRUPOS, ...extras].filter((g) =>
    itens.some((i) => grupoDe(i) === g.id),
  );

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-8">
      <BrandMark />
      <header>
        <h1 className="page-title">Configuração de providers</h1>
        <p className="mt-1 text-sm text-ink-2">
          Credenciais e URLs por provider. O valor salvo aqui vale na hora; sem
          valor no painel, vale o fallback do <code>.env</code>. Segredos ficam
          cifrados e mascarados.
        </p>
      </header>
      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      {grupos.map((g) => (
        <section key={g.id} className="flex flex-col gap-3">
          <div>
            <h2 className="label-mono">{g.titulo}</h2>
            {g.descricao && (
              <p className="mt-0.5 text-xs text-ink-3">{g.descricao}</p>
            )}
          </div>
          {itens
            .filter((i) => grupoDe(i) === g.id)
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
                  {i.configurado
                    ? (ORIGEM_LABEL[i.origem] ?? i.origem)
                    : "não definido"}
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
