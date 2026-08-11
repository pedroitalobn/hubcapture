"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { BotaoEspelho } from "@/components/BotaoEspelho";
import { Hint } from "@/components/Hint";
import { AndamentoProposta } from "@/components/AndamentoProposta";
import { EmendasProposta } from "@/components/EmendasProposta";
import { NumeroProposta } from "@/components/NumeroProposta";
import { Skeleton } from "@/components/Skeleton";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { TextoExpansivel } from "@/components/TextoExpansivel";
import { Aviso, Dado, cx } from "@/components/ui";
import {
  diasAte,
  formatBRL,
  formatDate,
  formatDateTime,
  humanizarCaixa,
  municipioPrincipal,
  municipioSecundario,
  prazoLabel,
  tomPrazo,
} from "@/lib/format";
import { useTerritorio } from "@/lib/territorio";

type Prazo = { tipo?: string | null; data_limite?: string | null };
type Pendencia = { descricao?: string | null; prazo?: string | null };

type Proposta = {
  id: string;
  fonte: string;
  id_externo: string;
  numero_proposta?: string | null;
  numero_plano_trabalho?: string | null;
  titulo?: string | null;
  objeto?: string | null;
  orgao_superior?: string | null;
  modalidade?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  contrapartida?: string | null;
  situacao?: string | null;
  emenda?: string | null;
  prazos?: Prazo[] | null;
  pendencias?: Pendencia[] | null;
  movimentacao?: string | null;
  data_proposta?: string | null;
  data_atualizacao_fonte?: string | null;
  url_origem?: string | null;
  proveniencia?: Record<string, string> | null;
  resumo_ia?: string | null;
  /** Pílulas de categoria (curadoria) — slug filtrável + rótulo exibível. */
  categorias?: { slug: string; rotulo: string }[] | null;
  tipo?: string;
  /** Ano de CRIAÇÃO da proposta (ANO_PROP na fonte) — a safra do cabeçalho. */
  ano?: string | null;
  // computados pela API — a tela antes descartava os três
  prazo_final?: string | null;
  dias_restantes?: number | null;
  natureza_juridica?: string | null;
  cache_atualizado_em?: string | null;
  execucao?: {
    valor_global?: string | null;
    valor_empenhado?: string | null;
    valor_liberado?: string | null;
    valor_pago?: string | null;
    saldo_conta?: string | null;
    ano?: string | number | null;
    ente_recebedor?: string | null;
    natureza_juridica?: string | null;
    data_assinatura?: string | null;
    data_inicio_vigencia?: string | null;
    data_fim_vigencia?: string | null;
    tipo_transferencia?: string | null;
  } | null;
  // registro-fonte COMPLETO (todos os campos do site de origem)
  dados_fonte?: Record<string, unknown> | null;
};

function num(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/** De-para situação → tom do badge (mesma disciplina do resto do painel). */
function tomSituacao(situacao?: string | null): BadgeTone {
  const s = (situacao ?? "").toLowerCase();
  if (/aprovad|celebrad|vigente|conclu/.test(s)) return "success";
  if (/pendenc|análise|analise|aguardand|diligenc/.test(s)) return "warning";
  if (/rejeitad|cancelad|impedid|arquivad/.test(s)) return "danger";
  return "neutral";
}

// rótulo legível a partir da chave crua da fonte (ex.: valor_total_repasse_plano_acao
// → "Valor total repasse"). Remove os sufixos de tabela e capitaliza.
function humanizar(chave: string): string {
  const limpa = chave
    .replace(/_(plano_acao|programa|especial|convenio|beneficiario|proposta)$/g, "")
    .replace(/_/g, " ")
    .trim();
  return limpa.charAt(0).toUpperCase() + limpa.slice(1);
}

function valorLegivel(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) {
    // lista de escalares vira "a · b · c"; de objetos, JSON indentado legível
    return v.every((x) => x === null || typeof x !== "object")
      ? v.map((x) => humanizarCaixa(String(x))).join(" · ")
      : JSON.stringify(v, null, 2);
  }
  if (typeof v === "object") return JSON.stringify(v, null, 2);
  return humanizarCaixa(String(v));
}

// A partir daqui o valor deixa de caber numa célula da grade e passa a ocupar a
// linha inteira, recortado e com botão de ampliar. O limiar é de caracteres
// (grosseiro de propósito): quem decide se HÁ corte é a medição no DOM, dentro
// do TextoExpansivel — isto aqui só escolhe o layout.
const LIMIAR_CAMPO_LONGO = 160;

