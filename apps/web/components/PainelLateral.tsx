"use client";

/**
 * Coluna lateral do Meu painel — a trilha do que exige ATENÇÃO hoje.
 *
 * O painel era uma única coluna que empilhava tudo em profundidade: os prazos
 * viviam só no Copiloto, os alertas eram uma faixa de aviso com um número e as
 * notícias caíam no rodapé, depois de rolar o feed inteiro. Na disposição de
 * duas colunas do preview aprovado, a esquerda é o QUE ACONTECEU (números,
 * gráfico, feed) e a direita é o QUE VENCE, o QUE MUDOU e o que o governo
 * publicou — três caixas curtas, sempre visíveis, cada uma com link para a
 * tela cheia.
 *
 * Cada caixa é best-effort: fonte fora do ar ou módulo desligado some da
 * coluna em silêncio, sem derrubar o painel (a coluna é acessória por
 * definição — o dado principal está à esquerda).
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Caixa } from "@/components/kit";
import { api } from "@/lib/api/client";
import { descreverAlerta, alertaTipoLabel, type Alerta } from "@/lib/alertas";
import {
  diasAte,
  formatDate,
  haQuantoTempo,
  humanizarCaixa,
  municipioPrincipal,
  recortarTexto,
  tomPrazo,
} from "@/lib/format";
import { paramMunicipio } from "@/lib/territorio";

/** Janela padrão da trilha de prazos — o bimestre que o gestor consegue agir. */
const JANELA_DIAS = 60;
const MAX_ITENS = 5;

interface PropostaPrazo {
  proposta: {
    id: string;
    titulo?: string | null;
    numero_proposta?: string | null;
    municipio_nome?: string | null;
    municipio_ibge?: string | null;
    uf?: string | null;
    prazo_final?: string | null;
    dias_restantes?: number | null;
  };
  prazos_na_janela: { tipo?: string; data_limite?: string }[];
}

interface Noticia {
  titulo: string;
  url: string;
  data?: string | null;
  resumo?: string | null;
}

/* ────────────────────────────────────────────────── Prazos próximos ───── */

