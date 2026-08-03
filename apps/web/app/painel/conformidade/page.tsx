"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonCards, SkeletonLines } from "@/components/Skeleton";
import { StatCard, StatRow } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { SyncForm } from "@/components/SyncForm";
import { Aviso, Card } from "@/components/ui";
import { api } from "@/lib/api/client";

interface Requisito {
  id: string;
  numero: string;
  secao?: string | null;
  descricao?: string | null;
  status?: string | null;
  orgao?: string | null;
}
interface SecaoResumo {
  secao: string;
  total: number;
  comprovados: number;
  a_comprovar: number;
  desativados: number;
}
interface Resumo {
  total: number;
  comprovados: number;
  a_comprovar: number;
  desativados: number;
  secoes: SecaoResumo[];
  capag?: { status?: string | null } | null;
  requisitos: Requisito[];
}

const TONE: Record<string, BadgeTone> = {
  comprovado: "success",
  a_comprovar: "warning",
  desativado: "neutral",
};
const LABEL: Record<string, string> = {
  comprovado: "Comprovado",
  a_comprovar: "A comprovar",
  desativado: "Desativado",
};

export default function ConformidadePage() {
  const [data, setData] = useState<Resumo | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [ibgeSugerido, setIbgeSugerido] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    const { data: d, error } = await api.GET("/api/v1/conformidade", {
      params: { query: {} },
    });
    if (error) setErro("Não foi possível carregar a conformidade fiscal.");
    else setData(d as Resumo);
    setLoading(false);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  useEffect(() => {
    void (async () => {
      const { data: perfil } = await api.GET("/api/v1/perfil");
      const m = (perfil as { municipios?: { ibge: string }[] } | undefined)?.municipios?.[0];
      if (m) setIbgeSugerido(m.ibge);
    })();
  }, []);

  const requisitosPorSecao = (secao: string) =>
    (data?.requisitos ?? []).filter((r) => (r.secao ?? "—") === secao);

  const pendentes = data?.a_comprovar ?? 0;

  return (
    <>
      <PageHeader
        titulo="Conformidade fiscal"
        descricao="CAUC e CAPAG — o que pode travar a assinatura de um convênio."
      />

      <SyncForm
        rotulo="Sincronizar município (IBGE)"
        botao="Buscar no Tesouro"
        erroPadrao="A fonte (Tesouro) não respondeu agora. Tente novamente."
        ibgeSugerido={ibgeSugerido}
        onSync={async (ibge) => {
          const { error } = await api.POST("/api/v1/conformidade/sync", {
            body: { municipio_ibge: ibge },
          });
          if (error) return { ok: false };
          await carregar();
          return { ok: true, mensagem: "Sincronização concluída." };
        }}
      />

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {loading ? (
        <>
          <SkeletonCards />
          <SkeletonLines count={4} />
        </>
      ) : (data?.total ?? 0) === 0 ? (
        <EmptyState
          titulo="Sem dados de conformidade."
          descricao="Sincronize um município acima para buscar os requisitos do CAUC no Tesouro Transparente."
        />
      ) : (
        <>
          <StatRow cols={4}>
            <StatCard
              label="Requisitos"
              value={String(data?.total ?? 0)}
              context="avaliados no CAUC"
            />
            <StatCard
              label="Comprovados"
              value={String(data?.comprovados ?? 0)}
              tone="ok"
              context={
                (data?.total ?? 0) > 0
                  ? `${(((data?.comprovados ?? 0) / data!.total) * 100).toFixed(0)}% do total`
                  : undefined
              }
            />
            <StatCard
              label="A comprovar"
              value={String(pendentes)}
              tone={pendentes > 0 ? "alerta" : "ok"}
              context={pendentes > 0 ? "bloqueiam repasses" : "nada pendente"}
            />
            <StatCard
              label="CAPAG"
              value={data?.capag?.status ?? "—"}
              context="capacidade de pagamento"
            />
          </StatRow>

          <div className="flex flex-col gap-5">
            {(data?.secoes ?? []).map((sec) => (
              <section key={sec.secao} className="flex flex-col gap-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                    {sec.secao}
                  </h2>
                  <span className="num text-xs text-muted">
                    {sec.comprovados}/{sec.total} comprovados
                  </span>
                </div>
                <Card>
                  <ul className="flex flex-col divide-y divide-line">
                    {requisitosPorSecao(sec.secao).map((r) => (
                      <li
                        key={r.id}
                        className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 px-4 py-2.5 text-sm"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="font-mono text-xs text-muted">{r.numero}</span>{" "}
                          <span className="text-ink-2">{r.descricao ?? "—"}</span>
                          {r.orgao && <span className="text-xs text-muted"> · {r.orgao}</span>}
                        </span>
                        <StatusBadge tone={TONE[r.status ?? ""] ?? "neutral"}>
                          {LABEL[r.status ?? ""] ?? r.status ?? "—"}
                        </StatusBadge>
                      </li>
                    ))}
                  </ul>
                </Card>
              </section>
            ))}
          </div>
        </>
      )}
    </>
  );
}
