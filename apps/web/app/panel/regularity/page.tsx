"use client";

/**
 * Regularidade — a situação do ente nos requisitos fiscais (CAUC, Tesouro).
 *
 * Sem regularidade não se assina convênio: é a trava que derruba proposta já
 * aprovada. Por isso vira lente própria no menu, e não um detalhe dentro da
 * conformidade fiscal completa (módulo `conformidade`, que segue desligado até
 * o Siconfi estar calibrado — §2.7 do plano de melhorias).
 *
 * Fase 1 leva ao extrato oficial por ente, com o território do usuário à mão
 * para ele saber qual município consultar. A leitura do extrato dentro do Hub
 * entra na Fase 2.
 */

import Link from "next/link";
import { ModuloGate } from "@/components/ModuloGate";
import { useTerritorio } from "@/lib/territorio";

const CAUC_URL = "https://cauc.tesouro.gov.br/ng/#/extrato/ente/filtro";

function Conteudo() {
  const { municipios, selecionados } = useTerritorio();
  // o recorte ativo do trilho lateral manda; sem recorte, todo o território
  const emFoco =
    selecionados.length > 0
      ? municipios.filter((m) => selecionados.includes(m.ibge))
      : municipios;

  return (
    <>
      <header>
        <h1 className="page-title">Regularidade</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Requisitos fiscais do ente no CAUC — é o que o concedente confere
          antes de celebrar. Uma pendência aqui trava a transferência mesmo com
          a proposta aprovada.
        </p>
      </header>

      <section className="card flex flex-col gap-5 p-6">
        <div>
          <h2 className="tracking-tight">Extrato CAUC do ente</h2>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-2">
            Consulte pelo nome ou CNPJ do município. O extrato lista item a item
            o que está em dia e o que está pendente, com a data de verificação.
          </p>
        </div>

        {emFoco.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="label-mono">Seu território</p>
            <ul className="flex flex-wrap gap-1.5">
              {emFoco.map((m) => (
                <li
                  key={m.ibge}
                  className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 text-xs text-ink-2"
                >
                  <span className="brand-dot" aria-hidden />
                  {m.nome ?? m.ibge}
                  {m.uf ? `/${m.uf}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}

        <a
          href={CAUC_URL}
          target="_blank"
          rel="noreferrer"
          className="btn btn-primary self-start"
        >
          Abrir extrato no CAUC ↗
        </a>
      </section>

      <p className="text-[12px] text-ink-3">
        A leitura automática do extrato dentro do Hub — com alerta quando um
        requisito vence — está no plano de melhorias. Enquanto isso, a consulta
        oficial é a fonte. Veja também{" "}
        <Link href="/panel/alerts" className="underline underline-offset-2">
          seus alertas
        </Link>
        .
      </p>
    </>
  );
}

export default function RegularidadePage() {
  return (
    <ModuloGate modulo="regularidade" titulo="Regularidade">
      <Conteudo />
    </ModuloGate>
  );
}
