"use client";

/**
 * UI kit do painel — o vocabulário novo de seletores, menus e caixas.
 *
 * Antes cada tela montava o seu: o território era um popover artesanal no
 * trilho, a origem eram chips soltos, o ano outra fileira de chips e cada
 * lista desenhava a própria linha. O resultado é que dois filtros da mesma
 * página não se pareciam e nenhum deles se parecia com o que o gestor usa em
 * qualquer outro sistema. Aqui mora UMA implementação de cada peça:
 *
 * - `Seletor`      gatilho (rótulo em cima, valor embaixo) + menu suspenso;
 * - `ItemMenu`     linha do menu, com caixa de seleção ou marca de escolha;
 * - `SeletorMultiplo` escolha de VÁRIOS sobre uma lista (nenhum = todos);
 * - `ChipFiltro`   filtro APLICADO, com × para remover;
 * - `Caixa`        a unidade de conteúdo (cabeçalho + corpo) do painel.
 *
 * O estilo vive em `globals.css` (bloco "UI KIT"), em tokens de tema — claro
 * e escuro saem do mesmo markup, e a v1 (§48) porta o kit junto.
 */

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cx } from "@/components/ui";
import { filtrarPorBusca } from "@/lib/busca";

/** A partir de quantas opções o menu ganha campo de busca. */
const COM_BUSCA = 8;

/* ─────────────────────────────────────────────────────── Seletor ──────── */

/** Folga entre o menu e a borda da janela, e entre o menu e o gatilho (px). */
const FOLGA_JANELA = 8;
const FOLGA_GATILHO = 6;
/** Abaixo disso de espaço livre sob o gatilho, o menu abre para CIMA (px). */
const ALTURA_CONFORTAVEL = 280;
/** Teto de altura do menu, mesmo com a janela inteira livre (px). */
const ALTURA_TETO = 560;

type Posicao = {
  left: number;
  top?: number;
  bottom?: number;
  alturaMax: number;
  paraCima: boolean;
};

const SELETOR_FOCAVEL =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

