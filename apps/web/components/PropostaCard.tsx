"use client";

import Link from "next/link";
import { StatusBadge } from "./StatusBadge";
import { Button, cx } from "./ui";
import {
  diasAte,
  formatBRL,
  formatDate,
  formatDateTime,
  prazoLabel,
} from "@/lib/format";
import {
  fonteCurta,
  municipioLabel,
  pendencias,
  percentualContrapartida,
  prazoMaisProximo,
  propostaTone,
  provenienciaResumo,
  situacaoTone,
  tituloProposta,
  type Proposta,
} from "@/lib/proposta";

const FAIXA = {
  danger: "bg-danger",
  warning: "bg-warn",
  success: "bg-ok",
  info: "bg-brand",
  brand: "bg-brand",
  neutral: "bg-line-strong",
} as const;

/**
 * Cartão denso de proposta. Substitui a linha de tabela, que mostrava 6 dos 23
 * campos do PropostaRead e quebrava no celular: pendências, prazos, emenda,
 * resumo da IA, movimentação e proveniência do merge agora aparecem.
 */
export function PropostaCard({
  proposta,
  favorito,
  monitorada,
  onFavoritar,
  onMonitorar,
  onPdf,
}: {
  proposta: Proposta;
  favorito?: boolean;
  monitorada?: boolean;
  onFavoritar?: (p: Proposta) => void;
  onMonitorar?: (p: Proposta) => void;
  onPdf?: (p: Proposta) => void;
}) {
  const p = proposta;
  const { texto: titulo, ehFallback } = tituloProposta(p);
  const pend = pendencias(p);
  const prox = prazoMaisProximo(p);
  const diasProx = prox ? diasAte(prox.data) : null;
  const pctCp = percentualContrapartida(p);
  const prov = provenienciaResumo(p);
  const tone = propostaTone(p);

  return (
    <article className="grid grid-cols-[3px_1fr] overflow-hidden rounded-xl border border-line bg-bg shadow-card">
      <span aria-hidden className={FAIXA[tone]} />
      <div className="flex min-w-0 flex-col gap-3 p-4">
        {/* título + dinheiro */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <h3 className="min-w-0 text-[15px] font-semibold leading-snug text-ink">
            <Link
              href={`/painel/captacao/${p.id}`}
              className={cx("hover:text-brand hover:underline", ehFallback && "font-medium text-ink-2")}
            >
              {titulo}
            </Link>
          </h3>
          <p className="shrink-0 sm:text-right">
            <span className="num block text-[17px] font-bold tracking-tight text-ink">
              {formatBRL(p.valor_total)}
            </span>
            <span className="num block text-[11px] text-muted">
              {p.contrapartida === null || p.contrapartida === undefined
                ? "contrapartida não informada"
                : Number(p.contrapartida) === 0
                  ? "sem contrapartida"
                  : `contrapartida ${formatBRL(p.contrapartida)}${
                      pctCp !== null ? ` · ${pctCp.toFixed(1)}%` : ""
                    }`}
            </span>
          </p>
        </div>

        {/* estado, fonte, modalidade, emenda, pendências */}
        <div className="flex flex-wrap items-center gap-1.5">
          {p.situacao && (
            <StatusBadge tone={situacaoTone(p.situacao)}>{p.situacao}</StatusBadge>
          )}
          <StatusBadge tone="brand" mono>
            {fonteCurta(p.fonte)}
          </StatusBadge>
          {p.modalidade && <StatusBadge>{p.modalidade}</StatusBadge>}
          {p.emenda && <StatusBadge tone="info">{p.emenda}</StatusBadge>}
          {pend.length > 0 ? (
            <StatusBadge tone="danger">
              {pend.length === 1 ? "1 pendência" : `${pend.length} pendências`}
            </StatusBadge>
          ) : (
            <StatusBadge tone="success">Sem pendências</StatusBadge>
          )}
          {diasProx !== null && diasProx <= 15 && pend.length === 0 && (
            <StatusBadge tone="warning">{prazoLabel(prox!.data)}</StatusBadge>
          )}
        </div>

        {/* identificação */}
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
          <Fato rotulo="Nº" valor={p.numero_proposta ?? p.id_externo} mono />
          <Fato rotulo="Órgão" valor={p.orgao_superior} />
          <Fato rotulo="Município" valor={municipioLabel(p)} />
        </dl>

        {p.resumo_ia && (
          <p className="flex gap-2 rounded-lg bg-brand-soft px-3 py-2 text-xs leading-relaxed text-brand-soft-fg">
            <span className="shrink-0 pt-px font-mono text-[10px] font-bold tracking-widest">
              IA
            </span>
            <span>{p.resumo_ia}</span>
          </p>
        )}

        {pend.length > 0 && (
          <ul className="flex flex-col gap-1 text-xs">
            {pend.map((x, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-2 text-ink-2">
                <span aria-hidden className="mt-1 size-1.5 shrink-0 rounded-full bg-warn" />
                <span className="min-w-0 flex-1">{x.descricao ?? "Pendência sem descrição"}</span>
                {x.prazo && (
                  <span
                    className={cx(
                      "num shrink-0 font-semibold",
                      (diasAte(x.prazo) ?? 99) < 0 ? "text-danger" : "text-warn",
                    )}
                  >
                    {prazoLabel(x.prazo)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}

        {p.movimentacao && (
          <p className="text-xs text-ink-2">
            <span className="text-muted">Movimentação · </span>
            {p.movimentacao}
          </p>
        )}

        {/* rodapé: procedência do dado + ações */}
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <p className="mr-auto text-[11px] text-muted">
            {p.data_atualizacao_fonte
              ? `Fonte atualizada em ${formatDate(p.data_atualizacao_fonte)}`
              : "Data da fonte não informada"}
            {p.cache_atualizado_em && ` · sincronizado ${formatDateTime(p.cache_atualizado_em)}`}
            {prov && ` · ${prov}`}
            {ehFallback && " · sem título na fonte, exibindo o objeto"}
          </p>
          <Link href={`/painel/captacao/${p.id}`}>
            <Button tamanho="sm">Abrir detalhe</Button>
          </Link>
          {onMonitorar && (
            <Button
              tamanho="sm"
              variante={monitorada ? "primary" : "secondary"}
              onClick={() => onMonitorar(p)}
              aria-pressed={monitorada}
            >
              {monitorada ? "Monitorando" : "Monitorar"}
            </Button>
          )}
          {onFavoritar && (
            <Button
              tamanho="sm"
              variante={favorito ? "primary" : "secondary"}
              onClick={() => onFavoritar(p)}
              aria-pressed={favorito}
            >
              {favorito ? "★ Favorita" : "☆ Favoritar"}
            </Button>
          )}
          {onPdf && (
            <Button tamanho="sm" variante="secondary" onClick={() => onPdf(p)}>
              PDF
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}

function Fato({
  rotulo,
  valor,
  mono,
}: {
  rotulo: string;
  valor?: string | null;
  mono?: boolean;
}) {
  if (!valor) return null;
  return (
    <div className="flex min-w-0 gap-1.5">
      <dt className="shrink-0 text-muted">{rotulo}</dt>
      <dd className={cx("min-w-0 truncate text-ink-2", mono && "font-mono")} title={valor}>
        {valor}
      </dd>
    </div>
  );
}
