"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Skeleton } from "@/components/Skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

interface Opcao {
  chave: string;
  label: string;
  descricao?: string | null;
}

interface Opcoes {
  modulos: Opcao[];
  fontes: Opcao[];
  features: Opcao[];
}

interface Plano {
  id: string;
  nome: string;
  slug: string;
  descricao?: string | null;
  preco_mensal?: string | null;
  limites?: Record<string, unknown> | null;
  ativo: boolean;
}

/** Config editável de um plano — espelho do formato canônico do backend
 * (services/plano_gates.py, §39). null em modulos/fontes = sem restrição. */
interface ConfigPlano {
  municipios_max: number | null;
  membros_max: number | null;
  modulos: string[] | null;
  fontes: string[] | null;
  features: Record<string, boolean>;
}

function configDoPlano(p: Plano, opcoes: Opcoes): ConfigPlano {
  const lim = (p.limites ?? {}) as Record<string, unknown>;
  const int = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;

  let modulos: string[] | null = Array.isArray(lim.modulos)
    ? (lim.modulos as string[])
    : null;
  if (modulos === null) {
    // legado: bool de módulo no topo ("copiloto": false) exclui o módulo
    const excluidos = opcoes.modulos
      .map((m) => m.chave)
      .filter((chave) => lim[chave] === false);
    if (excluidos.length > 0)
      modulos = opcoes.modulos
        .map((m) => m.chave)
        .filter((chave) => !excluidos.includes(chave));
  }

  const features: Record<string, boolean> = {};
  const brutas = (lim.features ?? {}) as Record<string, unknown>;
  for (const f of opcoes.features)
    features[f.chave] = brutas[f.chave] !== false; // ausente = liberada

  return {
    municipios_max: int(lim.municipios_max ?? lim.municipios),
    membros_max: int(lim.membros_max ?? lim.membros),
    modulos,
    fontes: Array.isArray(lim.fontes) ? (lim.fontes as string[]) : null,
    features,
  };
}

export default function AdminPlanosPage() {
  const [planos, setPlanos] = useState<Plano[] | null>(null);
  const [opcoes, setOpcoes] = useState<Opcoes | null>(null);
  const [nome, setNome] = useState("");
  const [slug, setSlug] = useState("");
  const [preco, setPreco] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const [planosRes, opcoesRes] = await Promise.all([
      api.GET("/api/v1/plans", { params: { query: { incluir_inativos: true } } }),
      api.GET("/api/v1/plans/options", {}),
    ]);
    if (!planosRes.error) setPlanos((planosRes.data as Plano[]) ?? []);
    if (!opcoesRes.error) setOpcoes(opcoesRes.data as unknown as Opcoes);
    else setMsg("Acesso negado — é necessário ser administrador.");
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
      body: { nome, slug, preco_mensal: preco ? preco : null, ativo: true },
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
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Catálogo de planos atribuíveis aos usuários. A config de cada plano
          define os gates da assinatura: módulos liberados, fontes de dados,
          limite de municípios monitorados, membros convidáveis e features.
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
      {msg && <p className="text-sm text-danger">{msg}</p>}

      {planos === null || opcoes === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <section className="stagger flex flex-col gap-3">
          {planos.map((p) => (
            <PlanoCard key={p.id} plano={p} opcoes={opcoes} aoSalvar={carregar} />
          ))}
          {planos.length === 0 && (
            <p className="card p-5 text-sm text-ink-3">
              Nenhum plano cadastrado ainda.
            </p>
          )}
        </section>
      )}
    </>
  );
}

