"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { FilterChips } from "@/components/FilterChips";
import { PageHeader } from "@/components/PageHeader";
import { PropostaCard } from "@/components/PropostaCard";
import { SkeletonCards, SkeletonList } from "@/components/Skeleton";
import { StatCard, StatRow } from "@/components/StatCard";
import { SyncForm } from "@/components/SyncForm";
import { Aviso } from "@/components/ui";
import { api, baixarPdfProposta } from "@/lib/api/client";
import { formatBRLCompact, prazoLabel } from "@/lib/format";
import { fonteCurta, resumirCaptacao, type Proposta } from "@/lib/proposta";

interface Perfil {
  municipios: { ibge: string; nome?: string | null; uf?: string | null }[];
}

export default function CaptacaoPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [favoritos, setFavoritos] = useState<Set<string>>(new Set());
  const [monitoradas, setMonitoradas] = useState<Set<string>>(new Set());
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  // Filtros que a API já aceita e a tela nunca enviava (UI-05).
  const [fonte, setFonte] = useState<string | null>(null);
  const [situacao, setSituacao] = useState<string | null>(null);
  const [municipio, setMunicipio] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    const query: Record<string, string> = {};
    if (fonte) query.fonte = fonte;
    if (situacao) query.situacao = situacao;
    if (municipio) query.municipio = municipio;

    const { data, error } = await api.GET("/api/v1/propostas", {
      params: { query },
    });
    if (error) setErro("Não foi possível carregar as propostas do cache.");
    else setPropostas((data as Proposta[]) ?? []);
    setCarregando(false);
  }, [fonte, situacao, municipio]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const carregarCuradoria = useCallback(async () => {
    const [fav, mon, per] = await Promise.all([
      api.GET("/api/v1/favoritos"),
      api.GET("/api/v1/monitoramentos"),
      api.GET("/api/v1/perfil"),
    ]);
    if (Array.isArray(fav.data)) {
      setFavoritos(new Set((fav.data as { proposta_id: string }[]).map((f) => f.proposta_id)));
    }
    if (Array.isArray(mon.data)) {
      setMonitoradas(
        new Set(
          (mon.data as { proposta_id: string; ativo: boolean }[])
            .filter((m) => m.ativo)
            .map((m) => m.proposta_id),
        ),
      );
    }
    if (per.data) setPerfil(per.data as Perfil);
  }, []);

  useEffect(() => {
    void carregarCuradoria();
  }, [carregarCuradoria]);

  async function alternarFavorito(p: Proposta) {
    const jaEra = favoritos.has(p.id);
    setFavoritos((s) => {
      const n = new Set(s);
      if (jaEra) n.delete(p.id);
      else n.add(p.id);
      return n;
    });
    const { error } = jaEra
      ? await api.DELETE("/api/v1/favoritos/{proposta_id}", {
          params: { path: { proposta_id: p.id } },
        })
      : await api.POST("/api/v1/favoritos", { body: { proposta_id: p.id } });
    if (error) {
      // Devolve o estado — otimismo só vale se o erro voltar atrás.
      setFavoritos((s) => {
        const n = new Set(s);
        if (jaEra) n.add(p.id);
        else n.delete(p.id);
        return n;
      });
      setErro("Não foi possível salvar o favorito.");
    }
  }

  async function monitorar(p: Proposta) {
    if (monitoradas.has(p.id)) return;
    setMonitoradas((s) => new Set(s).add(p.id));
    const { error } = await api.POST("/api/v1/monitoramentos", {
      body: { proposta_id: p.id, canais: ["painel"] },
    });
    if (error) {
      setMonitoradas((s) => {
        const n = new Set(s);
        n.delete(p.id);
        return n;
      });
      setErro("Não foi possível ativar o monitoramento.");
    }
  }

  const resumo = useMemo(() => resumirCaptacao(propostas), [propostas]);

  const chipsFonte = useMemo(
    () => resumo.porFonte.map((f) => ({ value: f.fonte, label: fonteCurta(f.fonte), count: f.total })),
    [resumo],
  );

  const chipsSituacao = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of propostas) {
      if (p.situacao) m.set(p.situacao, (m.get(p.situacao) ?? 0) + 1);
    }
    return [...m.entries()].map(([value, count]) => ({ value, label: value, count }));
  }, [propostas]);

  const chipsMunicipio = useMemo(
    () =>
      (perfil?.municipios ?? []).map((m) => ({
        value: m.ibge,
        label: m.nome ? `${m.nome}${m.uf ? `/${m.uf}` : ""}` : m.ibge,
      })),
    [perfil],
  );

  const ibgeSugerido = perfil?.municipios?.[0]?.ibge ?? null;
  const temFiltro = Boolean(fonte || situacao || municipio);

  return (
    <>
      <PageHeader
        titulo="Captação"
        descricao="Propostas e editais abertos para o seu território."
      />

      <SyncForm
        rotulo="Consultar fonte por município (IBGE)"
        botao="Buscar na fonte"
        erroPadrao="A fonte oficial não respondeu agora (a API do TransfereGov é instável). Tente novamente."
        ibgeSugerido={ibgeSugerido}
        onSync={async (ibge) => {
          const { error } = await api.POST("/api/v1/consulta-avulsa", {
            body: { municipio_ibge: ibge, fonte: "transferegov_ff" },
          });
          if (error) return { ok: false };
          await carregar();
          return { ok: true, mensagem: "Consulta concluída e cache atualizado." };
        }}
      />

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {carregando ? (
        <>
          <SkeletonCards />
          <SkeletonList />
        </>
      ) : (
        <>
          <StatRow cols={4}>
            <StatCard
              label="Em captação"
              value={formatBRLCompact(resumo.valorTotal)}
              context={`${resumo.total} ${resumo.total === 1 ? "proposta" : "propostas"}`}
            />
            <StatCard
              label="Contrapartida"
              value={formatBRLCompact(resumo.contrapartidaTotal)}
              context={
                resumo.valorTotal > 0
                  ? `${((resumo.contrapartidaTotal / resumo.valorTotal) * 100).toFixed(1)}% do total`
                  : "sem base de cálculo"
              }
            />
            <StatCard
              label="Pendências"
              value={String(resumo.pendenciasTotal)}
              tone={resumo.pendenciasTotal > 0 ? "alerta" : "ok"}
              context={
                resumo.pendenciasTotal > 0
                  ? `em ${resumo.comPendencia} ${resumo.comPendencia === 1 ? "proposta" : "propostas"}`
                  : "nenhuma proposta travada"
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
              tone={
                resumo.prazoMaisProximo && resumo.prazoMaisProximo.dias <= 15 ? "alerta" : "neutral"
              }
              context={
                resumo.prazoMaisProximo
                  ? `${fonteCurta(resumo.prazoMaisProximo.proposta.fonte)} · ${prazoLabel(
                      resumo.prazoMaisProximo.data,
                    )}`
                  : "sem prazo registrado"
              }
            />
          </StatRow>

          {chipsMunicipio.length > 1 && (
            <FilterChips
              ariaLabel="Filtrar por município"
              options={chipsMunicipio}
              selected={municipio}
              onSelect={setMunicipio}
              todasLabel="Todo o território"
            />
          )}
          {chipsFonte.length > 0 && (
            <FilterChips
              ariaLabel="Filtrar por fonte"
              options={chipsFonte}
              selected={fonte}
              onSelect={setFonte}
              todasLabel="Todas as fontes"
              todasCount={resumo.total}
            />
          )}
          {chipsSituacao.length > 1 && (
            <FilterChips
              ariaLabel="Filtrar por situação"
              options={chipsSituacao}
              selected={situacao}
              onSelect={setSituacao}
              todasLabel="Todas as situações"
            />
          )}

          {propostas.length === 0 ? (
            temFiltro ? (
              <EmptyState
                titulo="Nenhuma proposta com esses filtros."
                descricao="Ajuste ou limpe os filtros acima para ver o resto do território."
              />
            ) : (
              <EmptyState
                titulo="Nenhuma proposta no cache ainda."
                descricao="O Hub trabalha cache-first: faça uma consulta avulsa acima para buscar na fonte oficial e popular o painel."
              />
            )
          ) : (
            <section className="flex flex-col gap-3" aria-label="Propostas">
              {propostas.map((p) => (
                <PropostaCard
                  key={p.id}
                  proposta={p}
                  favorito={favoritos.has(p.id)}
                  monitorada={monitoradas.has(p.id)}
                  onFavoritar={alternarFavorito}
                  onMonitorar={monitorar}
                  onPdf={(x) => void baixarPdfProposta(x.id)}
                />
              ))}
            </section>
          )}
        </>
      )}
    </>
  );
}
