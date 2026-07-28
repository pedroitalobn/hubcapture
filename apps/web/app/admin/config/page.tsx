"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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

interface LlmProvider {
  id: string;
  label: string;
  chave: string;
  configurado: boolean;
  chave_mascarada?: string | null;
  docs_url: string;
  modelo_chat: boolean;
  modelo_resumo: boolean;
}

interface Categoria {
  id: string;
  label: string;
  desc: string;
}

const CATEGORIAS: Categoria[] = [
  { id: "ia", label: "IA · LLMs", desc: "Modelos de linguagem e embeddings" },
  { id: "scraping", label: "Scraping", desc: "Enriquecimento e fallback de coleta" },
  { id: "fonte", label: "Fontes de dados", desc: "APIs e portais do governo" },
  { id: "whatsapp", label: "WhatsApp", desc: "Alertas e chat (Uniq)" },
  { id: "email", label: "E-mail", desc: "SMTP transacional" },
];

/** Agrupamento das chaves do catálogo em provedores (categorias genéricas). */
const GRUPOS: { id: string; label: string; categoria: string; prefixos: string[] }[] = [
  { id: "firecrawl", label: "Firecrawl", categoria: "scraping", prefixos: ["firecrawl_"] },
  { id: "transferegov_ff", label: "TransfereGov — Fundo a Fundo", categoria: "fonte", prefixos: ["transferegov_ff_"] },
  { id: "transferegov_esp", label: "TransfereGov — Especiais", categoria: "fonte", prefixos: ["transferegov_esp_"] },
  { id: "transferegov_disc", label: "TransfereGov — Discricionárias", categoria: "fonte", prefixos: ["transferegov_disc_"] },
  { id: "fns", label: "FNS — Fundo Nacional de Saúde", categoria: "fonte", prefixos: ["fns_"] },
  { id: "fnde", label: "FNDE", categoria: "fonte", prefixos: ["fnde_"] },
  { id: "serpro", label: "SERPRO", categoria: "fonte", prefixos: ["serpro_"] },
  { id: "fpm", label: "FPM (Tesouro)", categoria: "fonte", prefixos: ["fpm_"] },
  { id: "emendas", label: "Emendas", categoria: "fonte", prefixos: ["emendas_"] },
  { id: "siconfi", label: "Siconfi / CAUC", categoria: "fonte", prefixos: ["siconfi_"] },
  { id: "sismob", label: "SISMOB (obras saúde)", categoria: "fonte", prefixos: ["sismob_"] },
  { id: "simec", label: "SIMEC (obras educação)", categoria: "fonte", prefixos: ["simec_"] },
  { id: "caixa", label: "CAIXA / SIORB (obras infra)", categoria: "fonte", prefixos: ["caixa_"] },
  { id: "uniq", label: "Uniq (WhatsApp)", categoria: "whatsapp", prefixos: ["uniq_"] },
  { id: "smtp", label: "SMTP / E-mail transacional", categoria: "email", prefixos: ["email_", "app_base_url"] },
  { id: "embeddings", label: "Embeddings (RAG)", categoria: "ia", prefixos: ["embedding_"] },
  { id: "llm_legado", label: "LLM genérico (LiteLLM, legado)", categoria: "ia", prefixos: ["llm_api_key"] },
];

function grupoDaChave(chave: string): string | null {
  const g = GRUPOS.find((gr) => gr.prefixos.some((p) => chave.startsWith(p)));
  return g?.id ?? null;
}

