/* ────────────────────────────────────────────── Ícones da navegação ──────
   O menu lateral são LENTES sobre o território (§19), e cada lente ganha um
   glifo próprio: o gestor volta ao mesmo item pela FORMA, sem reler a lista
   inteira. `.nav-item` já nasceu com `display:flex` e `gap` — o slot existia
   no design system desde a Bancada; faltava o desenho.

   SVG inline, `currentColor` e traço de 1.5 — mesmo padrão de
   `BotaoEspelho`. Nada de biblioteca de ícones: herdar a cor é o que faz o
   item ativo (fundo em gradiente, tinta abyss) e o hover funcionarem sem
   nenhuma regra extra, e a stack não muda (CLAUDE.md §1). */

export type NomeIcone =
  | "painel"
  | "propostas"
  | "favoritas"
  | "oportunidades"
  | "regularidade"
  | "recebidos"
  | "conformidade"
  | "obras"
  | "alertas"
  | "contatos"
  | "copiloto"
  | "assessoria"
  | "class"
  | "conta"
  | "admin";

const GLIFOS: Record<NomeIcone, React.ReactNode> = {
  // Meu painel — os quadrantes do dashboard
  painel: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </>
  ),
  // Propostas — documento com texto
  propostas: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </>
  ),
  // Minhas Propostas — a estrela do favoritar, a mesma da lista
  favoritas: (
    <path d="m12 3.6 2.6 5.3 5.8.85-4.2 4.1 1 5.75-5.2-2.73-5.2 2.73 1-5.75-4.2-4.1 5.8-.85z" />
  ),
  // Oportunidades — o alvo do que está aberto para receber proposta
  oportunidades: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4" />
      <path d="M12 12h.01" />
    </>
  ),
  // Regularidade — escudo com o visto do CAUC
  regularidade: (
    <>
      <path d="M12 3.2 19 6v5.2c0 4.4-2.9 8.2-7 9.6-4.1-1.4-7-5.2-7-9.6V6z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </>
  ),
  // Recursos recebidos — o recurso caindo na bandeja
  recebidos: (
    <>
      <path d="M12 3.5v10.5" />
      <path d="m8 10.5 4 4 4-4" />
      <path d="M5 15.5V18a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2.5" />
    </>
  ),
  // Conformidade fiscal — prancheta conferida
  conformidade: (
    <>
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
      <rect x="9" y="3" width="6" height="4" rx="1.2" />
      <path d="m9.5 13.5 2 2 3.5-3.5" />
    </>
  ),
  // Obras — capacete de execução
  obras: (
    <>
      <path d="M5.5 15.5a6.5 6.5 0 0 1 13 0" />
      <path d="M9.5 15.5V9a2.5 2.5 0 0 1 5 0v6.5" />
      <path d="M3 18.5h18" />
    </>
  ),
  // Alertas — o sino
  alertas: (
    <>
      <path d="M18 15.5V10a6 6 0 1 0-12 0v5.5L4.5 18.5h15z" />
      <path d="M10 21h4" />
    </>
  ),
  // Agenda de contatos — a rede de pessoas
  contatos: (
    <>
      <circle cx="9.5" cy="8" r="3.5" />
      <path d="M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1" />
      <path d="M16.5 4.8a3.5 3.5 0 0 1 0 6.9" />
      <path d="M21 20v-1a4 4 0 0 0-3-3.85" />
    </>
  ),
  // Copiloto — a conversa com o brilho do agente
  copiloto: (
    <>
      <path d="M21 11.5a7.5 7.5 0 0 1-10.9 6.7L4.5 20l1.1-4.3A7.5 7.5 0 1 1 21 11.5z" />
      <path d="m12 8 .85 2.4 2.4.85-2.4.85L12 14.5l-.85-2.4-2.4-.85 2.4-.85z" />
    </>
  ),
  // Assessoria — o headset de quem atende
  assessoria: (
    <>
      <path d="M4.5 14V12a7.5 7.5 0 0 1 15 0v2" />
      <rect x="2.5" y="13.5" width="4" height="6.5" rx="2" />
      <rect x="17.5" y="13.5" width="4" height="6.5" rx="2" />
    </>
  ),
  // Class — o capelo das aulas
  class: (
    <>
      <path d="m12 4 9.5 4.8L12 13.6 2.5 8.8z" />
      <path d="M6.5 11.2V16c0 1.7 2.5 3 5.5 3s5.5-1.3 5.5-3v-4.8" />
    </>
  ),
  // Minha conta — a pessoa logada
  conta: (
    <>
      <circle cx="12" cy="8.5" r="3.8" />
      <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" />
    </>
  ),
  // Administração — os controles da plataforma
  admin: (
    <>
      <path d="M4 7.5h9" />
      <path d="M18.5 7.5H21" />
      <path d="M4 16.5h3" />
      <path d="M12.5 16.5H21" />
      <circle cx="15.75" cy="7.5" r="2.25" />
      <circle cx="9.75" cy="16.5" r="2.25" />
    </>
  ),
};

/**
 * Glifo de 16px que acompanha o rótulo no menu lateral. Decorativo por
 * definição — o rótulo ao lado é quem nomeia o destino —, então fica fora da
 * árvore de acessibilidade (`aria-hidden`) e não vira um segundo anúncio do
 * mesmo link no leitor de tela.
 */
export function IconeNav({
  nome,
  className,
}: {
  nome: NomeIcone;
  className?: string;
}) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ? `nav-icon ${className}` : "nav-icon"}
      aria-hidden
    >
      {GLIFOS[nome]}
    </svg>
  );
}

/* ─────────────────────────────────────────────── Ícones de AÇÃO ──────────
   Os botões de ação carregavam setas de CARACTERE ("←", "↻", "↓") — cada tela
   com um desenho, nenhum alinhado à métrica do texto. O registro abaixo dá a
   cada verbo recorrente do app um glifo único, no mesmo padrão dos da
   navegação (24 de viewBox, traço 1.5, `currentColor`). */

export type NomeAcao =
  | "voltar"
  | "avancar"
  | "varrer"
  | "atualizar"
  | "exportar"
  | "resumo";

const GLIFOS_ACAO: Record<NomeAcao, React.ReactNode> = {
  // Voltar — seta cheia para a esquerda (o retorno de tela)
  voltar: (
    <>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </>
  ),
  // Avançar — o par da volta, para links "ver mais adiante"
  avancar: (
    <>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </>
  ),
  // Varrer — o radar da varredura de alertas
  varrer: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <path d="m12 12 5.6-5.6" />
      <path d="M12 12h.01" />
    </>
  ),
  // Atualizar — consultar as fontes agora (refresh)
  atualizar: (
    <>
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v5h-5" />
    </>
  ),
  // Exportar — baixar o recorte (CSV, PDF)
  exportar: (
    <>
      <path d="M12 4v10.5" />
      <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
      <path d="M4.5 19.5h15" />
    </>
  ),
  // Resumo — as barras do consolidado
  resumo: (
    <>
      <path d="M4 20h16" />
      <path d="M7 16v-5" />
      <path d="M12 16V6" />
      <path d="M17 16v-8" />
    </>
  ),
};

/**
 * Glifo de 16px para dentro de botões e links de ação (`.btn` já tem `gap`).
 * Decorativo (`aria-hidden`) — o rótulo do botão é quem nomeia a ação.
 */
export function IconeAcao({
  nome,
  className,
}: {
  nome: NomeAcao;
  className?: string;
}) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {GLIFOS_ACAO[nome]}
    </svg>
  );
}
