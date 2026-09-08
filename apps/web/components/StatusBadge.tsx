export type BadgeTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info";

/* Design system v1 (/previews/guia.html §5): badge SÓLIDO, 12px/600, raio 4.
   Antes era pill de contorno com um dot de 6px — quatro estados que exigem
   reações opostas ("em análise" e "pendência") saíam com a mesma aparência,
   um contorno cinza. A cor agora É a informação; o dot deixou de ser
   necessário porque o preenchimento já distingue à distância. */
const TOM: Record<BadgeTone, string> = {
  neutral: "bg-ink-3 text-white",
  success: "badge-ok",
  warning: "badge-warn",
  danger: "badge-danger",
  info: "badge-info",
};

/** Badge de status: preenchimento semântico + rótulo em caixa de frase.
 *
 * O badge NUNCA transborda o container. A `situacao` da proposta é texto
 * livre da fonte ("Proposta Aprovada e Plano de Trabalho Complementado em
 * Análise") e, com `whitespace-nowrap` sem teto de largura, o retângulo
 * sólido saía da célula da grade e cobria o campo vizinho — a informação de
 * um registro apagando a do outro. Com `max-w-full` a frase longa quebra
 * DENTRO do próprio badge; rótulo curto (a esmagadora maioria: "ativo",
 * "publicado") nunca chega ao limite e segue em uma linha só.
 *
 * `leading-[1.3]` + padding vertical reduzido preservam a altura de antes no
 * caso de uma linha — com `leading-none` as linhas da frase quebrada se
 * encavalariam. */
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
}) {
  return (
    <span
      className={`inline-flex max-w-full items-center break-words rounded px-[0.65em] py-[0.22em] text-left text-xs font-semibold leading-[1.3] ${TOM[tone]}`}
    >
      {children}
    </span>
  );
}
