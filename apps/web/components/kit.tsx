"use client";

/**
 * UI kit do painel — o vocabulário novo de seletores, menus e caixas.
 *
 * Antes cada tela montava o seu: o território era um popover artesanal no
 * trilho, a origem eram chips soltos, a safra outra fileira de chips e cada
 * lista desenhava a própria linha. O resultado é que dois filtros da mesma
 * página não se pareciam e nenhum deles se parecia com o que o gestor usa em
 * qualquer outro sistema. Aqui mora UMA implementação de cada peça:
 *
 * - `Seletor`      gatilho (rótulo em cima, valor embaixo) + menu suspenso;
 * - `ItemMenu`     linha do menu, com caixa de seleção ou marca de escolha;
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
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cx } from "@/components/ui";

/** A partir de quantas opções o menu ganha campo de busca. */
const COM_BUSCA = 8;

/* ─────────────────────────────────────────────────────── Seletor ──────── */

export function Seletor({
  rotulo,
  valor,
  ativo = false,
  alinhar = "start",
  largura,
  titulo,
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
  /** Conteúdo do menu; recebe `fechar` para itens que encerram a escolha. */
  children: (fechar: () => void) => ReactNode;
}) {
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const idMenu = useId();
  const fechar = useCallback(() => setAberto(false), []);

  // Fecha no clique fora e no Esc — e devolve o foco ao gatilho, senão o
  // teclado cai no começo da página a cada menu fechado.
  useEffect(() => {
    if (!aberto) return;
    function fora(e: MouseEvent) {
      if (!caixa.current?.contains(e.target as Node)) setAberto(false);
    }
    function tecla(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setAberto(false);
      caixa.current?.querySelector("button")?.focus();
    }
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto]);

  return (
    <div ref={caixa} className="relative">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
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

      {aberto && (
        <div
          id={idMenu}
          className={cx(
            "menu anim-pop mt-1.5",
            alinhar === "end" ? "right-0" : "left-0",
          )}
          style={largura ? { minWidth: largura } : undefined}
        >
          {children(fechar)}
        </div>
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
  const lista = busca.trim()
    ? opcoes.filter((o) =>
        o.rotulo.toLowerCase().includes(busca.trim().toLowerCase()),
      )
    : opcoes;

  return (
    <Seletor
      rotulo={rotulo}
      valor={atual?.rotulo ?? vazio ?? valor}
      ativo={Boolean(valor)}
      largura={largura}
      alinhar={alinhar}
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