export function CardPrazos({ municipios }: { municipios: string[] }) {
  const [itens, setItens] = useState<PropostaPrazo[] | null>(null);

  useEffect(() => {
    void api
      .GET("/api/v1/proposals/deadlines", {
        params: {
          query: { dias: JANELA_DIAS, municipio: paramMunicipio(municipios) },
        },
      })
      .then(({ data }) => setItens(Array.isArray(data) ? data : []));
  }, [municipios]);

  // ainda carregando, ou território sem nenhum prazo na janela: a caixa não
  // se desenha — card vazio na coluna lateral só ocupa altura
  if (!itens || itens.length === 0) return null;

  return (
    <Caixa
      titulo="Prazos próximos"
      sub={`o que vence nos próximos ${JANELA_DIAS} dias`}
    >
      <div className="flex flex-col">
        {itens.slice(0, MAX_ITENS).map((p) => {
          const limite =
            p.prazos_na_janela[0]?.data_limite ?? p.proposta.prazo_final;
          const dias = p.proposta.dias_restantes ?? diasAte(limite);
          const tom = tomPrazo(dias ?? limite);
          return (
            <div key={p.proposta.id} className="tl-item">
              <div
                className={`tl-days ${
                  tom === "danger"
                    ? "tl-danger"
                    : tom === "warn"
                      ? "tl-warn"
                      : "tl-ok"
                }`}
              >
                {dias === null || dias === undefined ? (
                  <b>—</b>
                ) : dias < 0 ? (
                  <b>vencido</b>
                ) : (
                  <>
                    <b className="text-ink">{dias}</b>{" "}
                    <span>{dias === 1 ? "dia" : "dias"}</span>
                  </>
                )}
              </div>
              <div className="tl-body">
                <Link
                  href={`/panel/funding/${p.proposta.id}`}
                  className="block text-[13px] leading-snug text-ink hover:text-brand"
                >
                  {recortarTexto(humanizarCaixa(p.proposta.titulo), 70).trecho ||
                    p.proposta.numero_proposta ||
                    "Proposta"}
                </Link>
                <p className="mt-0.5 text-[11.5px] text-ink-3">
                  {[
                    p.prazos_na_janela[0]?.tipo,
                    formatDate(limite),
                    municipioPrincipal(p.proposta),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Caixa>
  );
}

/* ───────────────────────────────────────────────── Alertas recentes ───── */

export function CardAlertas({
  municipios,
  ativo,
}: {
  municipios: string[];
  /** Módulo `alertas` ligado no plano/plataforma (§29/§39). */
  ativo: boolean;
}) {
  const [alertas, setAlertas] = useState<Alerta[] | null>(null);

  useEffect(() => {
    if (!ativo) return;
    void api
      .GET("/api/v1/alerts", {
        params: {
          query: { nao_lidos: true, municipio: paramMunicipio(municipios) },
        },
      })
      .then(({ data }) => setAlertas(Array.isArray(data) ? data : []));
  }, [municipios, ativo]);

  if (!ativo || !alertas || alertas.length === 0) return null;

  return (
    <Caixa
      titulo="Alertas recentes"
      sub={`${alertas.length} ${alertas.length === 1 ? "não lido" : "não lidos"}`}
      acoes={
        <Link href="/panel/alerts" className="link-soft text-[12px]">
          Ver todos →
        </Link>
      }
      corpoRente
    >
      <ul className="flex flex-col divide-y divide-hairline">
        {alertas.slice(0, MAX_ITENS).map((a) => {
          const p = (a.payload ?? {}) as Record<string, string | undefined>;
          const destino = a.proposta_id
            ? `/panel/funding/${a.proposta_id}`
            : "/panel/alerts";
          return (
            <li key={a.id}>
              <Link href={destino} className="block px-5 py-3 row-interactive">
                <p className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--fill-accent)]" aria-hidden />
                  <span className="truncate text-[12px] font-semibold uppercase tracking-[0.04em] text-ink-2">
                    {alertaTipoLabel(a.tipo)}
                  </span>
                  <span className="ml-auto shrink-0 text-[11px] text-ink-3">
                    {haQuantoTempo(a.created_at)}
                  </span>
                </p>
                <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-ink">
                  {recortarTexto(descreverAlerta(a), 110).trecho}
                </p>
                {(p.titulo || p.municipio_nome || p.municipio_ibge) && (
                  <p className="mt-0.5 truncate text-[11.5px] text-ink-3">
                    {[
                      recortarTexto(humanizarCaixa(p.titulo), 60).trecho,
                      p.municipio_ibge || p.municipio_nome
                        ? municipioPrincipal({
                            municipio_nome: p.municipio_nome,
                            municipio_ibge: p.municipio_ibge,
                            uf: p.uf,
                          })
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </Caixa>
  );
}

/* ──────────────────────────────────────────────── Painel informativo ──── */

export function CardNoticias({ noticias }: { noticias: Noticia[] }) {
  if (noticias.length === 0) return null;
  return (
    <Caixa titulo="Painel informativo" sub="TransfereGov · notícias oficiais">
      <div className="flex flex-col divide-y divide-hairline">
        {noticias.slice(0, 4).map((n, i) => (
          <a
            key={i}
            href={n.url}
            target="_blank"
            rel="noreferrer"
            className="news-item"
          >
            <span className="min-w-0">
              <b>{n.titulo} ↗</b>
              <small>
                {[n.resumo ? recortarTexto(n.resumo, 60).trecho : null, formatDate(n.data)]
                  .filter(Boolean)
                  .join(" · ") || "gov.br"}
              </small>
            </span>
          </a>
        ))}
      </div>
    </Caixa>
  );
}
