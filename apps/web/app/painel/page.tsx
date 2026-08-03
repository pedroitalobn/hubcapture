"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonCards, SkeletonList } from "@/components/Skeleton";
import { StatCard, StatRow } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { Button, Card, cx } from "@/components/ui";
import { alertaTipoLabel, descreverAlerta, type Alerta } from "@/lib/alertas";
import { api } from "@/lib/api/client";
import { diasAte, formatBRLCompact, haQuantoTempo, prazoLabel } from "@/lib/format";
import {
  fonteCurta,
  prazoMaisProximo,
  resumirCaptacao,
  tituloProposta,
  type Proposta,
} from "@/lib/proposta";

interface Dimensao {
  chave: string;
  titulo: string;
  total: number;
  destaque?: string | null;
  href: string;
}
interface Municipio {
  ibge: string;
  nome?: string | null;
  uf?: string | null;
}
interface VisaoGeral {
  papel?: string | null;
  municipios: Municipio[];
  areas: string[];
  dimensoes: Dimensao[];
}
export default function MeuPainelPage() {
  const [visao, setVisao] = useState<VisaoGeral | null>(null);
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      const [vg, props, alrt] = await Promise.all([
        api.GET("/api/v1/perfil/visao-geral"),
        api.GET("/api/v1/propostas", { params: { query: {} } }),
        api.GET("/api/v1/alertas", { params: { query: { nao_lidos: true } } }),
      ]);
      if (vg.data) setVisao(vg.data as VisaoGeral);
      if (Array.isArray(props.data)) setPropostas(props.data as Proposta[]);
      if (Array.isArray(alrt.data)) setAlertas(alrt.data as Alerta[]);
      setLoading(false);
    })();
  }, []);

  const resumo = useMemo(() => resumirCaptacao(propostas), [propostas]);

  /** Prazos e pendências ordenados pelo relógio — o que exige ação primeiro. */
  const agenda = useMemo(() => {
    return propostas
      .map((p) => {
        const prox = prazoMaisProximo(p);
        if (!prox) return null;
        const dias = diasAte(prox.data);
        if (dias === null) return null;
        return { proposta: p, data: prox.data, tipo: prox.tipo, dias };
      })
      .filter((x): x is NonNullable<typeof x> => x !== null)
      .sort((a, b) => a.dias - b.dias)
      .slice(0, 6);
  }, [propostas]);

  const semTerritorio = !loading && (visao?.municipios.length ?? 0) === 0;

  if (loading) {
    return (
      <>
        <PageHeader titulo="Meu painel" />
        <SkeletonCards />
        <SkeletonList count={2} />
      </>
    );
  }

  if (semTerritorio) {
    return (
      <>
        <PageHeader titulo="Meu painel" />
        <EmptyState
          titulo="Você ainda não acompanha nenhum município."
          descricao="O Hub Capture se organiza a partir do seu perfil — comece escolhendo os municípios e áreas que quer acompanhar."
          acao={
            <Link href="/onboarding">
              <Button>Configurar meu perfil</Button>
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        titulo="Meu painel"
        descricao="Tudo do seu território, por etapa do ciclo do recurso público."
      />

      {/* Faixa de alertas: a detecção de mudança já gerava alerta e ele não
          tinha onde aparecer. Agora abre o painel. */}
      {alertas.length > 0 && (
        <Link
          href="/painel/alertas"
          className="flex flex-wrap items-center gap-3 rounded-xl border border-warn-line bg-warn-bg px-4 py-3 transition hover:brightness-[0.98]"
        >
          <span className="num rounded-full bg-warn px-2 py-0.5 text-xs font-bold text-white">
            {alertas.length}
          </span>
          <span className="text-sm font-medium text-warn">
            {alertas.length === 1
              ? "1 alerta não lido nas suas propostas"
              : `${alertas.length} alertas não lidos nas suas propostas`}
          </span>
          <span className="ml-auto text-xs text-warn">
            mais recente {haQuantoTempo(alertas[0]?.created_at)} →
          </span>
        </Link>
      )}

      {/* KPIs em reais — antes o painel só contava registros (UI-08). */}
      <StatRow cols={4}>
        <StatCard
          label="Em captação"
          value={formatBRLCompact(resumo.valorTotal)}
          context={`${resumo.total} ${resumo.total === 1 ? "proposta" : "propostas"} no território`}
        />
        <StatCard
          label="Contrapartida prevista"
          value={formatBRLCompact(resumo.contrapartidaTotal)}
          context="do caixa do município"
        />
        <StatCard
          label="Pendências"
          value={String(resumo.pendenciasTotal)}
          tone={resumo.pendenciasTotal > 0 ? "alerta" : "ok"}
          context={
            resumo.pendenciasTotal > 0
              ? `em ${resumo.comPendencia} ${resumo.comPendencia === 1 ? "proposta" : "propostas"}`
              : "nada travado"
          }
        />
        <StatCard
          label="Prazo mais próximo"
          value={
            resumo.prazoMaisProximo
              ? resumo.prazoMaisProximo.dias < 0
                ? "vencido"
                : `${resumo.prazoMaisProximo.dias} dias`
              : "—"
          }
          tone={resumo.prazoMaisProximo && resumo.prazoMaisProximo.dias <= 15 ? "alerta" : "neutral"}
          context={
            resumo.prazoMaisProximo
              ? fonteCurta(resumo.prazoMaisProximo.proposta.fonte)
              : "sem prazo registrado"
          }
        />
      </StatRow>

      <section className="flex flex-col gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Ciclo do recurso público
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {(visao?.dimensoes ?? []).map((d) => (
            <Link
              key={d.chave}
              href={d.href}
              className="group flex items-baseline justify-between gap-3 rounded-xl border border-line bg-bg p-4 shadow-card transition hover:border-brand"
            >
              <span className="min-w-0">
                <span className="block font-semibold text-ink group-hover:text-brand">
                  {d.titulo}
                </span>
                <span className="mt-0.5 block text-sm text-muted">{d.destaque ?? "—"}</span>
              </span>
              <span className="num shrink-0 text-2xl font-bold tracking-tight text-ink">
                {d.total}
              </span>
            </Link>
          ))}
        </div>
      </section>

      {/* Agenda: os prazos que a listagem escondia. */}
      <section className="flex flex-col gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Próximos prazos
        </h2>
        {agenda.length === 0 ? (
          <EmptyState
            titulo="Nenhum prazo registrado nas suas propostas."
            descricao="Prazos e pendências aparecem aqui assim que as fontes os informarem."
          />
        ) : (
          <Card>
            <ul className="flex flex-col divide-y divide-line">
              {agenda.map((item) => {
                const { texto } = tituloProposta(item.proposta);
                return (
                  <li key={`${item.proposta.id}-${item.data}`}>
                    <Link
                      href={`/painel/captacao/${item.proposta.id}`}
                      className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3 transition hover:bg-surface"
                    >
                      <StatusBadge
                        tone={item.dias < 0 ? "danger" : item.dias <= 15 ? "warning" : "neutral"}
                      >
                        {prazoLabel(item.data)}
                      </StatusBadge>
                      <span className="min-w-0 flex-1 truncate text-sm text-ink" title={texto}>
                        {texto}
                      </span>
                      <span className="shrink-0 text-xs text-muted">{item.tipo}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
      </section>

      {alertas.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Alertas recentes
          </h2>
          <Card>
            <ul className="flex flex-col divide-y divide-line">
              {alertas.slice(0, 5).map((a) => (
                <li key={a.id}>
                  <Link
                    href={`/painel/captacao/${a.proposta_id}`}
                    className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3 transition hover:bg-surface"
                  >
                    <StatusBadge tone="warning">{alertaTipoLabel(a.tipo)}</StatusBadge>
                    <span className={cx("min-w-0 flex-1 truncate text-sm text-ink-2")}>
                      {descreverAlerta(a)}
                    </span>
                    <span className="shrink-0 text-xs text-muted">
                      {haQuantoTempo(a.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          <Link
            href="/painel/alertas"
            className="self-start text-sm text-brand underline underline-offset-2"
          >
            Ver todos os alertas
          </Link>
        </section>
      )}
    </>
  );
}
