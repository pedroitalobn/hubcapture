"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StatCard } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import {
  api,
  baixarContatosVcf,
  importarContatosVcf,
} from "@/lib/api/client";

interface Valor {
  tipo?: string | null;
  valor: string;
}
interface Contato {
  id: string;
  nome: string;
  sobrenome?: string | null;
  organizacao?: string | null;
  cargo?: string | null;
  emails?: Valor[];
  telefones?: Valor[];
  tags?: string[];
  origem: string;
  municipio_ibge?: string | null;
}
interface Provedor {
  provedor: string;
  rotulo: string;
  tipo_auth: string;
  disponivel: boolean;
  instrucoes?: string | null;
}
interface Integracao {
  id: string;
  provedor: string;
  conta: string;
  status: string;
  direcao: string;
  ultima_sync_em?: string | null;
  ultimo_erro?: string | null;
  total_contatos: number;
  ativo: boolean;
}
interface SyncResultado {
  provedor: string;
  conta: string;
  status: string;
  importados: number;
  atualizados_local: number;
  exportados: number;
  atualizados_remoto: number;
  removidos_local: number;
  removidos_remoto: number;
  conflitos: number;
  erro?: string | null;
}

const STATUS_TONE: Record<string, BadgeTone> = {
  conectada: "success",
  expirada: "warning",
  erro: "danger",
  desconectada: "neutral",
};
const DIRECAO_LABEL: Record<string, string> = {
  bidirecional: "Nos dois sentidos",
  importar: "Só importar",
  exportar: "Só exportar",
};
const ORIGEM_LABEL: Record<string, string> = {
  manual: "Manual",
  google: "Google",
  microsoft: "Outlook",
  apple: "Apple",
  carddav: "CardDAV",
  vcard: "vCard",
};

function placar(r: SyncResultado): string {
  if (r.status === "erro") return r.erro ?? "falhou";
  const partes = [
    r.importados && `${r.importados} novos`,
    r.atualizados_local && `${r.atualizados_local} atualizados aqui`,
    r.exportados && `${r.exportados} enviados`,
    r.atualizados_remoto && `${r.atualizados_remoto} atualizados lá`,
    r.removidos_local && `${r.removidos_local} removidos aqui`,
    r.removidos_remoto && `${r.removidos_remoto} removidos lá`,
    r.conflitos && `${r.conflitos} conflitos mesclados`,
  ].filter(Boolean);
  return partes.length ? partes.join(" · ") : "já estava em dia";
}

