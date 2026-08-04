"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken, testarEmail } from "@/lib/api/client";

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

const CATEGORIAS: { id: string; label: string; desc: string }[] = [
  { id: "ia", label: "IA · LLMs", desc: "Modelos de linguagem e embeddings" },
  { id: "scraping", label: "Scraping", desc: "Enriquecimento e fallback de coleta" },
  { id: "fonte", label: "Fontes de dados", desc: "APIs e portais do governo" },
  {
    id: "integracoes",
    label: "Integrações · Agenda",
    desc: "Contatos do usuário no Google, Microsoft e Apple",
  },
  { id: "whatsapp", label: "WhatsApp", desc: "Alertas e chat (Uniq)" },
  { id: "email", label: "E-mail", desc: "SMTP transacional" },
];

const ORIGEM_LABEL: Record<string, string> = {
  banco: "painel",
  env: ".env (fallback)",
};

/** Agrupa as chaves do catálogo em provedores dentro de cada categoria. */
const GRUPOS: { id: string; label: string; categoria: string; prefixos: string[] }[] = [
  { id: "firecrawl", label: "Firecrawl (SaaS)", categoria: "scraping", prefixos: ["firecrawl_"] },
  {
    id: "crawl4ai",
    label: "Crawl4AI (self-hosted)",
    categoria: "scraping",
    prefixos: ["crawl4ai_"],
  },
  {
    id: "scraping_pref",
    label: "Preferência de scraper",
    categoria: "scraping",
    prefixos: ["scraping_provider"],
  },
  {
    id: "transferegov_ff",
    label: "TransfereGov — Fundo a Fundo",
    categoria: "fonte",
    prefixos: ["transferegov_ff_"],
  },
  {
    id: "transferegov_esp",
    label: "TransfereGov — Especiais",
    categoria: "fonte",
    prefixos: ["transferegov_esp_"],
  },
  {
    id: "transferegov_voluntarias",
    label: "TransfereGov — Voluntárias",
    categoria: "fonte",
    prefixos: ["transferegov_voluntarias_"],
  },
  {
    id: "transferegov_disc",
    label: "TransfereGov — Discricionárias",
    categoria: "fonte",
    prefixos: ["transferegov_disc_"],
  },
  {
    id: "transferegov_noticias",
    label: "TransfereGov — Notícias (RSS)",
    categoria: "fonte",
    prefixos: ["transferegov_noticias_"],
  },
  {
    id: "fns",
    label: "FNS — Fundo Nacional de Saúde",
    categoria: "fonte",
    prefixos: ["fns_"],
  },
  { id: "fnde", label: "FNDE", categoria: "fonte", prefixos: ["fnde_"] },
  { id: "serpro", label: "SERPRO", categoria: "fonte", prefixos: ["serpro_"] },
  { id: "fpm", label: "FPM (Tesouro)", categoria: "fonte", prefixos: ["fpm_"] },
  { id: "emendas", label: "Emendas", categoria: "fonte", prefixos: ["emendas_"] },
  { id: "siconfi", label: "Siconfi / CAUC", categoria: "fonte", prefixos: ["siconfi_"] },
  {
    id: "sismob",
    label: "SISMOB (obras saúde)",
    categoria: "fonte",
    prefixos: ["sismob_"],
  },
  {
    id: "simec",
    label: "SIMEC (obras educação)",
    categoria: "fonte",
    prefixos: ["simec_"],
  },
  {
    id: "caixa",
    label: "CAIXA / SIORB (obras infra)",
    categoria: "fonte",
    prefixos: ["caixa_"],
  },
  { id: "ibge", label: "IBGE Localidades", categoria: "fonte", prefixos: ["ibge_"] },
  {
    id: "google_contatos",
    label: "Google Contacts (OAuth)",
    categoria: "integracoes",
    prefixos: ["google_"],
  },
  {
    id: "microsoft_contatos",
    label: "Outlook / Microsoft 365 (OAuth)",
    categoria: "integracoes",
    prefixos: ["microsoft_"],
  },
  {
    id: "apple_contatos",
    label: "Apple / iCloud (CardDAV)",
    categoria: "integracoes",
    prefixos: ["apple_"],
  },
  { id: "uniq", label: "Uniq (WhatsApp)", categoria: "whatsapp", prefixos: ["uniq_"] },
  {
    id: "smtp",
    label: "SMTP / E-mail transacional",
    categoria: "email",
    prefixos: ["email_", "app_base_url"],
  },
  {
    id: "embeddings",
    label: "Embeddings (RAG)",
    categoria: "ia",
    prefixos: ["embedding_"],
  },
  {
    id: "llm_legado",
    label: "LLM genérico (LiteLLM, legado)",
    categoria: "ia",
    prefixos: ["llm_api_key"],
  },
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
  // id do grupo/provider inativo aberto para configuração
  const [adicionando, setAdicionando] = useState<string | null>(null);
  // teste de envio de e-mail (valida Maileroo/SMTP sem depender de convite)
  const [emailTeste, setEmailTeste] = useState("");
  const [emailResultado, setEmailResultado] = useState<string | null>(null);
  const [testandoEmail, setTestandoEmail] = useState(false);

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

  /** Grupos (não-LLM) da categoria ativa, com suas chaves e status. */
  const gruposDaCategoria = useMemo(
    () =>
      GRUPOS.filter((g) => g.categoria === cat)
        .map((g) => {
          const chaves = itens.filter((i) => grupoDaChave(i.chave) === g.id);
          return { ...g, chaves, ativo: chaves.some((i) => i.configurado) };
        })
        .filter((g) => g.chaves.length > 0),
    [cat, itens],
  );

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
          <div className="text-sm tracking-tight">{item.label}</div>
          <div className="text-xs text-ink-3">
            {item.chave}
            {item.valor ? ` · ${item.valor}` : ""}
          </div>
        </div>
        <StatusBadge tone={item.configurado ? "success" : "neutral"}>
          {item.configurado ? (ORIGEM_LABEL[item.origem] ?? item.origem) : "não definido"}
        </StatusBadge>
        <input
          type={item.secreto ? "password" : "text"}
          placeholder={item.secreto ? "nova credencial" : "novo valor"}
          value={edits[item.chave] ?? ""}
          onChange={(e) => setEdits((s) => ({ ...s, [item.chave]: e.target.value }))}
          className="input w-48 text-sm"
        />
        <button
          onClick={() => salvarChaveCatalogo(item.chave)}
          disabled={!(edits[item.chave] ?? "").length}
          className="btn btn-primary btn-sm"
        >
          Salvar
        </button>
      </div>
    );
  }

  function cardProviderLlm(p: LlmProvider) {
    const lista = modelos[p.id];
    return (
      <div className="card flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex-1">
            <div className="text-sm tracking-tight">{p.label}</div>
            <div className="text-xs text-ink-3">
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
            className="input w-56 text-sm"
          />
          <button
            onClick={() => salvarChaveLlm(p.id)}
            disabled={!(chaveEdits[p.id] ?? "").trim().length || !!carregandoModelos[p.id]}
            className="btn btn-primary btn-sm"
          >
            {carregandoModelos[p.id] ? "Validando…" : "Salvar chave"}
          </button>
          <a
            href={p.docs_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-ink-3 underline"
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
                className="btn btn-sm"
              >
                {carregandoModelos[p.id] ? "Buscando modelos…" : "Listar modelos"}
              </button>
            ) : (
              <>
                <select
                  value={modeloSel[p.id] ?? lista[0] ?? ""}
                  onChange={(e) => setModeloSel((s) => ({ ...s, [p.id]: e.target.value }))}
                  className="input min-w-56 text-sm"
                >
                  {lista.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
                <button onClick={() => usarModelo(p.id, "chat")} className="btn btn-sm">
                  Usar no chat
                </button>
                <button onClick={() => usarModelo(p.id, "resumo")} className="btn btn-sm">
                  Usar no resumo
                </button>
                {origemModelos[p.id] === "fallback" && (
                  <span className="text-xs text-ink-3">
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
    <>
      <header>
        <h1 className="page-title">Providers &amp; Config</h1>
        <p className="mt-1 text-sm text-ink-2">
          Credenciais e URLs por categoria de provedor. O valor salvo aqui vale na
          hora; sem valor no painel, vale o fallback do <code>.env</code>. Segredos
          ficam cifrados e mascarados.
        </p>
      </header>
      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <div className="flex flex-col gap-6 md:flex-row md:gap-8">
        {/* Menu lateral — categoria do provedor */}
        <aside className="w-full shrink-0 md:w-56">
          <nav className="flex flex-row flex-wrap gap-1 md:flex-col">
            {CATEGORIAS.map((c) => (
              <button
                key={c.id}
                onClick={() => {
                  setCat(c.id);
                  setAdicionando(null);
                }}
                className={`nav-item text-left ${cat === c.id ? "nav-item-active" : ""}`}
              >
                <span className="flex w-full items-center justify-between gap-2">
                  <span>{c.label}</span>
                  <span className="text-xs opacity-70">
                    {contagemPorCategoria[c.id] ?? 0}
                  </span>
                </span>
              </button>
            ))}
          </nav>
        </aside>

        {/* Provedores da categoria selecionada */}
        <section className="flex min-w-0 flex-1 flex-col gap-6">
          <div>
            <h2 className="label-mono">{catMeta?.label}</h2>
            <p className="mt-0.5 text-xs text-ink-3">{catMeta?.desc}</p>
          </div>

          {cat === "ia" ? (
            <>
              <div className="card p-4 text-sm">
                <div className="mb-1 tracking-tight">Modelos em uso</div>
                <div className="text-ink-2">
                  Chat/Copiloto: <code>{modeloChat ?? "padrão"}</code> · Resumos:{" "}
                  <code>{modeloResumo ?? "padrão"}</code>
                </div>
                <p className="mt-1 text-xs text-ink-3">
                  Cole a API key de um provedor abaixo — os modelos dele aparecem na
                  hora para você escolher.
                </p>
              </div>

              {llmAtivos.length > 0 && (
                <div className="flex flex-col gap-3">
                  <h3 className="label-mono">Provedores ativos</h3>
                  {llmAtivos.map((p) => (
                    <div key={p.id}>{cardProviderLlm(p)}</div>
                  ))}
                </div>
              )}

              <div className="flex flex-col gap-3">
                <h3 className="label-mono">Adicionar provedor</h3>
                <div className="flex flex-wrap gap-2">
                  {llmInativos.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setAdicionando(adicionando === p.id ? null : p.id)}
                      className={`chip ${adicionando === p.id ? "chip-active" : ""}`}
                    >
                      + {p.label}
                    </button>
                  ))}
                  {llmInativos.length === 0 && (
                    <p className="text-sm text-ink-3">
                      Todos os provedores estão ativos.
                    </p>
                  )}
                </div>
                {adicionando &&
                  providers
                    .filter((p) => p.id === adicionando)
                    .map((p) => <div key={p.id}>{cardProviderLlm(p)}</div>)}
              </div>

              {gruposDaCategoria.map((g) => (
                <div key={g.id} className="card p-4">
                  <div className="mb-2 flex items-center gap-2">
                    <h3 className="flex-1 text-sm tracking-tight">{g.label}</h3>
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
              {cat === "email" && (
                <div className="card border border-lime/30 p-4">
                  <h3 className="text-sm tracking-tight">Testar envio de e-mail</h3>
                  <p className="mt-1 text-xs text-ink-2">
                    Manda um e-mail de teste (usa Maileroo se a API key estiver setada;
                    senão o SMTP). Se o provedor recusar, o erro aparece aqui.
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <input
                      value={emailTeste}
                      onChange={(e) => setEmailTeste(e.target.value)}
                      placeholder="destinatário (vazio = seu e-mail de admin)"
                      className="input w-72"
                    />
                    <button
                      onClick={async () => {
                        setTestandoEmail(true);
                        setEmailResultado(null);
                        try {
                          const r = await testarEmail(emailTeste);
                          setEmailResultado((r.enviado ? "✓ " : "✗ ") + r.detalhe);
                        } catch (e) {
                          setEmailResultado(
                            e instanceof Error ? e.message : "erro desconhecido",
                          );
                        } finally {
                          setTestandoEmail(false);
                        }
                      }}
                      disabled={testandoEmail}
                      className="btn btn-primary"
                    >
                      {testandoEmail ? "Enviando…" : "Enviar teste"}
                    </button>
                  </div>
                  {emailResultado && (
                    <p className="mt-3 text-xs text-ink-2">{emailResultado}</p>
                  )}
                </div>
              )}
              {gruposAtivos.length > 0 && (
                <div className="flex flex-col gap-3">
                  <h3 className="label-mono">Provedores ativos</h3>
                  {gruposAtivos.map((g) => (
                    <div key={g.id} className="card p-4">
                      <div className="mb-2 flex items-center gap-2">
                        <h4 className="flex-1 text-sm tracking-tight">{g.label}</h4>
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
                <h3 className="label-mono">Adicionar provedor</h3>
                <div className="flex flex-wrap gap-2">
                  {gruposInativos.map((g) => (
                    <button
                      key={g.id}
                      onClick={() => setAdicionando(adicionando === g.id ? null : g.id)}
                      className={`chip ${adicionando === g.id ? "chip-active" : ""}`}
                    >
                      + {g.label}
                    </button>
                  ))}
                  {gruposInativos.length === 0 && (
                    <p className="text-sm text-ink-3">
                      Todos os provedores desta categoria estão ativos.
                    </p>
                  )}
                </div>
                {gruposInativos
                  .filter((g) => g.id === adicionando)
                  .map((g) => (
                    <div key={g.id} className="card p-4">
                      <h4 className="mb-2 text-sm tracking-tight">{g.label}</h4>
                      {g.chaves.map((i) => (
                        <div key={i.chave}>{campoChave(i)}</div>
                      ))}
                    </div>
                  ))}
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
