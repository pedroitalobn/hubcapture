"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { FilterChips } from "@/components/FilterChips";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { StatCard, StatRow } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { Aviso, Button, Card, cx } from "@/components/ui";
import { alertaTipoLabel, descreverAlerta, type Alerta } from "@/lib/alertas";
import { api } from "@/lib/api/client";
import { formatDateTime, haQuantoTempo } from "@/lib/format";
import { tituloProposta, type Proposta } from "@/lib/proposta";

export default function AlertasPage() {
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [propostas, setPropostas] = useState<Map<string, Proposta>>(new Map());
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [tipo, setTipo] = useState<string | null>(null);
  const [soNaoLidos, setSoNaoLidos] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const [al, props] = await Promise.all([
      api.GET("/api/v1/alertas", { params: { query: { nao_lidos: soNaoLidos } } }),
      api.GET("/api/v1/propostas", { params: { query: {} } }),
    ]);
    if (al.error) setErro("Não foi possível carregar os alertas.");
    else setAlertas((al.data as Alerta[]) ?? []);
    if (Array.isArray(props.data)) {
      setPropostas(new Map((props.data as Proposta[]).map((p) => [p.id, p])));
    }
    setCarregando(false);
  }, [soNaoLidos]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function marcarLido(a: Alerta) {
    if (a.lido) return;
    setAlertas((lista) => lista.map((x) => (x.id === a.id ? { ...x, lido: true } : x)));
    const { error } = await api.POST("/api/v1/alertas/{alerta_id}/lido", {
      params: { path: { alerta_id: a.id } },
    });
    if (error) {
      setAlertas((lista) => lista.map((x) => (x.id === a.id ? { ...x, lido: false } : x)));
      setErro("Não foi possível marcar como lido.");
    }
  }

  async function marcarTodos() {
    const pendentes = alertas.filter((a) => !a.lido);
    if (pendentes.length === 0) return;
    setAlertas((lista) => lista.map((x) => ({ ...x, lido: true })));
    const res = await Promise.all(
      pendentes.map((a) =>
        api.POST("/api/v1/alertas/{alerta_id}/lido", {
          params: { path: { alerta_id: a.id } },
        }),
      ),
    );
    if (res.some((r) => r.error)) {
      setErro("Alguns alertas não puderam ser marcados. Recarregando…");
      await carregar();
    }
  }

  const naoLidos = alertas.filter((a) => !a.lido).length;

  const chips = useMemo(() => {
    const m = new Map<string, number>();
    for (const a of alertas) {
      const t = a.tipo ?? "outro";
      m.set(t, (m.get(t) ?? 0) + 1);
    }
    return [...m.entries()].map(([value, count]) => ({
      value,
      label: alertaTipoLabel(value),
      count,
    }));
  }, [alertas]);

  const visiveis = useMemo(
    () => (tipo ? alertas.filter((a) => (a.tipo ?? "outro") === tipo) : alertas),
    [alertas, tipo],
  );

  return (
    <>
      <PageHeader
        titulo="Alertas"
        descricao="Mudanças detectadas nas propostas que você acompanha."
        acoes={
          <>
            <Button
              variante={soNaoLidos ? "primary" : "secondary"}
              tamanho="sm"
              onClick={() => setSoNaoLidos((v) => !v)}
              aria-pressed={soNaoLidos}
            >
              Só não lidos
            </Button>
            <Button
              variante="secondary"
              tamanho="sm"
              onClick={marcarTodos}
              disabled={naoLidos === 0}
            >
              Marcar todos como lidos
            </Button>
          </>
        }
      />

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {carregando ? (
        <SkeletonLines count={5} />
      ) : (
        <>
          <StatRow cols={2}>
            <StatCard
              label="Não lidos"
              value={String(naoLidos)}
              tone={naoLidos > 0 ? "alerta" : "ok"}
              context={naoLidos > 0 ? "aguardando sua leitura" : "tudo em dia"}
            />
            <StatCard
              label="Total no período"
              value={String(alertas.length)}
              context="alertas registrados"
            />
          </StatRow>

          {chips.length > 1 && (
            <FilterChips
              ariaLabel="Filtrar por tipo de alerta"
              options={chips}
              selected={tipo}
              onSelect={setTipo}
              todasLabel="Todos os tipos"
              todasCount={alertas.length}
            />
          )}

          {visiveis.length === 0 ? (
            <EmptyState
              titulo={soNaoLidos ? "Nenhum alerta não lido." : "Nenhum alerta ainda."}
              descricao="Alertas nascem do job de detecção de mudança: quando a situação, um prazo ou uma pendência muda numa proposta monitorada, ela aparece aqui."
              acao={
                <Link href="/painel/captacao">
                  <Button variante="secondary">Escolher propostas para monitorar</Button>
                </Link>
              }
            />
          ) : (
            <Card>
              <ul className="flex flex-col divide-y divide-line">
                {visiveis.map((a) => {
                  const p = propostas.get(a.proposta_id);
                  return (
                    <li
                      key={a.id}
                      className={cx(
                        "flex flex-wrap items-start gap-x-3 gap-y-2 px-4 py-3",
                        !a.lido && "bg-warn-bg/40",
                      )}
                    >
                      {!a.lido && (
                        <span
                          aria-label="Não lido"
                          className="mt-1.5 size-2 shrink-0 rounded-full bg-warn"
                        />
                      )}
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge tone={a.lido ? "neutral" : "warning"}>
                            {alertaTipoLabel(a.tipo)}
                          </StatusBadge>
                          <span className="text-sm text-ink">{descreverAlerta(a)}</span>
                        </div>
                        <Link
                          href={`/painel/captacao/${a.proposta_id}`}
                          className="truncate text-xs text-muted hover:text-brand hover:underline"
                        >
                          {p ? tituloProposta(p).texto : "Abrir proposta"}
                        </Link>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span
                          className="text-xs text-muted"
                          title={formatDateTime(a.created_at)}
                        >
                          {haQuantoTempo(a.created_at)}
                        </span>
                        {!a.lido && (
                          <Button variante="ghost" tamanho="sm" onClick={() => marcarLido(a)}>
                            Marcar lido
                          </Button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </>
      )}
    </>
  );
}
