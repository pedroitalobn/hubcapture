import type { ReactNode } from "react";

/** Tons cheios da marca p/ KPIs que precisam contrastar com o canvas claro.
 *  `ink` usa os tokens de ação (inverte no tema escuro); lime/aqua/grad são
 *  preenchimentos fixos da marca com tinta abyss — legíveis nos dois temas. */
export type StatTone = "ink" | "lime" | "aqua" | "grad";

export interface StatCardProps {
  label: string;
  value: string;
  context?: string;
  icon?: ReactNode;
  tone?: StatTone;
  /** Valor por extenso quando `value` é compacto (vira tooltip do número). */
  title?: string;
  /** Com `onClick` o card vira BOTÃO de filtro (ponto 06): clicar recorta a
   *  lista abaixo dele. Sem `onClick` continua sendo leitura pura — o card
   *  não ganha afordância de clique que não leva a lugar nenhum. */
  onClick?: () => void;
  /** Estado do filtro que este card representa (só com `onClick`). */
  ativo?: boolean;
}

/** KPI stat card flat: label mono em caixa-alta + valor grande em peso único. */
export function StatCard({
  label,
  value,
  context,
  icon,
  tone,
  title,
  onClick,
  ativo = false,
}: StatCardProps) {
  // Botão de verdade quando clicável: teclado, foco e leitor de tela vêm de
  // graça, e o estado do filtro sai por `aria-pressed` — um `div` com onClick
  // deixaria o filtro inacessível para quem não usa mouse.
  const Elemento = onClick ? "button" : "div";
  return (
    <Elemento
      {...(onClick
        ? { type: "button" as const, onClick, "aria-pressed": ativo }
        : {})}
      className={`card p-5 ${tone ? `stat-${tone}` : ""} ${
        onClick
          ? `w-full cursor-pointer text-left transition-transform duration-200 hover:-translate-y-0.5 ${
              // O card ativo tem tinta cheia da marca por baixo: um anel lime
              // sumiria dentro dele. O contorno usa a TINTA do card (ink), que
              // contrasta nos quatro tons e nos dois temas.
              ativo ? "outline outline-2 outline-offset-2 outline-ink" : "card-hover"
            }`
          : "card-hover"
      }`}
    >
      <div className="flex items-center gap-2">
        {icon}
        <span className={`label-mono ${tone ? "text-inherit opacity-75" : ""}`}>
          {label}
        </span>
      </div>
      {/* key = valor: quando o recorte muda (ano, município), o número
          remonta e o anim-swap suaviza a troca em vez do corte seco */}
      <div key={value} className="anim-swap value-stat mt-3" title={title}>
        {value}
      </div>
      {context && (
        <div
          className={`mt-2 font-mono text-[11px] tracking-[-0.02em] ${
            tone ? "text-inherit opacity-70" : "text-ink-3"
          }`}
        >
          {context}
        </div>
      )}
    </Elemento>
  );
}
