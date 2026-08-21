"use client";

import { useCallback, useEffect, useState } from "react";
import { Skeleton } from "@/components/Skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import {
  type ArquivoSiconv,
  type CatalogoSiconv,
  carregarSiconv,
  catalogoSiconv,
} from "@/lib/api/client";

/**
 * Pacote de dados abertos do SIconv — transferências discricionárias e legais.
 *
 * A fonte NÃO publica consulta por município para este eixo: a base sai inteira,
 * um ZIP por tabela do modelo. Esta tela é a operação disso — ver quais arquivos
 * a fonte está publicando agora (nome e tamanho reais, sondados ao vivo) e
 * mandar carregar sem esperar a janela da madrugada.
 */

function tamanhoLegivel(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "—";
  const unidades = ["B", "KB", "MB", "GB"];
  let valor = bytes;
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i += 1;
  }
  return `${valor.toFixed(valor >= 10 || i === 0 ? 0 : 1)} ${unidades[i]}`;
}

function dataBr(iso?: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 16).replace("T", " ");
}

export default function AdminSiconvPage() {
  const [catalogo, setCatalogo] = useState<CatalogoSiconv | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [selecionadas, setSelecionadas] = useState<string[]>([]);
  const [disparando, setDisparando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      setCatalogo(await catalogoSiconv());
    } catch (e) {
      setErro(e instanceof Error ? e.message : "erro desconhecido");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const alternar = (tabela: string) =>
    setSelecionadas((atual) =>
      atual.includes(tabela) ? atual.filter((t) => t !== tabela) : [...atual, tabela],
    );

  const disparar = useCallback(async () => {
    setDisparando(true);
    setMsg(null);
    try {
      const r = await carregarSiconv(selecionadas);
      setMsg(`✓ ${r.detalhe} — tabelas: ${r.tabelas.join(", ")}`);
    } catch (e) {
      setMsg(`Falha: ${e instanceof Error ? e.message : "erro desconhecido"}`);
    } finally {
      setDisparando(false);
    }
  }, [selecionadas]);

  const daCarga = (a: ArquivoSiconv) => catalogo?.tabelas_da_carga.includes(a.tabela);

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Pacote SIconv (discricionárias e legais)</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-2">
            A fonte não publica consulta por município para este eixo — a base sai
            inteira, um arquivo por tabela. Aqui está o que a fonte publica{" "}
            <em>agora</em> (nome e tamanho reais) e o disparo da carga que alimenta
            as propostas, emendas e empenhos do painel.
          </p>
        </div>
        <button onClick={carregar} disabled={carregando} className="btn btn-ghost">
          {carregando ? "Sondando…" : "Sondar de novo"}
        </button>
      </header>

      {erro && (
        <p className="card border border-danger/30 bg-danger/5 p-4 text-sm text-danger">{erro}</p>
      )}

      {carregando && !catalogo ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-72" />
        </div>
      ) : catalogo ? (
        <>
          <section className="stagger grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="card flex flex-col gap-1 p-5">
              <span className="label-mono">Escopo das propostas</span>
              <span className="text-lg tracking-tight">{catalogo.escopo_propostas}</span>
              <span className="text-xs text-ink-3">
                {catalogo.escopo_propostas === "nacional"
                  ? "O país inteiro entra no banco — milhões de linhas."
                  : "Só os municípios monitorados. Mude em Providers & Config → siconv_propostas_escopo."}
              </span>
            </div>
            <div className="card flex flex-col gap-1 p-5">
              <span className="label-mono">Municípios monitorados</span>
              <span className="text-lg tracking-tight">{catalogo.municipios_monitorados}</span>
              <span className="text-xs text-ink-3">
                {catalogo.municipios_monitorados === 0
                  ? "Sem território, a carga de propostas não grava nada."
                  : "É este o recorte da carga no escopo território."}
              </span>
            </div>
            <div className="card flex flex-col gap-1 p-5">
              <span className="label-mono">Tabelas da carga diária</span>
              <span className="text-sm tracking-tight">
                {catalogo.tabelas_da_carga.join(", ")}
              </span>
              <span className="text-xs text-ink-3 break-all">{catalogo.base_url}</span>
            </div>
          </section>

          <section className="card anim-fade-up p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-medium">Carregar agora</h2>
                <p className="mt-0.5 text-xs text-ink-2">
                  Sem seleção, roda o mesmo recorte da carga agendada. São centenas
                  de MB por arquivo: leva minutos e roda em segundo plano.
                </p>
              </div>
              <button onClick={disparar} disabled={disparando} className="btn btn-primary">
                {disparando
                  ? "Disparando…"
                  : selecionadas.length
                    ? `Carregar ${selecionadas.length} arquivo(s)`
                    : "Carregar tudo da carga diária"}
              </button>
            </div>
            {msg && <p className="mt-3 text-xs text-ink-2">{msg}</p>}
          </section>

          <section className="card anim-fade-up overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-hairline text-left label-mono">
                  <th className="px-5 py-3">Carregar</th>
                  <th className="px-3 py-3">Tabela</th>
                  <th className="px-3 py-3">Arquivo na fonte</th>
                  <th className="px-3 py-3">Estado</th>
                  <th className="px-3 py-3">Tamanho</th>
                  <th className="px-3 py-3">Download</th>
                </tr>
              </thead>
              <tbody>
                {catalogo.arquivos.map((a) => (
                  <tr key={a.tabela} className="border-b border-hairline/60 last:border-0">
                    <td className="px-5 py-3">
                      <input
                        type="checkbox"
                        aria-label={`carregar ${a.tabela}`}
                        checked={selecionadas.includes(a.tabela)}
                        onChange={() => alternar(a.tabela)}
                        disabled={!a.disponivel}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs">{a.tabela}</span>
                        {daCarga(a) && (
                          <StatusBadge tone="success">na carga diária</StatusBadge>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-ink-3">{a.descricao}</p>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-ink-2">{a.nome ?? "—"}</td>
                    <td className="px-3 py-3">
                      <StatusBadge tone={a.disponivel ? "success" : "danger"}>
                        {a.disponivel ? "publicado" : "indisponível"}
                      </StatusBadge>
                      {a.erro && <p className="mt-1 max-w-xs text-xs text-ink-3">{a.erro}</p>}
                    </td>
                    <td className="px-3 py-3 text-xs text-ink-2">{tamanhoLegivel(a.tamanho)}</td>
                    <td className="px-3 py-3">
                      {a.url ? (
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs underline decoration-dotted"
                        >
                          baixar ↗
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="card anim-fade-up overflow-x-auto">
            <h2 className="px-5 pt-4 text-sm font-medium">Últimas cargas</h2>
            <table className="mt-2 w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-hairline text-left label-mono">
                  <th className="px-5 py-3">Início</th>
                  <th className="px-3 py-3">Fim</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Registros</th>
                  <th className="px-3 py-3">Erro</th>
                </tr>
              </thead>
              <tbody>
                {catalogo.ultimas_cargas.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-4 text-xs text-ink-3">
                      Nenhuma carga registrada ainda.
                    </td>
                  </tr>
                ) : (
                  catalogo.ultimas_cargas.map((c, i) => (
                    <tr key={i} className="border-b border-hairline/60 last:border-0">
                      <td className="px-5 py-3 text-xs">{dataBr(c.iniciado_em)}</td>
                      <td className="px-3 py-3 text-xs">{dataBr(c.finalizado_em)}</td>
                      <td className="px-3 py-3">
                        <StatusBadge tone={c.status === "ok" ? "success" : "danger"}>
                          {c.status}
                        </StatusBadge>
                      </td>
                      <td className="px-3 py-3 text-xs">{c.registros}</td>
                      <td className="px-3 py-3 max-w-md text-xs text-ink-3">{c.erro ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </>
  );
}