function ehLongo(valor: string): boolean {
  return valor.length > LIMIAR_CAMPO_LONGO || valor.includes("\n");
}

/** Um campo do registro-fonte: curto vira par rótulo/valor; longo, bloco amplo. */
function CampoFonte({
  rotulo,
  valor,
  abrirTudo,
}: {
  rotulo: string;
  valor: string;
  abrirTudo: boolean;
}) {
  if (!ehLongo(valor)) return <Dado rotulo={rotulo} valor={valor} />;
  return (
    <div className="field col-span-full">
      <span className="field-label">{rotulo}</span>
      <TextoExpansivel
        // remonta ao alternar "ampliar tudo" — o botão da seção manda no campo
        key={abrirTudo ? "aberto" : "fechado"}
        texto={valor}
        abertoInicial={abrirTudo}
        linhas={3}
      />
    </div>
  );
}

// Renderiza TODOS os campos do registro-fonte. `dados_fonte` costuma vir agrupado
// ({plano_acao:{...}, programa:{...}}); se um valor for objeto, vira subgrupo.
function DadosCompletos({
  dados,
  abrirTudo,
}: {
  dados: Record<string, unknown>;
  abrirTudo: boolean;
}) {
  const grupos = Object.entries(dados).filter(
    ([, v]) => v && typeof v === "object" && !Array.isArray(v),
  );
  const soltos = Object.entries(dados).filter(
    ([, v]) => !(v && typeof v === "object" && !Array.isArray(v)),
  );
  const bloco = (titulo: string | null, obj: Record<string, unknown>) => {
    const entradas = Object.entries(obj)
      .filter(([, v]) => v !== null && v !== "")
      .map(([k, v]) => [k, valorLegivel(v)] as const);
    if (entradas.length === 0) return null;
    // curtos primeiro: assim a grade fecha suas colunas antes de o campo de
    // extensão tomar a linha inteira (senão sobram buracos no meio da grade)
    const ordenadas = [
      ...entradas.filter(([, v]) => !ehLongo(v)),
      ...entradas.filter(([, v]) => ehLongo(v)),
    ];
    return (
      <div key={titulo ?? "raiz"} className="mb-5 last:mb-0">
        {titulo && (
          <p className="field-label mb-2.5 border-b border-hairline pb-1.5">
            {humanizar(titulo)}
          </p>
        )}
        <div className="data-grid">
          {ordenadas.map(([k, v]) => (
            <CampoFonte key={k} rotulo={humanizar(k)} valor={v} abrirTudo={abrirTudo} />
          ))}
        </div>
      </div>
    );
  };
  return (
    <>
      {soltos.length > 0 && bloco(null, Object.fromEntries(soltos))}
      {grupos.map(([g, obj]) => bloco(g, obj as Record<string, unknown>))}
    </>
  );
}

function Secao({
  titulo,
  acao,
  children,
  className,
}: {
  titulo: string;
  /** Controle no canto direito do cabeçalho (ex.: "Ampliar tudo"). */
  acao?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("card p-5", className)}>
      <div className="mb-3.5 flex items-center justify-between gap-3 border-b border-hairline pb-2">
        <h2 className="label-mono">{titulo}</h2>
        {acao}
      </div>
      {children}
    </section>
  );
}

const CANAIS = [
  ["painel", "Painel"],
  ["email", "E-mail"],
  ["wpp", "WhatsApp"],
] as const;

function Carregando() {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-36 w-full" />
      <div className="grid gap-5 md:grid-cols-2">
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
    </div>
  );
}