function PlanoCard({
  plano,
  opcoes,
  aoSalvar,
}: {
  plano: Plano;
  opcoes: Opcoes;
  aoSalvar: () => Promise<void>;
}) {
  const inicial = useMemo(() => configDoPlano(plano, opcoes), [plano, opcoes]);
  const [aberto, setAberto] = useState(false);
  const [cfg, setCfg] = useState<ConfigPlano>(inicial);
  const [preco, setPreco] = useState(plano.preco_mensal ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => setCfg(inicial), [inicial]);

  function alternarLista(campo: "modulos" | "fontes", chave: string) {
    setCfg((c) => {
      const todas = (campo === "modulos" ? opcoes.modulos : opcoes.fontes).map(
        (o) => o.chave
      );
      const atual = c[campo] ?? todas; // null = todos marcados
      const nova = atual.includes(chave)
        ? atual.filter((k) => k !== chave)
        : [...atual, chave];
      // marcar tudo de volta = sem restrição (null)
      return { ...c, [campo]: nova.length === todas.length ? null : nova };
    });
  }

  async function salvar(extra?: { ativo?: boolean }) {
    setSalvando(true);
    setErro(null);
    const { error } = await api.PATCH("/api/v1/plans/{plano_id}", {
      params: { path: { plano_id: plano.id } },
      body: {
        preco_mensal: preco === "" ? null : preco,
        ...extra,
        limites: {
          municipios_max: cfg.municipios_max,
          membros_max: cfg.membros_max,
          modulos: cfg.modulos,
          fontes: cfg.fontes,
          features: cfg.features,
        },
      },
    });
    setSalvando(false);
    if (error) {
      setErro("Falha ao salvar a config do plano.");
      return;
    }
    await aoSalvar();
  }

  const resumo: string[] = [];
  resumo.push(
    cfg.municipios_max == null
      ? "municípios ilimitados"
      : `${cfg.municipios_max} município(s)`
  );
  resumo.push(
    cfg.membros_max == null ? "membros ilimitados" : `${cfg.membros_max} membro(s)`
  );
  resumo.push(
    cfg.modulos == null ? "todos os módulos" : `${cfg.modulos.length} módulo(s)`
  );
  resumo.push(
    cfg.fontes == null ? "todas as fontes" : `${cfg.fontes.length} fonte(s)`
  );

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-48 flex-1">
          <div className="flex items-center gap-2 text-sm tracking-tight">
            {plano.nome} <span className="text-xs text-ink-3">/{plano.slug}</span>
            <StatusBadge tone={plano.ativo ? "success" : "neutral"}>
              {plano.ativo ? "ativo" : "inativo"}
            </StatusBadge>
          </div>
          <p className="mt-1 text-xs text-ink-3">{resumo.join(" · ")}</p>
        </div>
        <span className="tabular-nums text-sm">
          {formatBRL(plano.preco_mensal)}/mês
        </span>
        <button className="btn btn-ghost" onClick={() => setAberto((a) => !a)}>
          {aberto ? "Fechar" : "Configurar"}
        </button>
      </div>

      {aberto && (
        <div className="mt-4 flex flex-col gap-5 border-t border-hairline pt-4">
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Municípios (máx.)</span>
              <input
                type="number"
                min={0}
                value={cfg.municipios_max ?? ""}
                placeholder="ilimitado"
                onChange={(e) =>
                  setCfg((c) => ({
                    ...c,
                    municipios_max:
                      e.target.value === "" ? null : Number(e.target.value),
                  }))
                }
                className="input w-32"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Membros convidáveis (máx.)</span>
              <input
                type="number"
                min={0}
                value={cfg.membros_max ?? ""}
                placeholder="ilimitado"
                onChange={(e) =>
                  setCfg((c) => ({
                    ...c,
                    membros_max:
                      e.target.value === "" ? null : Number(e.target.value),
                  }))
                }
                className="input w-32"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Preço/mês</span>
              <input
                value={preco ?? ""}
                onChange={(e) => setPreco(e.target.value)}
                placeholder="99.90"
                className="input w-28"
              />
            </label>
          </div>

          <fieldset>
            <legend className="field-label mb-2">
              Módulos liberados{" "}
              <span className="normal-case text-ink-3">
                (todos marcados = sem restrição)
              </span>
            </legend>
            <div className="flex flex-wrap gap-2">
              {opcoes.modulos.map((m) => {
                const marcado = cfg.modulos == null || cfg.modulos.includes(m.chave);
                return (
                  <button
                    key={m.chave}
                    type="button"
                    title={m.descricao ?? undefined}
                    onClick={() => alternarLista("modulos", m.chave)}
                    className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                      marcado
                        ? "border-transparent bg-ink text-paper"
                        : "border-hairline text-ink-3 hover:text-ink"
                    }`}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset>
            <legend className="field-label mb-2">
              Fontes de dados liberadas{" "}
              <span className="normal-case text-ink-3">
                (todas marcadas = sem restrição)
              </span>
            </legend>
            <div className="flex flex-wrap gap-2">
              {opcoes.fontes.map((f) => {
                const marcado = cfg.fontes == null || cfg.fontes.includes(f.chave);
                return (
                  <button
                    key={f.chave}
                    type="button"
                    title={f.descricao ?? undefined}
                    onClick={() => alternarLista("fontes", f.chave)}
                    className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                      marcado
                        ? "border-transparent bg-ink text-paper"
                        : "border-hairline text-ink-3 hover:text-ink"
                    }`}
                  >
                    {f.label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset>
            <legend className="field-label mb-2">Features</legend>
            <div className="flex flex-col gap-2">
              {opcoes.features.map((f) => (
                <label
                  key={f.chave}
                  className="flex cursor-pointer items-center gap-2.5 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={cfg.features[f.chave] ?? true}
                    onChange={(e) =>
                      setCfg((c) => ({
                        ...c,
                        features: { ...c.features, [f.chave]: e.target.checked },
                      }))
                    }
                  />
                  <span>{f.label}</span>
                  {f.descricao && (
                    <span className="text-xs text-ink-3">{f.descricao}</span>
                  )}
                </label>
              ))}
            </div>
          </fieldset>

          {erro && <p className="text-sm text-danger">{erro}</p>}
          <div className="flex flex-wrap gap-3">
            <button
              className="btn btn-primary"
              disabled={salvando}
              onClick={() => salvar()}
            >
              {salvando ? "Salvando…" : "Salvar config"}
            </button>
            <button
              className="btn btn-ghost"
              disabled={salvando}
              onClick={() => salvar({ ativo: !plano.ativo })}
            >
              {plano.ativo ? "Desativar plano" : "Reativar plano"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