function formatarQuando(iso?: string | null): string {
  if (!iso) return "nunca sincronizada";
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function ContatosPage() {
  const [contatos, setContatos] = useState<Contato[]>([]);
  const [provedores, setProvedores] = useState<Provedor[]>([]);
  const [integracoes, setIntegracoes] = useState<Integracao[]>([]);
  const [busca, setBusca] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [sincronizando, setSincronizando] = useState(false);
  const [conectando, setConectando] = useState<string | null>(null);
  const [editando, setEditando] = useState<Contato | null>(null);
  const [novo, setNovo] = useState(false);
  const arquivoRef = useRef<HTMLInputElement>(null);

  const carregarContatos = useCallback(async (termo: string) => {
    const { data } = await api.GET("/api/v1/contacts", {
      params: { query: termo ? { busca: termo } : {} },
    });
    setContatos((data as Contato[]) ?? []);
  }, []);

  const carregarIntegracoes = useCallback(async () => {
    const [{ data: provs }, { data: ints }] = await Promise.all([
      api.GET("/api/v1/integrations/contacts/providers"),
      api.GET("/api/v1/integrations/contacts"),
    ]);
    setProvedores((provs as Provedor[]) ?? []);
    setIntegracoes((ints as Integracao[]) ?? []);
  }, []);

  useEffect(() => {
    void (async () => {
      await Promise.all([carregarContatos(""), carregarIntegracoes()]);
      setCarregando(false);
    })();
  }, [carregarContatos, carregarIntegracoes]);

  // volta do consentimento OAuth (/integrations/callback redireciona para cá)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const conectado = params.get("conectado");
    const falha = params.get("erro");
    if (conectado) setMsg(`Conta ${conectado} conectada. Sincronize para começar.`);
    if (falha) setMsg(`Não foi possível conectar: ${falha}`);
    if (conectado || falha) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  async function conectarOauth(provedor: string) {
    setMsg(null);
    setConectando(provedor);
    const { data, error } = await api.POST(
      "/api/v1/integrations/contacts/{provedor}/authorize",
      { params: { path: { provedor }, query: {} } },
    );
    if (error || !data) {
      const detalhe = (error as { detail?: string } | undefined)?.detail;
      setMsg(detalhe ?? "Provedor indisponível — peça ao admin para configurar.");
      setConectando(null);
      return;
    }
    window.location.href = (data as { url: string }).url;
  }

  async function sincronizar(integracaoId?: string) {
    setMsg(null);
    setSincronizando(true);
    const resposta = integracaoId
      ? await api.POST("/api/v1/integrations/contacts/{integracao_id}/sync", {
          params: { path: { integracao_id: integracaoId } },
        })
      : await api.POST("/api/v1/integrations/contacts/sync", {});
    const bruto = resposta.data;
    const lista = (Array.isArray(bruto) ? bruto : [bruto]).filter(
      Boolean,
    ) as SyncResultado[];
    setMsg(
      resposta.error
        ? "Falha ao sincronizar."
        : lista.length === 0
          ? "Nenhuma agenda conectada ainda."
          : lista.map((r) => `${r.conta}: ${placar(r)}`).join(" | "),
    );
    await Promise.all([carregarContatos(busca), carregarIntegracoes()]);
    setSincronizando(false);
  }

  async function alterarDirecao(integracao: Integracao, direcao: string) {
    await api.PATCH("/api/v1/integrations/contacts/{integracao_id}", {
      params: { path: { integracao_id: integracao.id } },
      body: { direcao },
    });
    await carregarIntegracoes();
  }

  async function desconectar(integracao: Integracao) {
    if (
      !window.confirm(
        `Desconectar ${integracao.conta}? Os contatos já sincronizados continuam na agenda do Hub.`,
      )
    )
      return;
    await api.DELETE("/api/v1/integrations/contacts/{integracao_id}", {
      params: { path: { integracao_id: integracao.id } },
    });
    await carregarIntegracoes();
  }

  async function arquivar(contato: Contato) {
    if (!window.confirm(`Remover ${contato.nome} da agenda?`)) return;
    await api.DELETE("/api/v1/contacts/{contato_id}", {
      params: { path: { contato_id: contato.id } },
    });
    await carregarContatos(busca);
  }

  async function importar(e: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    if (!arquivo) return;
    try {
      const r = (await importarContatosVcf(arquivo)) as {
        importados: number;
        atualizados: number;
        ignorados: number;
      };
      setMsg(
        `Importação: ${r.importados} novos, ${r.atualizados} atualizados, ${r.ignorados} ignorados.`,
      );
      await carregarContatos(busca);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Falha ao importar");
    } finally {
      if (arquivoRef.current) arquivoRef.current.value = "";
    }
  }

  const porOrigem = useMemo(() => {
    const mapa: Record<string, number> = {};
    for (const c of contatos) mapa[c.origem] = (mapa[c.origem] ?? 0) + 1;
    return mapa;
  }, [contatos]);

  const naoConectados = provedores.filter(
    (p) => !integracoes.some((i) => i.provedor === p.provedor),
  );

  return (
    <>
      <header>
        <h1 className="text-2xl font-bold">Agenda de contatos</h1>
        <p className="text-sm text-ink-3">
          Sua rede de gabinetes, secretarias e técnicos — sincronizada com a agenda
          do seu celular (Google, Apple e Outlook).
        </p>
      </header>

      {msg && (
        <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-ink">
          {msg}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Contatos" value={String(contatos.length)} />
        <StatCard
          label="Agendas conectadas"
          value={String(integracoes.filter((i) => i.ativo).length)}
        />
        <StatCard label="Do Google" value={String(porOrigem.google ?? 0)} />
        <StatCard
          label="Do Outlook/Apple"
          value={String((porOrigem.microsoft ?? 0) + (porOrigem.apple ?? 0))}
        />
      </div>

      {/* ── Agendas conectadas ─────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Agendas conectadas</h2>
          <button
            onClick={() => void sincronizar()}
            disabled={sincronizando || integracoes.length === 0}
            className="btn btn-primary btn-sm"
          >
            {sincronizando ? "Sincronizando…" : "Sincronizar tudo"}
          </button>
        </div>

        {integracoes.length === 0 && (
          <p className="text-sm text-ink-3">
            Nenhuma conta conectada. Conecte uma abaixo — ou use o .vcf para levar
            os contatos na mão.
          </p>
        )}

        <ul className="flex flex-col divide-y divide-hairline">
          {integracoes.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{i.conta}</span>
                <span className="text-xs text-ink-3">
                  {ORIGEM_LABEL[i.provedor] ?? i.provedor} · {i.total_contatos}{" "}
                  vinculados · {formatarQuando(i.ultima_sync_em)}
                  {i.ultimo_erro ? ` · ${i.ultimo_erro.slice(0, 80)}` : ""}
                </span>
              </span>
              <select
                value={i.direcao}
                onChange={(e) => void alterarDirecao(i, e.target.value)}
                className="input text-xs"
              >
                {Object.entries(DIRECAO_LABEL).map(([valor, label]) => (
                  <option key={valor} value={valor}>
                    {label}
                  </option>
                ))}
              </select>
              <StatusBadge tone={STATUS_TONE[i.status] ?? "neutral"}>
                {i.status}
              </StatusBadge>
              <button
                onClick={() => void sincronizar(i.id)}
                disabled={sincronizando}
                className="text-xs text-ink-2 underline underline-offset-2 transition-colors hover:text-ink disabled:opacity-60"
              >
                Sincronizar
              </button>
              <button
                onClick={() => void desconectar(i)}
                className="text-xs text-ink-3 underline underline-offset-2 transition-colors hover:text-ink"
              >
                Desconectar
              </button>
            </li>
          ))}
        </ul>

        {naoConectados.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {naoConectados.map((p) =>
              p.tipo_auth === "oauth" ? (
                <button
                  key={p.provedor}
                  onClick={() => void conectarOauth(p.provedor)}
                  disabled={!p.disponivel || conectando === p.provedor}
                  title={
                    p.disponivel
                      ? (p.instrucoes ?? "")
                      : "Credenciais do app não configuradas (painel admin)"
                  }
                  className="btn btn-ghost btn-sm"
                >
                  Conectar {p.rotulo}
                </button>
              ) : (
                <button
                  key={p.provedor}
                  onClick={() => setConectando(p.provedor)}
                  className="btn btn-ghost btn-sm"
                >
                  Conectar {p.rotulo}
                </button>
              ),
            )}
          </div>
        )}

        {conectando &&
          provedores.find((p) => p.provedor === conectando)?.tipo_auth ===
            "senha_app" && (
            <FormularioSenhaApp
              provedor={provedores.find((p) => p.provedor === conectando)!}
              onCancelar={() => setConectando(null)}
              onConectado={async () => {
                setConectando(null);
                setMsg("Conta conectada. Sincronize para começar.");
                await carregarIntegracoes();
              }}
              onErro={(e) => setMsg(e)}
            />
          )}
      </section>

      {/* ── Agenda ─────────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Contatos</h2>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                setEditando(null);
                setNovo(true);
              }}
              className="btn btn-primary btn-sm"
            >
              Novo contato
            </button>
            <button
              onClick={() => void baixarContatosVcf()}
              className="btn btn-ghost btn-sm"
            >
              Exportar .vcf
            </button>
            <button
              onClick={() => arquivoRef.current?.click()}
              className="btn btn-ghost btn-sm"
            >
              Importar .vcf
            </button>
            <input
              ref={arquivoRef}
              type="file"
              accept=".vcf,text/vcard"
              onChange={(e) => void importar(e)}
              className="hidden"
            />
          </div>
        </div>

        <input
          value={busca}
          onChange={(e) => {
            setBusca(e.target.value);
            void carregarContatos(e.target.value);
          }}
          placeholder="Buscar por nome, órgão, cargo ou e-mail"
          className="input"
        />

        {(novo || editando) && (
          <FormularioContato
            contato={editando}
            onCancelar={() => {
              setNovo(false);
              setEditando(null);
            }}
            onSalvo={async () => {
              setNovo(false);
              setEditando(null);
              await carregarContatos(busca);
            }}
          />
        )}

        {carregando ? (
          <p className="text-sm text-ink-3">Carregando…</p>
        ) : contatos.length === 0 ? (
          <p className="text-sm text-ink-3">
            Nenhum contato ainda. Crie um, importe um .vcf ou conecte sua agenda.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-hairline">
            {contatos.map((c) => (
              <li key={c.id} className="flex items-start justify-between gap-3 py-3 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {[c.nome, c.sobrenome].filter(Boolean).join(" ")}
                  </span>
                  <span className="block truncate text-xs text-ink-3">
                    {[c.cargo, c.organizacao].filter(Boolean).join(" · ")}
                    {c.emails?.[0] ? ` · ${c.emails[0].valor}` : ""}
                    {c.telefones?.[0] ? ` · ${c.telefones[0].valor}` : ""}
                  </span>
                  {(c.tags ?? []).length > 0 && (
                    <span className="mt-1 flex flex-wrap gap-1">
                      {c.tags!.map((t) => (
                        <span
                          key={t}
                          className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-3"
                        >
                          {t}
                        </span>
                      ))}
                    </span>
                  )}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <StatusBadge tone="neutral">
                    {ORIGEM_LABEL[c.origem] ?? c.origem}
                  </StatusBadge>
                  <button
                    onClick={() => {
                      setNovo(false);
                      setEditando(c);
                    }}
                    className="text-xs text-ink-2 underline underline-offset-2 transition-colors hover:text-ink"
                  >
                    Editar
                  </button>
                  <button
                    onClick={() => void arquivar(c)}
                    className="text-xs text-ink-3 underline underline-offset-2 transition-colors hover:text-ink"
                  >
                    Remover
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

/** Conexão Apple/iCloud e CardDAV genérico (conta + senha de app). */
function FormularioSenhaApp({
  provedor,
  onCancelar,
  onConectado,
  onErro,
}: {
  provedor: Provedor;
  onCancelar: () => void;
  onConectado: () => Promise<void>;
  onErro: (msg: string) => void;
}) {
  const [conta, setConta] = useState("");
  const [senha, setSenha] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    const { error } = await api.POST(
      "/api/v1/integrations/contacts/{provedor}/app-password",
      {
        params: { path: { provedor: provedor.provedor } },
        body: {
          conta,
          senha_app: senha,
          base_url: baseUrl || undefined,
          direcao: "bidirecional",
        },
      },
    );
    setSalvando(false);
    if (error) {
      const detalhe = (error as { detail?: string }).detail;
      onErro(detalhe ?? "Não foi possível conectar.");
      return;
    }
    await onConectado();
  }

  return (
    <form
      onSubmit={enviar}
      className="card flex flex-col gap-3 p-4 text-sm"
    >
      <p className="text-xs text-ink-3">{provedor.instrucoes}</p>
      <label className="flex flex-col gap-1">
        Conta (Apple ID / usuário)
        <input
          value={conta}
          onChange={(e) => setConta(e.target.value)}
          required
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        Senha de app
        <input
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
          className="input"
        />
      </label>
      {provedor.provedor === "carddav" && (
        <label className="flex flex-col gap-1">
          URL do servidor CardDAV
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://nuvem.exemplo.br/remote.php/dav"
            required
            className="input"
          />
        </label>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={salvando}
          className="btn btn-primary btn-sm"
        >
          {salvando ? "Conectando…" : "Conectar"}
        </button>
        <button type="button" onClick={onCancelar} className="text-xs text-ink-3 underline underline-offset-2 transition-colors hover:text-ink">
          Cancelar
        </button>
      </div>
    </form>
  );
}

/** Criação/edição de contato (e-mails e telefones separados por vírgula). */
function FormularioContato({
  contato,
  onCancelar,
  onSalvo,
}: {
  contato: Contato | null;
  onCancelar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const [nome, setNome] = useState(contato?.nome ?? "");
  const [sobrenome, setSobrenome] = useState(contato?.sobrenome ?? "");
  const [organizacao, setOrganizacao] = useState(contato?.organizacao ?? "");
  const [cargo, setCargo] = useState(contato?.cargo ?? "");
  const [emails, setEmails] = useState(
    (contato?.emails ?? []).map((e) => e.valor).join(", "),
  );
  const [telefones, setTelefones] = useState(
    (contato?.telefones ?? []).map((t) => t.valor).join(", "),
  );
  const [tags, setTags] = useState((contato?.tags ?? []).join(", "));
  const [municipio, setMunicipio] = useState(contato?.municipio_ibge ?? "");
  const [salvando, setSalvando] = useState(false);

  function lista(texto: string): Valor[] {
    return texto
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean)
      .map((valor) => ({ valor }));
  }

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    const corpo = {
      nome,
      sobrenome: sobrenome || undefined,
      organizacao: organizacao || undefined,
      cargo: cargo || undefined,
      emails: lista(emails),
      telefones: lista(telefones),
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      municipio_ibge: municipio || undefined,
    };
    if (contato) {
      await api.PATCH("/api/v1/contacts/{contato_id}", {
        params: { path: { contato_id: contato.id } },
        body: corpo,
      });
    } else {
      await api.POST("/api/v1/contacts", { body: corpo });
    }
    setSalvando(false);
    await onSalvo();
  }

  return (
    <form
      onSubmit={enviar}
      className="grid gap-3 rounded-lg border border-hairline p-4 text-sm md:grid-cols-2"
    >
      <label className="flex flex-col gap-1">
        Nome*
        <input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          required
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        Sobrenome
        <input
          value={sobrenome}
          onChange={(e) => setSobrenome(e.target.value)}
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        Órgão / organização
        <input
          value={organizacao}
          onChange={(e) => setOrganizacao(e.target.value)}
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        Cargo
        <input
          value={cargo}
          onChange={(e) => setCargo(e.target.value)}
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        E-mails (separados por vírgula)
        <input
          value={emails}
          onChange={(e) => setEmails(e.target.value)}
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        Telefones (separados por vírgula)
        <input
          value={telefones}
          onChange={(e) => setTelefones(e.target.value)}
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        Etiquetas (vírgula)
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="gabinete, saude"
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1">
        Município (IBGE)
        <input
          value={municipio}
          onChange={(e) => setMunicipio(e.target.value)}
          maxLength={7}
          placeholder="3550308"
          className="input"
        />
      </label>
      <div className="flex gap-2 md:col-span-2">
        <button
          type="submit"
          disabled={salvando}
          className="btn btn-primary btn-sm"
        >
          {salvando ? "Salvando…" : contato ? "Salvar" : "Criar contato"}
        </button>
        <button type="button" onClick={onCancelar} className="text-xs text-ink-3 underline underline-offset-2 transition-colors hover:text-ink">
          Cancelar
        </button>
      </div>
    </form>
  );
}