export default function PropostaDetalhePage() {
  const params = useParams<{ id: string }>();
  // módulos efetivos do perfil — decide se a seção de pareceres (exploração
  // ao vivo do módulo captação) aparece; o detalhe em si é panel-core (§40)
  const { perfil } = useTerritorio();
  const [p, setP] = useState<Proposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [favorita, setFavorita] = useState(false);
  const [monitorando, setMonitorando] = useState(false);
  const [canais, setCanais] = useState<string[]>(["painel"]);
  // Aviso da tela com TOM: os erros (favorita que não salvou, PDF que falhou)
  // não podem sair pintados de verde como se fossem sucesso.
  const [msg, setMsg] = useState<{ tom: "ok" | "erro"; texto: string } | null>(
    null,
  );
  // "Ampliar tudo" da seção de dados da fonte (campos de extensão longa)
  const [abrirTudo, setAbrirTudo] = useState(false);

  useEffect(() => {
    void (async () => {
      const { data, error } = await api.GET("/api/v1/proposals/{proposta_id}", {
        params: { path: { proposta_id: params.id } },
      });
      if (error) {
        setErro("Proposta não encontrada (ou fora do seu território).");
        return;
      }
      setP(data as Proposta);
      const [fav, mon] = await Promise.all([
        api.GET("/api/v1/favorites"),
        api.GET("/api/v1/monitors"),
      ]);
      if (fav.data)
        setFavorita(
          (fav.data as { proposta_id: string }[]).some(
            (f) => f.proposta_id === params.id,
          ),
        );
      if (mon.data)
        setMonitorando(
          (mon.data as { proposta_id: string; ativo: boolean }[]).some(
            (m) => m.proposta_id === params.id && m.ativo,
          ),
        );
    })();
  }, [params.id]);

  async function alternarFavorito() {
    const proximo = !favorita;
    setFavorita(proximo); // otimista — a estrela responde na hora
    const { error } = proximo
      ? await api.POST("/api/v1/favorites", { body: { proposta_id: params.id } })
      : await api.DELETE("/api/v1/favorites/{proposta_id}", {
          params: { path: { proposta_id: params.id } },
        });
    if (error) {
      // desfaz E avisa — o rollback mudo lia como "favoritei e não persistiu"
      setFavorita(!proximo);
      setMsg({
        tom: "erro",
        texto: proximo
          ? "Não foi possível favoritar agora — tente novamente."
          : "Não foi possível remover a favorita agora — tente novamente.",
      });
    }
  }

  async function monitorar() {
    const { error } = await api.POST("/api/v1/monitors", {
      body: { proposta_id: params.id, canais },
    });
    if (!error) {
      setMonitorando(true);
      setMsg({
        tom: "ok",
        texto: "Monitorando: você recebe aviso quando a situação ou o prazo mudar.",
      });
    }
  }

  if (erro) {
    return (
      <div className="flex flex-col items-start gap-4">
        <Aviso tom="erro">{erro}</Aviso>
        <Link href="/panel/funding" className="btn btn-ghost btn-sm">
          ← Voltar à captação
        </Link>
      </div>
    );
  }
  if (!p) return <Carregando />;

  // Ano da proposta (safra): o computado pela API (ANO_PROP na fonte), com
  // retaguarda no ano da data de criação já ingerida.
  const anoProposta = p.ano ?? (p.data_proposta ? p.data_proposta.slice(0, 4) : null);
  const disponivel = p.tipo === "disponivel";
  // §40: o detalhe é panel-core; o módulo captação governa só a consulta ATIVA
  // às fontes (o botão "Consultar fonte" das seções de andamento e emenda).
  const podeExplorar = (perfil?.modulos ?? []).includes("captacao");
  const empenhadoAUtilizar = p.execucao
    ? Math.max(0, num(p.execucao.valor_empenhado) - num(p.execucao.valor_pago))
    : 0;

  return (
    <div className="flex flex-col gap-5">
      {/* ── Cabeçalho compacto: contexto, não protagonismo ───────────── */}
      <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        {/* Hierarquia (seção 23): MUNICÍPIO → objeto → números → identificadores.
            O município é a identidade do registro, então encabeça o header; o
            código IBGE desce para linha de apoio e o id da fonte sai daqui. */}
        <div className="min-w-0">
          <Link
            href="/panel/funding"
            className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 transition-colors hover:text-ink"
          >
            ← Captação
          </Link>
          <h1 className="page-title mt-1.5">{municipioPrincipal(p)}</h1>
          {municipioSecundario(p) && (
            <p className="mt-0.5 font-mono text-[11px] tracking-[0.04em] text-ink-3">
              {municipioSecundario(p)}
            </p>
          )}
          {/* O objeto da proposta vem logo abaixo — nunca um identificador:
              antes o h1 caía para `id_externo` quando faltava título. */}
          <p className="mt-2 text-lg font-semibold leading-snug text-ink">
            {humanizarCaixa(p.titulo ?? p.objeto) || "Proposta sem título na fonte"}
          </p>
          {/* Nº da proposta e data de criação: é assim que o gestor se refere a
              ela ("14275/2026, de 26/03") e é o que ele digita para conferir no
              portal da fonte. Dado de cabeçalho — diferente de `id_externo`/UUID,
              que são plumbing e ficam em "Dados gerais". */}
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
            {p.numero_proposta ? (
              // mesma pílula da lista e do feed: o gestor reconhece o número
              // pelo formato e daqui copia para colar no portal da fonte
              <NumeroProposta numero={p.numero_proposta} />
            ) : (
              <span>
                Proposta <span className="num text-ink-3">sem nº na fonte</span>
              </span>
            )}
            <Hint chave="proposta.numero_proposta" className="align-middle" />
            {p.data_proposta && (
              <>
                <span className="text-ink-3">·</span>
                <span>
                  criada em{" "}
                  <span className="num text-ink">{formatDate(p.data_proposta)}</span>
                </span>
              </>
            )}
          </p>
          {/* Órgão concedente: quem repassa o recurso. É o que define a porta de
              entrada da proposta, então acompanha o número no cabeçalho em vez
              de ficar só na grade de dados. */}
          {p.orgao_superior && (
            <p className="mt-1 text-sm text-ink-2">
              {humanizarCaixa(p.orgao_superior)}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-2">
            <span className="font-mono text-xs uppercase tracking-[0.04em]">
              {p.fonte}
            </span>
            <StatusBadge tone={disponivel ? "success" : "neutral"}>
              {disponivel ? "oportunidade disponível" : "cadastrada"}
            </StatusBadge>
          </div>
          {/* pílulas de categoria (curadoria) — do que esta proposta trata */}
          {(p.categorias ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {p.categorias!.map((c) => (
                <span
                  key={c.slug}
                  className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 text-xs text-ink-2"
                >
                  <span className="brand-dot" aria-hidden />
                  {c.rotulo}
                </span>
              ))}
            </div>
          )}
        </div>
        {/* Ações agrupadas — nunca um botão grande solto no canto */}
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={alternarFavorito}
            aria-pressed={favorita}
            className={cx("btn btn-sm", favorita ? "btn-accent" : "btn-ghost")}
          >
            {favorita ? "★ Favorita" : "☆ Favoritar"}
          </button>
          {/* atalho "P": o gestor exporta sem tirar a mão do teclado */}
          <BotaoEspelho
            propostaId={params.id}
            atalho="p"
            onResultado={(texto, tom) => setMsg({ tom, texto })}
          />
          {p.url_origem && (
            <a
              href={p.url_origem}
              target="_blank"
              rel="noreferrer"
              className="btn btn-ghost btn-sm"
            >
              Fonte oficial ↗
            </a>
          )}
        </div>
      </header>

      {msg && <Aviso tom={msg.tom}>{msg.texto}</Aviso>}

      {/* ── FAIXA DE DESTAQUE ────────────────────────────────────────
          O topo da hierarquia: valor, empenho e a SAFRA da proposta
          (ano de criação na fonte). Tudo o mais é subordinado. */}
      {/* Dois degraus DENTRO da faixa: valor/empenho/ano ocupam a linha de
          cima inteira; o resto desce um nível. Quatro colunas de peso igual
          não cabiam — os números colidiam. */}
      <section className="hero-band anim-page-delayed">
        <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
          <div className="field">
            <span className="field-label">
              Valor total <Hint chave="proposta.valor_total" />
            </span>
            <span className="value-hero">{formatBRL(p.valor_total)}</span>
            {p.contrapartida && num(p.contrapartida) > 0 && (
              <span className="num mt-1 text-xs text-ink-3">
                contrapartida <Hint chave="proposta.contrapartida" className="mr-1 align-middle" />
                {formatBRL(p.contrapartida)}
              </span>
            )}
          </div>

          {/* EMPENHO no primeiro degrau: é o que diz se o recurso saiu do
              papel. Antes vivia lá embaixo, na grade secundária. */}
          {/* O hint contextual em ação: o ⓘ ao lado de "Empenhado" abre o
              artigo que o admin plantou na chave proposta.empenhado. */}
          <div className="field">
            <span className="field-label">
              Empenhado <Hint chave="proposta.empenhado" />
            </span>
            {p.execucao ? (
              <>
                <span className="value-hero">
                  {formatBRL(p.execucao.valor_empenhado)}
                </span>
                <span className="num mt-1 text-xs text-ink-3">
                  {empenhadoAUtilizar > 0
                    ? `${formatBRL(String(empenhadoAUtilizar))} a utilizar`
                    : "nada a utilizar"}
                </span>
              </>
            ) : (
              <>
                <span className="value-hero text-ink-3">—</span>
                <span className="num mt-1 text-xs text-ink-3">
                  sem execução informada
                </span>
              </>
            )}
          </div>

          {/* ANO da proposta no lugar do prazo de vencimento: a safra (ANO_PROP)
              é o que situa a proposta — o prazo vinha marcado errado com
              frequência e segue disponível na seção "Prazos", abaixo. */}
          <div className="field">
            <span className="field-label">
              Ano da proposta <Hint chave="proposta.ano" />
            </span>
            {anoProposta ? (
              <>
                <span className="value-hero num">{anoProposta}</span>
                <span className="mt-1 font-mono text-xs uppercase tracking-[0.04em] text-ink-3">
                  {p.data_proposta
                    ? `criada em ${formatDate(p.data_proposta)}`
                    : "ano de criação na fonte"}
                </span>
              </>
            ) : (
              <>
                <span className="value-hero text-ink-3">—</span>
                <span className="num mt-1 text-xs text-ink-3">
                  sem ano informado na fonte
                </span>
              </>
            )}
          </div>
        </div>

        <hr className="hairline-rule" />

        <div className="data-grid">
          <div className="field">
            <span className="field-label">
              Situação <Hint chave="proposta.situacao" />
            </span>
            <span className="mt-0.5">
              <StatusBadge tone={tomSituacao(p.situacao)}>
                {humanizarCaixa(p.situacao) || "sem registro"}
              </StatusBadge>
            </span>
          </div>

          {/* "Empenhado a utilizar" subiu para a faixa de destaque, junto do
              valor empenhado — não se repete aqui. */}
          <Dado
            rotulo={
              <>
                Pendências <Hint chave="proposta.pendencias" />
              </>
            }
            valor={
              (p.pendencias ?? []).length === 0
                ? "nenhuma"
                : `${(p.pendencias ?? []).length} a resolver`
            }
            tom={(p.pendencias ?? []).length > 0 ? "warn" : "ok"}
            destaque
          />

          <Dado
            rotulo={
              <>
                Modalidade <Hint chave="proposta.modalidade" />
              </>
            }
            valor={humanizarCaixa(p.modalidade)}
            destaque
          />
        </div>
      </section>

      {p.resumo_ia && (
        <Secao titulo="Resumo inteligente">
          <p className="text-sm leading-relaxed text-ink-2">{p.resumo_ia}</p>
        </Secao>
      )}

      {/* ── Prazos e pendências: segundo degrau, largura inteira ────── */}
      <div className="stagger grid gap-5 md:grid-cols-2">
        {/* o ⓘ do prazo mora aqui agora — o cabeçalho mostra a safra */}
        <Secao titulo="Prazos" acao={<Hint chave="proposta.prazo" />}>
          {(p.prazos ?? []).length === 0 ? (
            <p className="text-sm text-ink-3">Sem prazos registrados.</p>
          ) : (
            <ul>
              {p.prazos!.map((pr, i) => {
                const d = diasAte(pr.data_limite);
                const tom = tomPrazo(d);
                return (
                  <li key={i} className="data-row">
                    <span className="text-sm">{humanizarCaixa(pr.tipo) || "prazo"}</span>
                    <span className="flex shrink-0 items-baseline gap-2">
                      <span className={cx("num text-sm", tom && `tone-${tom}`)}>
                        {formatDate(pr.data_limite)}
                      </span>
                      <span
                        className={cx(
                          "font-mono text-[11px] uppercase tracking-[0.04em]",
                          tom ? `tone-${tom}` : "text-ink-3",
                        )}
                      >
                        {prazoLabel(pr.data_limite)}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Secao>

        <Secao titulo="Pendências">
          {(p.pendencias ?? []).length === 0 ? (
            <p className="tone-ok text-sm">✓ Sem pendências.</p>
          ) : (
            <ul>
              {p.pendencias!.map((pe, i) => {
                const d = diasAte(pe.prazo);
                const tom = tomPrazo(d);
                return (
                  <li key={i} className="data-row">
                    <span className="text-sm">{humanizarCaixa(pe.descricao) || "—"}</span>
                    {pe.prazo && (
                      <span className={cx("num shrink-0 text-sm", tom && `tone-${tom}`)}>
                        {formatDate(pe.prazo)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Secao>
      </div>

      {/* ── Execução financeira: largura inteira, a barra precisa dela ─ */}
      {p.execucao && (
        <Secao
          titulo={`Execução financeira — TransfereGov${
            p.execucao.ano ? ` (${p.execucao.ano})` : ""
          }`}
          acao={<Hint chave="proposta.execucao" />}
        >
          {(() => {
            const global = num(p.execucao!.valor_global ?? p.valor_total);
            const empenhado = num(p.execucao!.valor_empenhado);
            const liberado = num(p.execucao!.valor_liberado);
            const pago = num(p.execucao!.valor_pago);
            const pct = (v: number) =>
              global > 0 ? `${Math.min(100, (v / global) * 100)}%` : "0%";
            return (
              <div className="flex flex-col gap-4">
                <div
                  className="relative h-3 overflow-hidden rounded-full bg-surface-2"
                  title="Barra sobre o valor global: empenhado, liberado e pago"
                >
                  <div
                    className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ease-out"
                    style={{ width: pct(empenhado), background: "var(--bar-1)" }}
                  />
                  <div
                    className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ease-out"
                    style={{ width: pct(liberado), background: "var(--bar-2)" }}
                  />
                  <div
                    className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ease-out"
                    style={{ width: pct(pago), background: "var(--bar-3)" }}
                  />
                </div>
                <div className="data-grid">
                  <Dado
                    rotulo="Valor global"
                    valor={formatBRL(p.execucao!.valor_global)}
                    destaque
                  />
                  <Dado
                    rotulo="Empenhado"
                    valor={formatBRL(p.execucao!.valor_empenhado)}
                    destaque
                  />
                  <Dado rotulo="Liberado" valor={formatBRL(p.execucao!.valor_liberado)} />
                  <Dado rotulo="Pago" valor={formatBRL(p.execucao!.valor_pago)} />
                  <Dado
                    rotulo="Saldo em conta"
                    valor={formatBRL(p.execucao!.saldo_conta)}
                  />
                  <Dado
                    rotulo="Empenhado a utilizar"
                    valor={formatBRL(String(empenhadoAUtilizar))}
                    tom={empenhadoAUtilizar > 0 ? "ok" : undefined}
                    destaque
                  />
                </div>
                <hr className="hairline-rule" />
                <div className="data-grid">
                  <Dado
                    rotulo="Tipo"
                    valor={humanizarCaixa(p.execucao!.tipo_transferencia)}
                  />
                  <Dado
                    rotulo="Ente recebedor"
                    valor={humanizarCaixa(p.execucao!.ente_recebedor)}
                  />
                  <Dado
                    rotulo="Natureza jurídica"
                    valor={humanizarCaixa(
                      p.natureza_juridica ?? p.execucao!.natureza_juridica,
                    )}
                  />
                  <Dado
                    rotulo="Assinatura"
                    valor={formatDate(p.execucao!.data_assinatura)}
                  />
                  <Dado
                    rotulo="Início da vigência"
                    valor={formatDate(p.execucao!.data_inicio_vigencia)}
                  />
                  <Dado
                    rotulo="Fim da vigência"
                    valor={formatDate(p.execucao!.data_fim_vigencia)}
                    tom={tomPrazo(diasAte(p.execucao!.data_fim_vigencia))}
                  />
                </div>
              </div>
            );
          })()}
        </Secao>
      )}

      <div className="stagger grid gap-5 md:grid-cols-2">
        <Secao titulo="Dados gerais">
          <div className="data-grid">
            {/* Município nomeado; o código IBGE aparece rotulado logo abaixo,
                como apoio — antes este campo mostrava só o número. */}
            <Dado rotulo="Município" valor={municipioPrincipal(p)} />
            <Dado rotulo="Código IBGE" valor={p.municipio_ibge} />
            <Dado rotulo="Órgão superior" valor={humanizarCaixa(p.orgao_superior)} />
            <Dado rotulo="Modalidade" valor={humanizarCaixa(p.modalidade)} />
            <Dado rotulo="Emenda" valor={p.emenda} />
            <Dado rotulo="Natureza jurídica" valor={p.natureza_juridica} />
            <Dado
              rotulo="Nº da proposta"
              valor={p.numero_proposta ?? p.id_externo}
            />
            <Dado rotulo="Identificador na fonte" valor={p.id_externo} />
            <Dado
              rotulo="Criada na fonte"
              valor={formatDate(p.data_proposta)}
            />
            <Dado
              rotulo="Atualizado na fonte"
              valor={formatDate(p.data_atualizacao_fonte)}
            />
            <Dado
              rotulo="Cache atualizado"
              valor={formatDateTime(p.cache_atualizado_em)}
            />
          </div>
          {p.objeto && (
            <>
              <hr className="hairline-rule my-4" />
              <div className="field">
                <span className="field-label">Objeto</span>
                {/* o objeto é o outro campo de extensão livre da fonte */}
                <TextoExpansivel texto={humanizarCaixa(p.objeto)} linhas={4} />
              </div>
            </>
          )}
        </Secao>

        <Secao titulo="Situação e movimentação">
          <div className="flex flex-col gap-4">
            <div className="field">
              <span className="field-label">Situação</span>
              <span className="value-lg">{humanizarCaixa(p.situacao) || "—"}</span>
            </div>
            <div className="field">
              <span className="field-label">Última movimentação</span>
              {p.movimentacao ? (
                <TextoExpansivel texto={humanizarCaixa(p.movimentacao)} linhas={4} />
              ) : (
                <p className="text-sm leading-relaxed text-ink-3">
                  Sem movimentação registrada.
                </p>
              )}
            </div>
          </div>
        </Secao>
      </div>

      {/* Andamento e emenda são leitura de CACHE (panel-core, §40) — ficam na
          tela mesmo com a captação desligada. O que o módulo governa é a
          consulta AO VIVO, então só o botão "Consultar fonte" depende dele. */}
      <AndamentoProposta proposta={p} podeConsultarFonte={podeExplorar} />

      <EmendasProposta proposta={p} podeConsultarFonte={podeExplorar} />

      <Secao titulo="Acompanhar e ser avisado">
        {monitorando ? (
          <p className="tone-ok text-sm">
            ✓ Você monitora esta proposta — aviso quando mudar status ou prazo.
          </p>
        ) : (
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap gap-2">
              {CANAIS.map(([valor, rotulo]) => {
                const ativo = canais.includes(valor);
                const fixo = valor === "painel";
                return (
                  <button
                    key={valor}
                    type="button"
                    disabled={fixo}
                    aria-pressed={ativo}
                    onClick={() =>
                      setCanais((prev) =>
                        prev.includes(valor)
                          ? prev.filter((c) => c !== valor)
                          : [...prev, valor],
                      )
                    }
                    className={cx(
                      "chip",
                      ativo && "chip-active",
                      fixo && "cursor-default opacity-70",
                    )}
                  >
                    {rotulo}
                  </button>
                );
              })}
            </div>
            <button onClick={monitorar} className="btn btn-primary btn-sm">
              Monitorar proposta-chave
            </button>
          </div>
        )}
      </Secao>

      {p.dados_fonte && Object.keys(p.dados_fonte).length > 0 && (
        <Secao
          titulo="Dados completos da fonte"
          acao={
            <button
              type="button"
              onClick={() => setAbrirTudo((v) => !v)}
              aria-expanded={abrirTudo}
              className="btn btn-ghost btn-sm"
            >
              {abrirTudo ? "Recolher tudo ↑" : "Ampliar tudo ↓"}
            </button>
          }
        >
          <p className="mb-4 text-xs text-ink-3">
            Todos os campos como vêm da origem — a mesma informação que você veria
            direto no site oficial. Campos longos entram recortados; use{" "}
            <span className="font-mono">Ampliar</span> para ler por inteiro.
          </p>
          <DadosCompletos dados={p.dados_fonte} abrirTudo={abrirTudo} />
        </Secao>
      )}

      {p.proveniencia && Object.keys(p.proveniencia).length > 0 && (
        <Secao titulo="Proveniência dos dados (API × painel)">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(p.proveniencia).map(([campo, origem]) => (
              <span
                key={campo}
                className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 font-mono text-[11px] text-ink-2"
              >
                <span
                  className={cx(
                    "h-1.5 w-1.5 rounded-full",
                    origem === "api" ? "bg-aqua" : "bg-lime",
                  )}
                  aria-hidden
                />
                {campo}: {origem}
              </span>
            ))}
          </div>
        </Secao>
      )}
    </div>
  );
}
