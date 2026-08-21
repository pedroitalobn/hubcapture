import Link from "next/link";
import { IconeAcao } from "./icons";

/**
 * Retorno de tela padronizado. O "← Voltar" vivia espalhado — ghost pequeno no
 * canto DIREITO do cabeçalho numa tela, link mono de 11px noutra — e o gestor
 * não o encontrava. A regra que fica: o retorno é SEMPRE a primeira coisa da
 * página, à ESQUERDA, acima do título (posição convencional de breadcrumb),
 * com a mesma pílula em toda superfície (`.back-link` em globals.css).
 */
export function BotaoVoltar({
  href,
  rotulo,
  className,
}: {
  href: string;
  rotulo: string;
  className?: string;
}) {
  return (
    <Link href={href} className={className ? `back-link ${className}` : "back-link"}>
      <IconeAcao nome="voltar" className="back-link-seta" />
      <span>{rotulo}</span>
    </Link>
  );
}