export function Seletor({
  rotulo,
  valor,
  ativo = false,
  alinhar = "start",
  largura,
  titulo,
  aoFechar,
  children,
}: {
  /** Rótulo fixo do gatilho ("Município", "Origem do recurso"). */
  rotulo: string;
  /** O que está escolhido AGORA — é o que o gestor lê sem abrir o menu. */
  valor: string;
  /** Há recorte aplicado (o gatilho ganha o tom do acento). */
  ativo?: boolean;
  alinhar?: "start" | "end";
  largura?: string;
  titulo?: string;
  /** Chamado sempre que o menu fecha — quem tem campo de busca o limpa aqui:
   *  reabrir o menu com o termo antigo mostrava a lista já recortada, e os
   *  municípios "sumiam" sem o gestor ter digitado nada. */
  aoFechar?: () => void;
  /** Conteúdo do menu; recebe `fechar` para itens que encerram a escolha. */
  children: (fechar: () => void) => ReactNode;
}) {
  const [aberto, setAberto] = useState(false);
  const [pos, setPos] = useState<Posicao | null>(null);
  const caixa = useRef<HTMLDivElement>(null);
  const gatilho = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const idMenu = useId();
  // em ref: `fechar` precisa ser estável (é dependência dos efeitos abaixo)
  const aoFecharRef = useRef(aoFechar);
  useLayoutEffect(() => {
    aoFecharRef.current = aoFechar;
  });

  const fechar = useCallback(() => {
    setAberto(false);
    setPos(null);
    aoFecharRef.current?.();
  }, []);

  /* O menu é desenhado num PORTAL no <body>, com posição fixa calculada a
     partir do gatilho. Dentro da árvore ele herdava o `overflow: hidden` do
     `.card` (a barra de filtros da Captação é um card): a lista era cortada
     na borda do card, sumiam os municípios e a barra de rolagem junto — o
     gestor via só "Todo o território" e um pedaço da linha seguinte. Mesma
     razão do `Modal`. */
  const posicionar = useCallback(() => {
    const g = gatilho.current;
    if (!g) return;
    const r = g.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const abaixo = vh - r.bottom - FOLGA_GATILHO - FOLGA_JANELA;
    const acima = r.top - FOLGA_GATILHO - FOLGA_JANELA;
    // abre para cima só quando embaixo não cabe com conforto E em cima cabe mais
    const paraCima = abaixo < ALTURA_CONFORTAVEL && acima > abaixo;
    const alturaMax = Math.max(
      120,
      Math.min(paraCima ? acima : abaixo, ALTURA_TETO),
    );
    const larguraMenu = menu.current?.getBoundingClientRect().width ?? 0;
    let left = alinhar === "end" ? r.right - larguraMenu : r.left;
    // nunca vaza da janela — no celular o gatilho da direita empurraria o
    // menu para fora da tela
    left = Math.min(left, vw - FOLGA_JANELA - larguraMenu);
    left = Math.max(FOLGA_JANELA, left);
    const nova: Posicao = {
      left,
      top: paraCima ? undefined : r.bottom + FOLGA_GATILHO,
      bottom: paraCima ? vh - r.top + FOLGA_GATILHO : undefined,
      alturaMax,
      paraCima,
    };
    // mesma posição = mesmo estado: sem isso o observador de tamanho e o
    // re-render se alimentariam em laço
    setPos((atual) =>
      atual &&
      atual.left === nova.left &&
      atual.top === nova.top &&
      atual.bottom === nova.bottom &&
      atual.alturaMax === nova.alturaMax &&
      atual.paraCima === nova.paraCima
        ? atual
        : nova,
    );
  }, [alinhar]);

  // Antes da pintura: o menu nasce já no lugar (sem piscar no canto da tela).
  useLayoutEffect(() => {
    if (aberto) posicionar();
  }, [aberto, posicionar]);

  // Acompanha rolagem (de qualquer contêiner), redimensionamento da janela e
  // mudança de tamanho do próprio menu (a busca encolhe a lista).
  useEffect(() => {
    if (!aberto) return;
    let quadro = 0;
    const agendar = () => {
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(posicionar);
    };
    window.addEventListener("scroll", agendar, true);
    window.addEventListener("resize", agendar);
    const observador =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(agendar) : null;
    if (menu.current) observador?.observe(menu.current);
    return () => {
      cancelAnimationFrame(quadro);
      window.removeEventListener("scroll", agendar, true);
      window.removeEventListener("resize", agendar);
      observador?.disconnect();
    };
  }, [aberto, posicionar]);

  // Fecha no clique fora e no Esc — e devolve o foco ao gatilho, senão o
  // teclado cai no começo da página a cada menu fechado. "Fora" agora são
  // DOIS lugares: o gatilho e o menu (que mora no portal).
  useEffect(() => {
    if (!aberto) return;
    function fora(e: MouseEvent) {
      const alvo = e.target as Node;
      if (caixa.current?.contains(alvo) || menu.current?.contains(alvo)) return;
      fechar();
    }
    function tecla(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      fechar();
      gatilho.current?.focus();
    }
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto, fechar]);

  // No portal o menu fica no FIM do documento: sem isto, Tab a partir do
  // gatilho pularia o menu inteiro e Tab no último item cairia no rodapé.
  function focaveis(): HTMLElement[] {
    return Array.from(
      menu.current?.querySelectorAll<HTMLElement>(SELETOR_FOCAVEL) ?? [],
    );
  }
  function tabNoGatilho(e: ReactKeyboardEvent) {
    if (!aberto || e.key !== "Tab" || e.shiftKey) return;
    const [primeiro] = focaveis();
    if (!primeiro) return;
    e.preventDefault();
    primeiro.focus();
  }
  function tabNoMenu(e: ReactKeyboardEvent) {
    if (e.key !== "Tab") return;
    const lista = focaveis();
    const sai = e.shiftKey
      ? document.activeElement === lista[0]
      : document.activeElement === lista[lista.length - 1];
    if (!sai) return;
    e.preventDefault();
    fechar();
    gatilho.current?.focus();
  }

  return (
    <div ref={caixa} className="relative">
      <button
        ref={gatilho}
        type="button"
        onClick={() => (aberto ? fechar() : setAberto(true))}
        onKeyDown={tabNoGatilho}
        aria-expanded={aberto}
        aria-haspopup="true"
        aria-controls={aberto ? idMenu : undefined}
        title={titulo}
        className={cx("trigger", ativo && "trigger-on")}
      >
        <span className="trigger-txt">
          <span className="trigger-label">{rotulo}</span>
          <span className="trigger-value">{valor}</span>
        </span>
        <Caret />
      </button>

      {aberto &&
        createPortal(
          <div
            id={idMenu}
            ref={menu}
            onKeyDown={tabNoMenu}
            className={cx("menu menu-flutuante", pos && "anim-pop")}
            style={{
              ...(largura ? { minWidth: largura } : {}),
              left: pos?.left ?? 0,
              top: pos ? pos.top : 0,
              bottom: pos?.bottom,
              maxHeight: pos?.alturaMax,
              transformOrigin: pos?.paraCima ? "bottom" : "top",
              // até a 1ª medida o menu existe só para ser medido. Opacidade, não
              // `visibility: hidden`: elemento invisível não recebe foco, e o
              // `autoFocus` do campo de busca roda justamente nesse instante
              opacity: pos ? undefined : 0,
            }}
          >
            {children(fechar)}
          </div>,
          document.body,
        )}
    </div>
  );
}