export default function AdminConfigPage() {
  const [itens, setItens] = useState<ConfigItem[]>([]);
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [cat, setCat] = useState<string>("ia");
  const [adicionando, setAdicionando] = useState<string | null>(null); // id do grupo/provider aberto p/ adicionar

  // estado da seção LLM
  const [chaveEdits, setChaveEdits] = useState<Record<string, string>>({});
  const [modelos, setModelos] = useState<Record<string, string[]>>({});
  const [modeloSel, setModeloSel] = useState<Record<string, string>>({});
  const [carregandoModelos, setCarregandoModelos] = useState<Record<string, boolean>>({});
  const [origemModelos, setOrigemModelos] = useState<Record<string, string>>({});

  const carregar = useCallback(async () => {
    const [cfg, llm] = await Promise.all([
      api.GET("/api/v1/admin/config", {}),
      api.GET("/api/v1/admin/config/llm/providers", {}),
    ]);
    if (cfg.error || llm.error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      return;
    }
    setItens((cfg.data as ConfigItem[]) ?? []);
    setProviders((llm.data as LlmProvider[]) ?? []);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      setMsg("Faça login como administrador.");
      return;
    }
    void carregar();
  }, [carregar]);

  async function salvarChaveCatalogo(chave: string) {
    const valor = edits[chave] ?? "";
    setMsg(null);
    const { error } = await api.PUT("/api/v1/admin/config", { body: { chave, valor } });
    if (error) {
      setMsg("Falha ao salvar (é necessário ser administrador).");
    } else {
      setEdits((e) => ({ ...e, [chave]: "" }));
      await carregar();
    }
  }

  /** Salva a API key do provedor LLM e já recebe os modelos dele (menor fricção). */
  async function salvarChaveLlm(pid: string) {
    const apiKey = (chaveEdits[pid] ?? "").trim();
    if (!apiKey) return;
    setMsg(null);
    setCarregandoModelos((s) => ({ ...s, [pid]: true }));
    const { data, error } = await api.PUT("/api/v1/admin/config/llm/{provider_id}/chave", {
      params: { path: { provider_id: pid } },
      body: { api_key: apiKey },
    });
    setCarregandoModelos((s) => ({ ...s, [pid]: false }));
    if (error) {
      setMsg("Falha ao salvar a chave do provedor.");
      return;
    }
    setChaveEdits((s) => ({ ...s, [pid]: "" }));
    setModelos((s) => ({ ...s, [pid]: data?.modelos ?? [] }));
    setOrigemModelos((s) => ({ ...s, [pid]: data?.origem ?? "" }));
    setAdicionando(null);
    await carregar();
  }

  async function carregarModelos(pid: string) {
    if (modelos[pid] || carregandoModelos[pid]) return;
    setCarregandoModelos((s) => ({ ...s, [pid]: true }));
    const { data, error } = await api.GET("/api/v1/admin/config/llm/{provider_id}/modelos", {
      params: { path: { provider_id: pid } },
    });
    setCarregandoModelos((s) => ({ ...s, [pid]: false }));
    if (!error && data) {
      setModelos((s) => ({ ...s, [pid]: data.modelos }));
      setOrigemModelos((s) => ({ ...s, [pid]: data.origem }));
    }
  }

  async function usarModelo(pid: string, uso: "chat" | "resumo") {
    const modelo = modeloSel[pid] ?? modelos[pid]?.[0];
    if (!modelo) return;
    const chave = uso === "chat" ? "llm_model_chat" : "llm_model_resumo";
    const { error } = await api.PUT("/api/v1/admin/config", {
      body: { chave, valor: `${pid}/${modelo}` },
    });
    if (error) setMsg("Falha ao definir o modelo.");
    else await carregar();
  }

  const porChave = useMemo(
    () => Object.fromEntries(itens.map((i) => [i.chave, i])),
    [itens],
  );
  const modeloChat = porChave["llm_model_chat"]?.valor ?? null;
  const modeloResumo = porChave["llm_model_resumo"]?.valor ?? null;

  /** Grupos (não-LLM) da categoria ativa, com itens e status. */
  const gruposDaCategoria = useMemo(() => {
    return GRUPOS.filter((g) => g.categoria === cat)
      .map((g) => {
        const chaves = itens.filter((i) => grupoDaChave(i.chave) === g.id);
        return { ...g, chaves, ativo: chaves.some((i) => i.configurado) };
      })
      .filter((g) => g.chaves.length > 0);
  }, [cat, itens]);

  const contagemPorCategoria = useMemo(() => {
    const conta: Record<string, number> = {};
    for (const c of CATEGORIAS) {
      if (c.id === "ia") {
        conta[c.id] =
          providers.filter((p) => p.configurado).length +
          (itens.some((i) => i.chave === "embedding_api_key" && i.configurado) ? 1 : 0);
      } else {
        const ids = new Set(
          itens
            .filter((i) => i.categoria === c.id && i.configurado)
            .map((i) => grupoDaChave(i.chave))
            .filter(Boolean),
        );
        conta[c.id] = ids.size;
      }
    }
    return conta;
  }, [itens, providers]);

  function campoChave(item: ConfigItem) {
    return (
      <div className="flex flex-wrap items-center gap-3 py-2">
        <div className="min-w-40 flex-1">
          <div className="text-sm font-medium">{item.label}</div>
          <div className="text-xs text-gray-500">
            {item.chave}
            {item.valor ? ` · ${item.valor}` : ""}
          </div>
        </div>
        <StatusBadge tone={item.configurado ? "success" : "neutral"}>
          {item.configurado ? item.origem : "não definido"}
        </StatusBadge>
        <input
          type={item.secreto ? "password" : "text"}
          placeholder={item.secreto ? "nova credencial" : "novo valor"}
          value={edits[item.chave] ?? ""}
          onChange={(e) => setEdits((s) => ({ ...s, [item.chave]: e.target.value }))}
          className="w-48 rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
        />
        <button
          onClick={() => salvarChaveCatalogo(item.chave)}
          disabled={!(edits[item.chave] ?? "").length}
          className="rounded-md bg-brand px-3 py-1.5 text-sm text-brand-fg disabled:opacity-50"
        >
          Salvar
        </button>
      </div>
    );
  }

  function cardProviderLlm(p: LlmProvider) {
    const lista = modelos[p.id];
    return (
      <div className="flex flex-col gap-3 rounded-md border border-gray-200 p-4 dark:border-gray-800">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex-1">
            <div className="text-sm font-semibold">{p.label}</div>
            <div className="text-xs text-gray-500">
              {p.configurado ? `chave ${p.chave_mascarada}` : "sem chave"}
            </div>
          </div>
          {p.modelo_chat && <StatusBadge tone="success">chat</StatusBadge>}
          {p.modelo_resumo && <StatusBadge tone="success">resumo</StatusBadge>}
          <StatusBadge tone={p.configurado ? "success" : "neutral"}>
            {p.configurado ? "ativo" : "inativo"}
          </StatusBadge>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            placeholder={p.configurado ? "trocar API key" : "colar API key"}
            value={chaveEdits[p.id] ?? ""}
            onChange={(e) => setChaveEdits((s) => ({ ...s, [p.id]: e.target.value }))}
            className="w-56 rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          />
          <button
            onClick={() => salvarChaveLlm(p.id)}
            disabled={!(chaveEdits[p.id] ?? "").trim().length || !!carregandoModelos[p.id]}
            className="rounded-md bg-brand px-3 py-1.5 text-sm text-brand-fg disabled:opacity-50"
          >
            {carregandoModelos[p.id] ? "Validando…" : "Salvar chave"}
          </button>
          <a
            href={p.docs_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-gray-500 underline"
          >
            obter chave
          </a>
        </div>

        {p.configurado && (
          <div className="flex flex-wrap items-center gap-2">
            {!lista ? (
              <button
                onClick={() => carregarModelos(p.id)}
                disabled={!!carregandoModelos[p.id]}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700"
              >
                {carregandoModelos[p.id] ? "Buscando modelos…" : "Listar modelos"}
              </button>
            ) : (
              <>
                <select
                  value={modeloSel[p.id] ?? lista[0] ?? ""}
                  onChange={(e) => setModeloSel((s) => ({ ...s, [p.id]: e.target.value }))}
                  className="min-w-56 rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
                >
                  {lista.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => usarModelo(p.id, "chat")}
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700"
                >
                  Usar no chat
                </button>
                <button
                  onClick={() => usarModelo(p.id, "resumo")}
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700"
                >
                  Usar no resumo
                </button>
                {origemModelos[p.id] === "fallback" && (
                  <span className="text-xs text-amber-600">
                    lista padrão (não foi possível listar ao vivo — confira a chave)
                  </span>
                )}
              </>
            )}
          </div>
        )}
      </div>
    );
  }

  const llmAtivos = providers.filter((p) => p.configurado);
  const llmInativos = providers.filter((p) => !p.configurado);
  const catMeta = CATEGORIAS.find((c) => c.id === cat);
  const gruposAtivos = gruposDaCategoria.filter((g) => g.ativo);
  const gruposInativos = gruposDaCategoria.filter((g) => !g.ativo);

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl gap-8 px-6 py-8">
      {/* Menu lateral: categorias de provedores */}
      <aside className="w-56 shrink-0">
        <h1 className="mb-1 text-lg font-bold">Provedores</h1>
        <p className="mb-4 text-xs text-gray-500">
          Credenciais e URLs por categoria. Segredos ficam cifrados e mascarados.
        </p>
        <nav className="flex flex-col gap-1">
          {CATEGORIAS.map((c) => (
            <button
              key={c.id}
              onClick={() => {
                setCat(c.id);
                setAdicionando(null);
              }}
              className={`rounded-md px-3 py-2 text-left text-sm ${
                cat === c.id
                  ? "bg-brand text-brand-fg"
                  : "hover:bg-gray-100 dark:hover:bg-gray-900"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{c.label}</span>
                <span
                  className={`text-xs ${cat === c.id ? "opacity-80" : "text-gray-500"}`}
                >
                  {contagemPorCategoria[c.id] ?? 0} ativo(s)
                </span>
              </div>
            </button>
          ))}
        </nav>
      </aside>

      {/* Conteúdo da categoria selecionada */}
      <section className="flex min-w-0 flex-1 flex-col gap-6">
        <header>
          <h2 className="text-2xl font-bold">{catMeta?.label}</h2>
          <p className="text-sm text-gray-500">{catMeta?.desc}</p>
        </header>
        {msg && <p className="text-sm text-amber-600">{msg}</p>}

        {cat === "ia" ? (
          <>
            <div className="rounded-md border border-gray-200 p-4 text-sm dark:border-gray-800">
              <div className="mb-1 font-semibold">Modelos em uso</div>
              <div className="text-gray-600 dark:text-gray-300">
                Chat/Copiloto: <code>{modeloChat ?? "padrão"}</code> · Resumos:{" "}
                <code>{modeloResumo ?? "padrão"}</code>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Cole a API key de um provedor abaixo — os modelos dele aparecem na
                hora para você escolher.
              </p>
            </div>

            {llmAtivos.length > 0 && (
              <div className="flex flex-col gap-3">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                  Provedores ativos
                </h3>
                {llmAtivos.map((p) => (
                  <div key={p.id}>{cardProviderLlm(p)}</div>
                ))}
              </div>
            )}

            <div className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                Adicionar provedor
              </h3>
              <div className="flex flex-wrap gap-2">
                {llmInativos.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setAdicionando(adicionando === p.id ? null : p.id)}
                    className={`rounded-full border px-3 py-1.5 text-sm ${
                      adicionando === p.id
                        ? "border-brand bg-brand text-brand-fg"
                        : "border-gray-300 hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-900"
                    }`}
                  >
                    + {p.label}
                  </button>
                ))}
                {llmInativos.length === 0 && (
                  <p className="text-sm text-gray-500">Todos os provedores estão ativos.</p>
                )}
              </div>
              {adicionando &&
                providers
                  .filter((p) => p.id === adicionando)
                  .map((p) => <div key={p.id}>{cardProviderLlm(p)}</div>)}
            </div>

            {gruposDaCategoria.map((g) => (
              <div
                key={g.id}
                className="rounded-md border border-gray-200 p-4 dark:border-gray-800"
              >
                <div className="mb-2 flex items-center gap-2">
                  <h3 className="flex-1 text-sm font-semibold">{g.label}</h3>
                  <StatusBadge tone={g.ativo ? "success" : "neutral"}>
                    {g.ativo ? "ativo" : "inativo"}
                  </StatusBadge>
                </div>
                {g.chaves.map((i) => (
                  <div key={i.chave}>{campoChave(i)}</div>
                ))}
              </div>
            ))}
          </>
        ) : (
          <>
            {gruposAtivos.length > 0 && (
              <div className="flex flex-col gap-3">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                  Provedores ativos
                </h3>
                {gruposAtivos.map((g) => (
                  <div
                    key={g.id}
                    className="rounded-md border border-gray-200 p-4 dark:border-gray-800"
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <h4 className="flex-1 text-sm font-semibold">{g.label}</h4>
                      <StatusBadge tone="success">ativo</StatusBadge>
                    </div>
                    {g.chaves.map((i) => (
                      <div key={i.chave}>{campoChave(i)}</div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            <div className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                Adicionar provedor
              </h3>
              <div className="flex flex-wrap gap-2">
                {gruposInativos.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => setAdicionando(adicionando === g.id ? null : g.id)}
                    className={`rounded-full border px-3 py-1.5 text-sm ${
                      adicionando === g.id
                        ? "border-brand bg-brand text-brand-fg"
                        : "border-gray-300 hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-900"
                    }`}
                  >
                    + {g.label}
                  </button>
                ))}
                {gruposInativos.length === 0 && (
                  <p className="text-sm text-gray-500">
                    Todos os provedores desta categoria estão ativos.
                  </p>
                )}
              </div>
              {gruposInativos
                .filter((g) => g.id === adicionando)
                .map((g) => (
                  <div
                    key={g.id}
                    className="rounded-md border border-gray-200 p-4 dark:border-gray-800"
                  >
                    <h4 className="mb-2 text-sm font-semibold">{g.label}</h4>
                    {g.chaves.map((i) => (
                      <div key={i.chave}>{campoChave(i)}</div>
                    ))}
                  </div>
                ))}
            </div>
          </>
        )}
      </section>
    </main>
  );
}
