"use client";

/**
 * Oportunidades — chamamentos públicos e programas ABERTOS a proposta.
 *
 * É uma lente sobre o que ainda dá para captar, não uma aba da plataforma de
 * governo (§19): as duas consultas do TransfereGov são o caminho oficial de
 * conferência, e a coleta dentro do Hub entra na Fase 2 do plano de melhorias
 * (`docs/PLANO_MELHORIAS_APP.md`, §2.5) — quando ela chegar, a lista aparece
 * aqui e o link vira "conferir na fonte", sem mudar o lugar no menu.
 *
 * O ANO não é fixo: o documento do cliente pedia 2026, mas um ano cravado no
 * código envelhece em janeiro e leva o gestor a uma consulta vazia. O padrão é
 * o ano corrente.
 */

import { useMemo } from "react";
import { ModuloGate } from "@/components/ModuloGate";

interface Consulta {
  chave: string;
  titulo: string;
  descricao: string;
  url: string;
  /** Filtros a marcar na tela da fonte — a consulta JSF não aceita querystring. */
  filtros: string[];
}

function consultas(ano: number): Consulta[] {
  return [
    {
      chave: "chamamento",
      titulo: "Chamamento público",
      descricao:
        "Editais de chamamento (MROSC) abertos por órgãos federais — a porta para organizações da sociedade civil e para parcerias com o município.",
      url: "https://discricionarias.transferegov.sistema.gov.br/voluntarias/prestacao/mrosc/ChamamentoPublico/chamamentoPublicoConsultaPesquisa.jsf",
      filtros: [`Ano: ${ano}`, "Apto a receber proposta: Sim"],
    },
    {
      chave: "programas",
      titulo: "Programas",
      descricao:
        "Programas de transferência voluntária com janela aberta — é onde a proposta do município entra.",
      url: "https://discricionarias.transferegov.sistema.gov.br/voluntarias/programa/ConsultarPrograma/ConsultarPrograma.do",
      filtros: [
        "Qualificação do proponente: Proposta Voluntária",
        `Ano do programa: ${ano}`,
        "Apto a receber proposta: Sim",
      ],
    },
  ];
}

function Conteudo() {
  const ano = useMemo(() => new Date().getFullYear(), []);
  const lista = useMemo(() => consultas(ano), [ano]);

  return (
    <>
      <header>
        <h1 className="page-title">Oportunidades</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          O que ainda está aberto para receber proposta. Cada consulta abre no
          TransfereGov já no caminho certo — marque os filtros indicados para ver
          só o que está apto neste ano.
        </p>
      </header>

      <section className="stagger grid gap-5 md:grid-cols-2">
        {lista.map((c) => (
          <div key={c.chave} className="card flex flex-col gap-4 p-6">
            <div>
              <h2 className="tracking-tight">{c.titulo}</h2>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
                {c.descricao}
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <p className="label-mono">Filtros a aplicar</p>
              <ul className="flex flex-wrap gap-1.5">
                {c.filtros.map((f) => (
                  <li
                    key={f}
                    className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 text-xs text-ink-2"
                  >
                    <span className="brand-dot" aria-hidden />
                    {f}
                  </li>
                ))}
              </ul>
            </div>

            <a
              href={c.url}
              target="_blank"
              rel="noreferrer"
              className="btn btn-primary mt-auto self-start"
            >
              Abrir consulta ↗
            </a>
          </div>
        ))}
      </section>

      <p className="text-[12px] text-ink-3">
        Por enquanto a consulta acontece no portal oficial. A coleta dentro do
        Hub — com os mesmos filtros, recortada pelo seu território e com ★ para
        acompanhar — está no plano de melhorias.
      </p>
    </>
  );
}

export default function OportunidadesPage() {
  return (
    <ModuloGate modulo="oportunidades" titulo="Oportunidades">
      <Conteudo />
    </ModuloGate>
  );
}