function Caret() {
  return (
    <svg
      className="trigger-caret"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

/* ───────────────────────────────────────────────────── Itens do menu ──── */

/** Caixa de seleção (ou marca redonda, para escolha única). */
export function Marca({ on, radio = false }: { on: boolean; radio?: boolean }) {
  return (
    <span className={cx("ck", radio && "ck-radio", on && "ck-on")} aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 12l5 5L20 7" />
      </svg>
    </span>
  );
}

export function ItemMenu({
  marcado,
  radio,
  rotulo,
  contagem,
  acessorio,
  onClick,
  title,
}: {
  marcado: boolean;
  radio?: boolean;
  rotulo: ReactNode;
  /** Número à direita (quantos registros a opção tem no recorte). */
  contagem?: number | string;
  /** Ação secundária, revelada no hover (ex.: "só este"). */
  acessorio?: ReactNode;
  onClick: () => void;
  title?: string;
}) {
  return (
    <div className="group flex items-center gap-1">
      <button
        type="button"
        role="option"
        aria-selected={marcado}
        onClick={onClick}
        title={title}
        className={cx("menu-item min-w-0 flex-1", marcado && "menu-item-on")}
      >
        <Marca on={marcado} radio={radio} />
        <span className="min-w-0 flex-1 truncate">{rotulo}</span>
        {contagem !== undefined && (
          <span className="shrink-0 tabular-nums text-[11.5px] text-ink-3">
            {contagem}
          </span>
        )}
      </button>
      {acessorio}
    </div>
  );
}

/** Seletor de escolha ÚNICA sobre uma lista de opções (ordenação, área,
 *  faceta com contagem…). É o substituto do `<select>` nativo nas barras de
 *  filtro: mesma forma dos demais seletores, a opção escolhida à vista sem
 *  abrir o menu, a contagem visível na lista e busca quando ela é longa —
 *  três coisas que o nativo não dá. */
export function SeletorSimples({
  rotulo,
  valor,
  opcoes,
  vazio = "Todas",
  largura,
  alinhar,
  aoMudar,
}: {
  rotulo: string;
  valor: string;
  opcoes: { valor: string; rotulo: string; total?: number }[];
  /** Rótulo da opção "sem filtro" (valor ""). Null remove a opção. */
  vazio?: string | null;
  largura?: string;
  alinhar?: "start" | "end";
  aoMudar: (v: string) => void;
}) {
  const [busca, setBusca] = useState("");
  const atual = opcoes.find((o) => o.valor === valor);
  const lista = filtrarPorBusca(opcoes, busca, (o) => o.rotulo);

  return (
    <Seletor
      rotulo={rotulo}
      valor={atual?.rotulo ?? vazio ?? valor}
      ativo={Boolean(valor)}
      largura={largura}
      alinhar={alinhar}
      aoFechar={() => setBusca("")}
    >
      {(fechar) => (
        <>
          {opcoes.length >= COM_BUSCA && (
            <div className="menu-head">
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder={`Filtrar ${rotulo.toLowerCase()}…`}
                className="input w-full text-sm"
                autoFocus
              />
            </div>
          )}
          {vazio !== null && (
            <>
              <ItemMenu
                marcado={!valor}
                radio
                rotulo={vazio}
                onClick={() => {
                  aoMudar("");
                  fechar();
                }}
              />
              <div className="menu-sep" />
            </>
          )}
          <div className="menu-scroll" role="listbox" aria-label={rotulo}>
            {lista.map((o) => (
              <ItemMenu
                key={o.valor}
                marcado={o.valor === valor}
                radio
                rotulo={o.rotulo}
                contagem={o.total}
                onClick={() => {
                  aoMudar(o.valor);
                  fechar();
                }}
              />
            ))}
            {lista.length === 0 && (
              <p className="px-2 py-2 text-sm text-ink-3">
                Nenhuma opção com esse nome.
              </p>
            )}
          </div>
        </>
      )}
    </Seletor>
  );
}

/* ──────────────────────────────────────────────────── Chip aplicado ───── */

export function ChipFiltro({
  children,
  onRemover,
  title,
}: {
  children: ReactNode;
  onRemover: () => void;
  title?: string;
}) {
  return (
    <span className="fchip">
      {children}
      <button
        type="button"
        onClick={onRemover}
        className="fchip-x"
        title={title ?? "Remover filtro"}
        aria-label={title ?? "Remover filtro"}
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden>
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </span>
  );
}

/* ────────────────────────────────────────────────────────── Caixa ─────── */

export function Caixa({
  titulo,
  sub,
  acoes,
  children,
  className,
  corpoRente = false,
}: {
  titulo: ReactNode;
  sub?: ReactNode;
  acoes?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Corpo colado nas bordas — para listas que já têm o próprio padding. */
  corpoRente?: boolean;
}) {
  return (
    <section className={cx("card", className)}>
      <div className="box-head">
        <div className="min-w-0">
          <h2 className="box-title">{titulo}</h2>
          {sub && <span className="box-sub">{sub}</span>}
        </div>
        {acoes && <div className="box-acts">{acoes}</div>}
      </div>
      <div className={corpoRente ? "box-body-flush" : "box-body"}>{children}</div>
    </section>
  );
}


/* ────────────────────────────────────────────── SeletorMultiplo ───────── */

/**
 * Escolha de VÁRIOS sobre uma lista fechada — município e origem do recurso
 * dentro de uma consulta salva (§61), por exemplo.
 *
 * Nada marcado = TODOS (o padrão), e marcar tudo um a um volta para nada: as
 * duas coisas dizem a mesma frase, e guardar "todos" item a item deixaria a
 * consulta presa numa lista que o perfil pode mudar amanhã.
 */
export function SeletorMultiplo({
  rotulo,
  titulo,
  rotuloTodos,
  opcoes,
  selecionados,
  aoMudar,
  largura = "17rem",
}: {
  rotulo: string;
  titulo?: string;
  /** Como se lê "sem recorte" nesta dimensão ("Todo o território"). */
  rotuloTodos: string;
  /** `busca`: texto extra que a busca também enxerga (o código IBGE). */
  opcoes: { valor: string; rotulo: string; busca?: string }[];
  selecionados: string[];
  aoMudar: (valores: string[]) => void;
  largura?: string;
}) {
  const [busca, setBusca] = useState("");
  const marcados = selecionados.filter((v) => opcoes.some((o) => o.valor === v));
  const tudo = marcados.length === 0;
  const valor = tudo
    ? `${rotuloTodos} (${opcoes.length})`
    : marcados.length === 1
      ? (opcoes.find((o) => o.valor === marcados[0])?.rotulo ?? marcados[0]!)
      : `${marcados.length} de ${opcoes.length}`;

  const alternar = (v: string) => {
    const novo = marcados.includes(v)
      ? marcados.filter((x) => x !== v)
      : [...marcados, v];
    aoMudar(novo.length === opcoes.length ? [] : novo);
  };

  // tolerante a acento e erro de digitação: "apuiarez" acha Apuiarés
  const lista = filtrarPorBusca(opcoes, busca, (o) =>
    o.busca ? `${o.rotulo} ${o.busca}` : o.rotulo,
  );

  return (
    <Seletor
      rotulo={rotulo}
      valor={valor}
      ativo={!tudo}
      largura={largura}
      titulo={titulo}
      aoFechar={() => setBusca("")}
    >
      {(fechar) => (
        <>
          {opcoes.length >= COM_BUSCA && (
            <div className="menu-head">
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Filtrar…"
                className="input w-full text-sm"
                autoFocus
              />
            </div>
          )}
          <ItemMenu
            marcado={tudo}
            radio
            rotulo={rotuloTodos}
            contagem={opcoes.length}
            onClick={() => {
              aoMudar([]);
              fechar();
            }}
          />
          <div className="menu-sep" />
          <div className="menu-scroll" role="listbox" aria-label={rotulo}>
            {lista.map((o) => (
              <ItemMenu
                key={o.valor}
                marcado={!tudo && marcados.includes(o.valor)}
                rotulo={o.rotulo}
                onClick={() => alternar(o.valor)}
                acessorio={
                  <button
                    type="button"
                    onClick={() => {
                      aoMudar([o.valor]);
                      fechar();
                    }}
                    title={`Só ${o.rotulo}`}
                    className="shrink-0 rounded px-1.5 py-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 opacity-0 transition hover:text-ink group-hover:opacity-100 focus:opacity-100"
                  >
                    só este
                  </button>
                }
              />
            ))}
            {lista.length === 0 && (
              <p className="px-2 py-2 text-sm text-ink-3">Nada com esse nome.</p>
            )}
          </div>
        </>
      )}
    </Seletor>
  );
}
