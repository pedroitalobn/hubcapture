"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChaveRecemCriada, LinhaChave } from "@/components/ChavesApi";
import { api, mensagemDaFalha } from "@/lib/api/client";
import type { components } from "@hub/api-client";

type Chave = components["schemas"]["ApiChaveRead"];
type ChaveCriada = components["schemas"]["ApiChaveCriada"];

interface Usuario {
  id: string;
  email: string;
  nome?: string | null;
  is_superuser: boolean;
  is_active: boolean;
}

/** Admin → Chaves de API (§67): emitir chave para a conta de um parceiro,
 * com limites próprios, acompanhar o consumo e revogar. */
export default function AdminChavesApiPage() {
  const [chaves, setChaves] = useState<Chave[] | null>(null);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [usuarioId, setUsuarioId] = useState("");
  const [nome, setNome] = useState("");
  const [escopo, setEscopo] = useState<"leitura" | "escrita">("leitura");
  const [porMinuto, setPorMinuto] = useState("");
  const [porDia, setPorDia] = useState("");
  const [criada, setCriada] = useState<ChaveCriada | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [soAtivas, setSoAtivas] = useState(true);

  const carregar = useCallback(async () => {
    const [c, u] = await Promise.all([
      api.GET("/api/v1/admin/api-keys"),
      api.GET("/api/v1/admin/users", {}),
    ]);
    if (!c.error && c.data) setChaves(c.data);
    if (!u.error) setUsuarios(((u.data as Usuario[]) ?? []).filter((x) => !x.is_superuser));
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const visiveis = useMemo(
    () => (chaves ?? []).filter((c) => !soAtivas || c.ativa),
    [chaves, soAtivas],
  );

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setEnviando(true);
    try {
      const { data, error } = await api.POST("/api/v1/admin/api-keys", {
        body: {
          usuario_id: usuarioId,
          nome,
          escopo,
          limite_por_minuto: porMinuto ? Number(porMinuto) : null,
          limite_por_dia: porDia ? Number(porDia) : null,
        },
      });
      if (error || !data) {
        setMsg(mensagemDaFalha(error, "Não foi possível criar a chave."));
        return;
      }
      setCriada(data);
      setNome("");
      setPorMinuto("");
      setPorDia("");
      await carregar();
    } finally {
      setEnviando(false);
    }
  }

  async function revogar(c: Chave) {
    if (!window.confirm(`Revogar "${c.nome}" (${c.usuario_email})? O sistema do parceiro para na hora.`)) {
      return;
    }
    await api.DELETE("/api/v1/admin/api-keys/{chave_id}", {
      params: { path: { chave_id: c.id } },
    });
    await carregar();
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl">Chaves de API</h1>
        <p className="max-w-2xl text-sm text-ink-2">
          Contas de parceiros acessam os dados do próprio território pela API, com a
          chave no cabeçalho <code className="font-mono">X-API-Key</code>. Os limites
          por minuto e por dia vêm do plano da conta; preencha abaixo só para
          sobrepor numa chave específica. Contas de administração não recebem chave.
        </p>
      </header>

      <section className="card flex max-w-3xl flex-col gap-4 p-6">
        <h2 className="label-mono">Nova chave</h2>
        {criada && <ChaveRecemCriada criada={criada} aoFechar={() => setCriada(null)} />}
        <form onSubmit={criar} className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 sm:col-span-2">
            <span className="field-label">Conta do parceiro</span>
            <select
              required
              value={usuarioId}
              onChange={(e) => setUsuarioId(e.target.value)}
              className="input"
            >
              <option value="">Escolha a conta…</option>
              {usuarios
                .filter((u) => u.is_active)
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nome ? `${u.nome} — ${u.email}` : u.email}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Nome da integração</span>
            <input
              required
              maxLength={120}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: CRM da consultoria"
              className="input"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Permissão</span>
            <select
              value={escopo}
              onChange={(e) => setEscopo(e.target.value as "leitura" | "escrita")}
              className="input"
            >
              <option value="leitura">Somente leitura</option>
              <option value="escrita">Leitura e escrita</option>
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Limite por minuto (opcional)</span>
            <input
              type="number"
              min={1}
              value={porMinuto}
              onChange={(e) => setPorMinuto(e.target.value)}
              placeholder="do plano"
              className="input"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Limite por dia (opcional)</span>
            <input
              type="number"
              min={1}
              value={porDia}
              onChange={(e) => setPorDia(e.target.value)}
              placeholder="do plano"
              className="input"
            />
          </label>
          <div className="sm:col-span-2">
            <button type="submit" disabled={enviando || !usuarioId} className="btn btn-primary">
              {enviando ? "Criando…" : "Criar chave"}
            </button>
          </div>
        </form>
        {msg && <p className="text-sm text-danger">{msg}</p>}
      </section>

      <section className="card flex max-w-3xl flex-col gap-2 p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="label-mono">Chaves emitidas</h2>
          <label className="flex items-center gap-2 text-xs text-ink-2">
            <input
              type="checkbox"
              checked={soAtivas}
              onChange={(e) => setSoAtivas(e.target.checked)}
            />
            Só as ativas
          </label>
        </div>
        {chaves === null ? (
          <p className="text-sm text-ink-3">Carregando…</p>
        ) : visiveis.length === 0 ? (
          <p className="text-sm text-ink-3">Nenhuma chave {soAtivas ? "ativa" : "emitida"}.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-hairline">
            {visiveis.map((c) => (
              <LinhaChave key={c.id} chave={c} aoRevogar={revogar} mostrarDono />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
