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

/** Badge de status: preenchimento semântico + rótulo em caixa de frase. */
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
}) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded px-[0.65em] py-[0.35em] text-xs font-semibold leading-none ${TOM[tone]}`}
    >
      {children}
    </span>
  );
}
