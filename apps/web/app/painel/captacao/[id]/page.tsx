"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonList } from "@/components/Skeleton";
import { StatCard, StatRow } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { Aviso, Button, Card, cx } from "@/components/ui";
import { api, baixarPdfProposta } from "@/lib/api/client";
import {
  diasAte,
  formatBRL,
  formatDate,
  formatDateTime,
  prazoLabel,
} from "@/lib/format";
import {
  fonteLabel,
  municipioLabel,
  pendencias,
  percentualContrapartida,
  prazoMaisProximo,
  prazos,
  situacaoTone,
  tituloProposta,
  type Proposta,
} from "@/lib/proposta";

const ORIGEM_LABEL: Record<string, string> = {
  api: "API oficial",
  scrape: "Scraping",
  scraping: "Scraping",
};

export default function PropostaDetalhePage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [proposta, setProposta] = useState<Proposta | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [naoEncontrada, setNaoEncontrada] = useState(false);
  const [favorito, setFavorito] = useState(false);
  const [monitorada, setMonitorada] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    if (!id) return;
    setCarregando(true);
    const { data, error } = await api.GET("/api/v1/propostas/{proposta_id}", {
      params: { path: { proposta_id: id } },
    });
    if (error) setNaoEncontrada(true);
    else setProposta(data as Proposta);
    setCarregando(false);
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  useEffect(() => {
    if (!id) return;
    void (async () => {
      const [fav, mon] = await Promise.all([
        api.GET("/api/v1/favoritos"),
        api.GET("/api/v1/monitoramentos"),
      ]);
      if (Array.isArray(fav.data)) {
        setFavorito((fav.data as { proposta_id: string }[]).some((f) => f.proposta_id === id));
      }
      if (Array.isArray(mon.data)) {
        setMonitorada(
          (mon.data as { proposta_id: string; ativo: boolean }[]).some(
            (m) => m.proposta_id === id && m.ativo,
          ),
        );
      }
    })();
  }, [id]);

  async function alternarFavorito() {
    if (!id) return;
    const jaEra = favorito;
    setFavorito(!jaEra);
    const { error } = jaEra
      ? await api.DELETE("/api/v1/favoritos/{proposta_id}", {
          params: { path: { proposta_id: id } },
        })
      : await api.POST("/api/v1/favoritos", { body: { proposta_id: id } });
    if (error) {
      setFavorito(jaEra);
      setErro("Não foi possível salvar o favorito.");
    }
  }

  async function monitorar() {
    if (!id || monitorada) return;
    setMonitorada(true);
    const { error } = await api.POST("/api/v1/monitoramentos", {
      body: { proposta_id: id, canais: ["painel"] },
    });
    if (error) {
      setMonitorada(false);
      setErro("Não foi possível ativar o monitoramento.");
    }
  }

  if (carregando) {
    return (
      <>
        <PageHeader titulo="Proposta" />
        <SkeletonList count={2} />
      </>
    );
  }

  if (naoEncontrada || !proposta) {
    return (
      <>
        <PageHeader titulo="Proposta" />
        <EmptyState
          titulo="Proposta não encontrada."
          descricao="Ela pode estar fora do seu território ou ter saído do cache."
          acao={
            <Link href="/painel/captacao">
              <Button variante="secondary">Voltar para Captação</Button>
            </Link>
          }
        />
      </>
    );
  }

  const p = proposta;
  const { texto: titulo, ehFallback } = tituloProposta(p);
  const pend = pendencias(p);
  const listaPrazos = prazos(p);
  const prox = prazoMaisProximo(p);
  const pctCp = percentualContrapartida(p);
  const prov = Object.entries(p.proveniencia ?? {});

  return (
    <>
      <nav className="text-sm">
        <Link href="/painel/captacao" className="text-muted hover:text-brand hover:underline">
          ← Captação
        </Link>
      </nav>

      <PageHeader
        titulo={titulo}
        descricao={
          ehFallback
            ? "A fonte não informou um título — exibindo o objeto da proposta."
            : undefined
        }
        acoes={
          <>
            <Button variante={monitorada ? "primary" : "secondary"} onClick={monitorar}>
              {monitorada ? "Monitorando" : "Monitorar"}
            </Button>
            <Button variante={favorito ? "primary" : "secondary"} onClick={alternarFavorito}>
              {favorito ? "★ Favorita" : "☆ Favoritar"}
            </Button>
            <Button variante="secondary" onClick={() => void baixarPdfProposta(p.id)}>
              PDF
            </Button>
          </>
        }
      />

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      <div className="flex flex-wrap items-center gap-1.5">
        {p.situacao && <StatusBadge tone={situacaoTone(p.situacao)}>{p.situacao}</StatusBadge>}
        <StatusBadge tone="brand">{fonteLabel(p.fonte)}</StatusBadge>
        {p.modalidade && <StatusBadge>{p.modalidade}</StatusBadge>}
        {p.emenda && <StatusBadge tone="info">{p.emenda}</StatusBadge>}
      </div>

      <StatRow cols={pend.length > 0 || prox ? 4 : 2}>
        <StatCard label="Valor total" value={formatBRL(p.valor_total)} />
        <StatCard
          label="Contrapartida"
          value={formatBRL(p.contrapartida)}
          context={pctCp !== null ? `${pctCp.toFixed(1)}% do total` : undefined}
        />
        {(pend.length > 0 || prox) && (
          <StatCard
            label="Pendências"
            value={String(pend.length)}
            tone={pend.length > 0 ? "alerta" : "ok"}
            context={pend.length > 0 ? "impedem o andamento" : "nada travando"}
          />
        )}
        {(pend.length > 0 || prox) && (
          <StatCard
            label="Prazo mais próximo"
            value={prox ? prazoLabel(prox.data) : "—"}
            tone={prox && (diasAte(prox.data) ?? 99) <= 15 ? "alerta" : "neutral"}
            context={prox ? formatDate(prox.data) : "sem prazo registrado"}
          />
        )}
      </StatRow>

      {p.resumo_ia && (
        <Card className="p-4">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Resumo da IA
          </p>
          <p className="text-sm leading-relaxed text-ink-2">{p.resumo_ia}</p>
        </Card>
      )}

      {p.objeto && (
        <Card className="p-4">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Objeto
          </p>
          <p className="max-w-prose text-sm leading-relaxed text-ink-2">{p.objeto}</p>
        </Card>
      )}

      {pend.length > 0 && (
        <Card className="p-4">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Pendências
          </p>
          <ul className="flex flex-col divide-y divide-line">
            {pend.map((x, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-2 py-2 text-sm first:pt-0">
                <span className="min-w-0 flex-1 text-ink-2">
                  {x.descricao ?? "Pendência sem descrição"}
                </span>
                {x.prazo && (
                  <span
                    className={cx(
                      "num shrink-0 text-xs font-semibold",
                      (diasAte(x.prazo) ?? 99) < 0 ? "text-danger" : "text-warn",
                    )}
                  >
                    {prazoLabel(x.prazo)} · {formatDate(x.prazo)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {listaPrazos.length > 0 && (
        <Card className="p-4">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Prazos
          </p>
          <ul className="flex flex-col divide-y divide-line">
            {listaPrazos.map((x, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-2 py-2 text-sm first:pt-0">
                <span className="min-w-0 flex-1 text-ink-2">{x.tipo ?? "Prazo"}</span>
                <span className="num shrink-0 text-xs text-muted">
                  {formatDate(x.data_limite)} · {prazoLabel(x.data_limite)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {p.movimentacao && (
        <Card className="p-4">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Última movimentação
          </p>
          <p className="text-sm text-ink-2">{p.movimentacao}</p>
        </Card>
      )}

      <Card className="p-4">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
          Identificação
        </p>
        <dl className="grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
          <Linha rotulo="Nº da proposta" valor={p.numero_proposta} mono />
          <Linha rotulo="ID na fonte" valor={p.id_externo} mono />
          <Linha rotulo="Órgão superior" valor={p.orgao_superior} />
          <Linha rotulo="Modalidade" valor={p.modalidade} />
          <Linha rotulo="Município" valor={municipioLabel(p)} />
          <Linha rotulo="Código IBGE" valor={p.municipio_ibge} mono />
          <Linha rotulo="Emenda" valor={p.emenda} />
          <Linha rotulo="Atualização na fonte" valor={formatDate(p.data_atualizacao_fonte)} />
          <Linha
            rotulo="Sincronizado no Hub"
            valor={p.cache_atualizado_em ? formatDateTime(p.cache_atualizado_em) : null}
          />
        </dl>
      </Card>

      {/* A auditoria do merge multi-fonte — regra central do CLAUDE.md que a
          web nunca expôs: qual lado (API ou scraping) venceu em cada campo. */}
      {prov.length > 0 && (
        <Card className="p-4">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Proveniência dos dados
          </p>
          <p className="mb-3 text-xs text-muted">
            A coleta combina API e scraping. Este é o lado que venceu em cada campo.
          </p>
          <ul className="flex flex-wrap gap-2">
            {prov.map(([campo, origem]) => (
              <li key={campo}>
                <StatusBadge tone={origem === "api" ? "info" : "warning"}>
                  <span className="font-mono text-[11px]">{campo.replace(/_/g, " ")}</span>
                  <span className="opacity-70">· {ORIGEM_LABEL[origem] ?? origem}</span>
                </StatusBadge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {p.url_origem && (
        <p className="text-sm">
          <a
            href={p.url_origem}
            target="_blank"
            rel="noreferrer noopener"
            className="text-brand underline underline-offset-2"
          >
            Abrir na fonte oficial ↗
          </a>
        </p>
      )}
    </>
  );
}

function Linha({
  rotulo,
  valor,
  mono,
}: {
  rotulo: string;
  valor?: string | null;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-x-2 border-b border-line py-1.5 last:border-0">
      <dt className="min-w-36 text-muted">{rotulo}</dt>
      <dd className={cx("min-w-0 flex-1 text-ink-2", mono && "font-mono text-xs")}>
        {valor && valor !== "—" ? valor : <span className="text-muted">não informado</span>}
      </dd>
    </div>
  );
}
