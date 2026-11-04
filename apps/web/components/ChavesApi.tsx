"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, mensagemDaFalha } from "@/lib/api/client";
import type { components } from "@hub/api-client";

type Chave = components["schemas"]["ApiChaveRead"];
type ChaveCriada = components["schemas"]["ApiChaveCriada"];
type ChavesDaConta = components["schemas"]["ChavesDaConta"];

/** Data curta (dd/mm/aaaa hh:mm) ou "—". */
export function quando(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A chave completa, exibida UMA vez logo após a criação. */
export function ChaveRecemCriada({
  criada,
  aoFechar,
}: {
  criada: ChaveCriada;
  aoFechar: () => void;
}) {
  const [copiada, setCopiada] = useState(false);
  async function copiar() {
    try {
      await navigator.clipboard.writeText(criada.chave);
      setCopiada(true);
    } catch {
      setCopiada(false);
    }
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-warn/50 bg-warn/10 p-4 text-sm">
      <p className="font-medium text-ink">
        Copie a chave agora — ela não será mostrada de novo.
      </p>
      <code className="select-all break-all rounded bg-surface-2 px-2 py-1.5 font-mono text-xs text-ink">
        {criada.chave}
      </code>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={copiar} className="btn btn-primary">
          {copiada ? "Copiada" : "Copiar chave"}
        </button>
        <button type="button" onClick={aoFechar} className="btn">
          Já guardei
        </button>
      </div>
      <p className="text-xs text-ink-3">
        Envie no cabeçalho <code className="font-mono">X-API-Key</code> de cada
        requisição. Guia completo em <code className="font-mono">/api/v1/docs</code>.
      </p>
    </div>
  );
}

/** Uma linha da lista de chaves (conta e admin). */
export function LinhaChave({
  chave,
  aoRevogar,
  mostrarDono = false,
}: {
  chave: Chave;
  aoRevogar?: (c: Chave) => void;
  mostrarDono?: boolean;
}) {
  return (
    <li className="flex flex-wrap items-start gap-3 py-3 text-sm">
      <div className="flex min-w-0 flex-[1_1_14rem] flex-col gap-0.5">
        <p className="truncate font-medium text-ink">{chave.nome}</p>
        <p className="font-mono text-xs text-ink-3">{chave.prefixo}…</p>
        {mostrarDono && chave.usuario_email && (
          <p className="truncate text-xs text-ink-2">{chave.usuario_email}</p>
        )}
        <p className="text-xs text-ink-3">
          {chave.escopo === "escrita" ? "Leitura e escrita" : "Somente leitura"} ·{" "}
          {chave.limite_por_minuto}/min · {chave.limite_por_dia.toLocaleString("pt-BR")}/dia
        </p>
        <p className="text-xs text-ink-3">
          Hoje: {chave.uso_hoje.toLocaleString("pt-BR")} requisições
          {chave.bloqueadas_hoje > 0 &&
            ` (${chave.bloqueadas_hoje.toLocaleString("pt-BR")} barradas pelo limite)`}{" "}
          · 30 dias: {chave.uso_30_dias.toLocaleString("pt-BR")} · último uso{" "}
          {quando(chave.ultimo_uso_em)}
        </p>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <StatusBadge tone={chave.ativa ? "success" : "neutral"}>
          {chave.ativa ? "ativa" : chave.revogada_em ? "revogada" : "expirada"}
        </StatusBadge>
        {chave.ambiente === "test" && <StatusBadge tone="warning">sandbox</StatusBadge>}
        {chave.ativa && aoRevogar && (
          <button
            type="button"
            onClick={() => aoRevogar(chave)}
            className="text-xs text-danger hover:underline"
          >
            Revogar
          </button>
        )}
      </div>
    </li>
  );
}

/** Minha conta → "Integração via API" (§67): o cliente emite e revoga as
 * próprias chaves, se o plano incluir a API (no sandbox, sempre). */
export function ChavesApiConta() {
  const [dados, setDados] = useState<ChavesDaConta | null>(null);
  const [nome, setNome] = useState("");
  const [escopo, setEscopo] = useState<"leitura" | "escrita">("leitura");
  const [criada, setCriada] = useState<ChaveCriada | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/account/api-keys");
    if (!error && data) setDados(data);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setEnviando(true);
    try {
      const { data, error } = await api.POST("/api/v1/account/api-keys", {
        body: { nome, escopo },
      });
      if (error || !data) {
        const detail = (error as { detail?: unknown })?.detail;
        setMsg(
          typeof detail === "string" && detail.startsWith("LIMITE_PLANO_API_CHAVES")
            ? "Você atingiu o número máximo de chaves ativas do seu plano. Revogue uma para criar outra."
            : mensagemDaFalha(error, "Não foi possível criar a chave."),
        );
        return;
      }
      setCriada(data);
      setNome("");
      await carregar();
    } finally {
      setEnviando(false);
    }
  }

  async function revogar(c: Chave) {
    if (!window.confirm(`Revogar a chave "${c.nome}"? Sistemas que a usam param na hora.`)) {
      return;
    }
    await api.DELETE("/api/v1/account/api-keys/{chave_id}", {
      params: { path: { chave_id: c.id } },
    });
    await carregar();
  }

  if (dados === null) return null;
  // sem a API no plano e sem chave antiga: a seção não aparece
  if (!dados.disponivel && dados.chaves.length === 0) return null;

  const ativas = dados.chaves.filter((c) => c.ativa).length;
  const esgotado = ativas >= dados.maximo;

  return (
    <section className="card flex max-w-xl flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="label-mono">Integração via API</h2>
        {dados.sandbox && <StatusBadge tone="warning">ambiente de testes</StatusBadge>}
      </div>
      <p className="text-xs leading-relaxed text-ink-3">
        Conecte outro sistema (ERP, CRM, planilha) aos dados do seu território.
        Cada chave entra como a sua conta e só enxerga os seus municípios.
        {dados.sandbox
          ? " Aqui no sandbox os dados são fictícios e nada é enviado para fora."
          : ""}{" "}
        {ativas} de {dados.maximo} chave(s) ativa(s).
      </p>

      {criada && <ChaveRecemCriada criada={criada} aoFechar={() => setCriada(null)} />}

      {dados.disponivel ? (
        <form onSubmit={criar} className="flex flex-wrap items-end gap-2">
          <label className="flex min-w-0 flex-[1_1_12rem] flex-col gap-1.5">
            <span className="field-label">Nome da integração</span>
            <input
              required
              maxLength={120}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: ERP da prefeitura"
              className="input"
              disabled={esgotado}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Permissão</span>
            <select
              value={escopo}
              onChange={(e) => setEscopo(e.target.value as "leitura" | "escrita")}
              className="input"
              disabled={esgotado}
            >
              <option value="leitura">Somente leitura</option>
              <option value="escrita">Leitura e escrita</option>
            </select>
          </label>
          <button type="submit" disabled={enviando || esgotado} className="btn btn-primary">
            {enviando ? "Criando…" : "Criar chave"}
          </button>
        </form>
      ) : (
        <p className="text-sm text-ink-2">{dados.motivo}</p>
      )}
      {msg && <p className="text-sm text-danger">{msg}</p>}

      {dados.chaves.length > 0 && (
        <ul className="flex flex-col divide-y divide-hairline">
          {dados.chaves.map((c) => (
            <LinhaChave key={c.id} chave={c} aoRevogar={revogar} />
          ))}
        </ul>
      )}
    </section>
  );
}
