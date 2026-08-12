"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { ModuloGate } from "@/components/ModuloGate";
import { municipioPrincipal, recortarTexto } from "@/lib/format";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";

type Alerta = {
  id: string;
  proposta_id?: string | null;
  tipo?: string | null;
  payload?: Record<string, unknown> | null;
  lido: boolean;
  created_at: string;
};

type Busca = {
  id: string;
  municipio_ibge: string;
  area?: string | null;
  fonte?: string | null;
  ativo: boolean;
  canais?: string[] | null;
  ultimo_alerta_em?: string | null;
};

const TIPO_LABEL: Record<string, string> = {
  status: "Mudança de status",
  prazo: "Prazo alterado",
  pendencia: "Nova pendência",
  nova_proposta: "Nova proposta",
  oportunidade: "Oportunidade",
};

const AREAS = [
  "saude",
  "educacao",
  "infraestrutura",
  "assistencia_social",
  "cultura",
  "esporte",
  "meio_ambiente",
  "agricultura",
];

function descricao(a: Alerta): string {
  const p = (a.payload ?? {}) as Record<string, string | undefined>;
  // município pelo nome; sem nome, o código vai rotulado (seção 23)
  const municipio = p.municipio_ibge
    ? municipioPrincipal({
        municipio_nome: p.municipio_nome,
        municipio_ibge: p.municipio_ibge,
        uf: p.uf,
      })
    : (p.municipio_nome ?? "");
  if (a.tipo === "nova_proposta")
    // mesmo teto de 80 do feed: o título do alerta é o `objeto` da fonte e,
    // inteiro, empurrava a fonte e o município para o fim de um parágrafo
    return `${recortarTexto(p.titulo, 80).trecho || "Nova proposta"} (${p.fonte ?? ""}) em ${municipio}`;
  if (a.tipo === "oportunidade")
    return `Recursos da fonte ${p.fonte ?? "?"} recebidos em ${municipio} sem proposta de captação cadastrada`;
  return `Proposta atualizada${municipio ? ` em ${municipio}` : ""}`;
}

export default function AlertasPage() {
  return (
    <ModuloGate modulo="alertas" titulo="Alertas">
      <AlertasConteudo />
    </ModuloGate>
  );
}

function AlertasConteudo() {
  // território do perfil + recorte ativo no painel (trilho lateral)
  const { municipios, selecionados } = useTerritorio();
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [buscas, setBuscas] = useState<Busca[]>([]);
  const [soNaoLidos, setSoNaoLidos] = useState(true);
  const [varrendo, setVarrendo] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // formulário de nova busca (monitorar futuras propostas)
  const [novoIbge, setNovoIbge] = useState("");
  const [novaArea, setNovaArea] = useState("");
  const [novosCanais, setNovosCanais] = useState<string[]>(["painel"]);

  const carregar = useCallback(async () => {
    const [al, bu] = await Promise.all([
      api.GET("/api/v1/alerts", {
        params: {
          query: {
            nao_lidos: soNaoLidos,
            municipio: paramMunicipio(selecionados),
          },
        },
      }),
      api.GET("/api/v1/monitors/searches"),
    ]);
    if (al.data) setAlertas(al.data as Alerta[]);
    if (bu.data) setBuscas((bu.data as Busca[]).filter((b) => b.ativo));
  }, [soNaoLidos, selecionados]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // varredura ao abrir: detecta novas propostas + oportunidades e despacha
  useEffect(() => {
    void (async () => {
      await api.POST("/api/v1/alerts/scan");
      await carregar();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function varrer() {
    setVarrendo(true);
    const { data } = await api.POST("/api/v1/alerts/scan");
    const n = (data as { alertas_criados?: number } | undefined)?.alertas_criados ?? 0;
    setMsg(
      n > 0
        ? `${n} novo(s) alerta(s) encontrado(s).`
        : "Nada novo desde a última varredura.",
    );
    await carregar();
    setVarrendo(false);
  }

  async function marcarLido(id: string) {
    await api.POST("/api/v1/alerts/{alerta_id}/read", {
      params: { path: { alerta_id: id } },
    });
    await carregar();
  }

  async function criarBusca(e: React.FormEvent) {
    e.preventDefault();
    const ibge = novoIbge || municipios[0]?.ibge;
    if (!ibge) return;
    const { error } = await api.POST("/api/v1/monitors/searches", {
      body: {
        municipio_ibge: ibge,
        area: novaArea || null,
        canais: novosCanais,
      },
    });
    if (!error) {
      setMsg("Monitoramento de futuras propostas ativado.");
      setNovaArea("");
      await carregar();
    }
  }

  async function removerBusca(id: string) {
    await api.DELETE("/api/v1/monitors/searches/{busca_id}", {
      params: { path: { busca_id: id } },
    });
    await carregar();
  }

  function nomeMunicipio(ibge: string): string {
    const m = municipios.find((x) => x.ibge === ibge);
    return m?.nome ? `${m.nome}${m.uf ? `/${m.uf}` : ""}` : ibge;
  }

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Alertas</h1>
          <p className="mt-1 text-sm text-ink-2">
            Mudanças nas propostas monitoradas, novas propostas do território e
            oportunidades não aproveitadas.
          </p>
        </div>
        <button onClick={varrer} disabled={varrendo} className="btn btn-primary">
          {varrendo ? "Varrendo…" : "Varrer agora"}
        </button>
      </header>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      {/* monitorar FUTURAS propostas */}
      <section className="card p-5">
        <h2 className="label-mono mb-3">Monitorar futuras propostas</h2>
        <p className="mb-3 text-sm text-ink-2">
          Vigie um município (e, se quiser, uma área): quando uma proposta nova
          aparecer nas fontes, você recebe alerta no painel — e por e-mail ou
          WhatsApp, se marcar os canais.
        </p>
        <form onSubmit={criarBusca} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="field-label">Município</span>
            <select
              value={novoIbge}
              onChange={(e) => setNovoIbge(e.target.value)}
              className="input w-52"
            >
              {municipios.map((m) => (
                <option key={m.ibge} value={m.ibge}>
                  {m.nome ?? m.ibge}
                  {m.uf ? `/${m.uf}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">Área (opcional)</span>
            <select
              value={novaArea}
              onChange={(e) => setNovaArea(e.target.value)}
              className="input w-44"
            >
              <option value="">todas</option>
              {AREAS.map((a) => (
                <option key={a} value={a}>
                  {a.replace("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <div className="flex gap-3 pb-2 text-sm">
            {(
              [
                ["painel", "Painel"],
                ["email", "E-mail"],
                ["wpp", "WhatsApp"],
              ] as const
            ).map(([valor, rotulo]) => (
              <label key={valor} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={novosCanais.includes(valor)}
                  disabled={valor === "painel"}
                  onChange={(e) =>
                    setNovosCanais((prev) =>
                      e.target.checked
                        ? [...prev, valor]
                        : prev.filter((c) => c !== valor),
                    )
                  }
                />
                {rotulo}
              </label>
            ))}
          </div>
          <button type="submit" className="btn btn-primary">
            Monitorar
          </button>
        </form>

        {buscas.length > 0 && (
          <ul className="mt-4 space-y-2">
            {buscas.map((b) => (
              <li
                key={b.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-hairline px-3 py-2 text-sm"
              >
                <span>
                  {nomeMunicipio(b.municipio_ibge)}
                  {b.area ? ` · ${b.area.replace("_", " ")}` : " · todas as áreas"}
                  <span className="ml-2 font-mono text-[11px] text-ink-3">
                    {(b.canais ?? ["painel"]).join(" + ")}
                  </span>
                </span>
                <button
                  onClick={() => removerBusca(b.id)}
                  className="btn btn-ghost btn-sm"
                >
                  Parar
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* central de alertas */}
      <section className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={soNaoLidos}
            onChange={(e) => setSoNaoLidos(e.target.checked)}
          />
          Só não lidos
        </label>
      </section>

      {alertas.length === 0 ? (
        <p className="text-ink-3">
          Nenhum alerta {soNaoLidos ? "não lido" : ""} por aqui. Monitore uma
          proposta-chave ou um município acima.
        </p>
      ) : (
        <ul className="space-y-2">
          {alertas.map((a) => (
            <li
              key={a.id}
              className={`card flex flex-wrap items-center justify-between gap-3 p-4 ${
                a.lido ? "opacity-60" : ""
              }`}
            >
              <div>
                <p className="text-sm font-medium">
                  <span
                    className={`mr-2 rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${
                      a.tipo === "oportunidade"
                        ? "bg-warn/10 text-warn"
                        : a.tipo === "nova_proposta"
                          ? "bg-ok/10 text-ok"
                          : "bg-surface-2 text-ink-2"
                    }`}
                  >
                    {TIPO_LABEL[a.tipo ?? ""] ?? a.tipo}
                  </span>
                  {descricao(a)}
                </p>
                <p className="mt-0.5 font-mono text-[11px] text-ink-3">
                  {new Date(a.created_at).toLocaleString("pt-BR")}
                </p>
              </div>
              <div className="flex gap-2">
                {a.proposta_id && (
                  <Link
                    href={`/panel/funding/${a.proposta_id}`}
                    className="btn btn-ghost btn-sm"
                  >
                    Abrir proposta
                  </Link>
                )}
                {!a.lido && (
                  <button
                    onClick={() => marcarLido(a.id)}
                    className="btn btn-ghost btn-sm"
                  >
                    Marcar lido
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
