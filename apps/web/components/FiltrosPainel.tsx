"use client";

/**
 * Barra de filtros do painel — o recorte GLOBAL de leitura, agora no
 * conteúdo e não mais no trilho lateral.
 *
 * Os dois recortes globais (§33 território e §33b origem do recurso) moravam
 * dentro do menu, espremidos numa coluna de 272px: o multi-select do município
 * abria um popover dentro de uma barra que rola, a origem virava chips
 * minúsculos e nada daquilo parecia um filtro para quem usa qualquer outro
 * sistema. Aqui os dois viram SELETORES no topo da tela — rótulo, valor
 * escolhido, menu com caixas de seleção — e o que está aplicado aparece em
 * chips removíveis ao lado, com "limpar tudo".
 *
 * O que a barra NÃO faz é ampliar visibilidade: continua sendo recorte de
 * leitura sobre o território do perfil (o RLS segue sendo o limite).
 *
 * A barra só se desenha nas telas em que os recortes MUDAM alguma coisa
 * (`FILTROS_DA_ROTA`): filtro que não altera a tela lê como controle quebrado.
 */

import Link from "next/link";
import { useState } from "react";
import { ChipFiltro, ItemMenu, Seletor } from "@/components/kit";
import { useOrigem } from "@/lib/origem";
import { useSafra } from "@/lib/safra";
import { rotuloMunicipio, useTerritorio } from "@/lib/territorio";

/** A partir daqui o menu de municípios ganha campo de busca. */
const COM_BUSCA = 8;

/** Quais recortes globais valem em cada tela do painel.
 *  Conformidade e obras ficam de fora da ORIGEM de propósito: as fontes
 *  delas (Siconfi, SISMOB/SIMEC/CAIXA) não estão no catálogo do gestor, e
 *  aplicar o filtro ali zeraria a tela sempre — o que é mentira, não filtro.
 *  A SAFRA hoje só vale no Meu painel: nas telas de exploração o ano é uma
 *  faceta local, com o universo daquela consulta. */
const FILTROS_DA_ROTA: {
  rota: RegExp;
  municipio: boolean;
  origem: boolean;
  safra?: boolean;
}[] = [
  { rota: /^\/panel$/, municipio: true, origem: true, safra: true },
  { rota: /^\/panel\/funding\/summary$/, municipio: true, origem: true },
  { rota: /^\/panel\/funding$/, municipio: true, origem: true },
  { rota: /^\/panel\/transfers(\/amendments)?$/, municipio: true, origem: true },
  {
    rota: /^\/panel\/(my-proposals|opportunities|regularity|compliance|works|alerts|advisory)$/,
    municipio: true,
    origem: false,
  },
];

export function filtrosDaRota(pathname: string) {
  return (
    FILTROS_DA_ROTA.find((r) => r.rota.test(pathname)) ?? {
      municipio: false,
      origem: false,
      safra: false,
    }
  );
}

export function FiltrosPainel({ pathname }: { pathname: string }) {
  const regra = filtrosDaRota(pathname);
  const { municipios } = useTerritorio();
  const { origens } = useOrigem();
  const { opcoes: safras } = useSafra();

  // Recorte com uma opção só não recorta nada: cada seletor some sozinho, e
  // a barra inteira sai da tela quando não sobra nenhum.
  const mostraMunicipio = regra.municipio && municipios.length > 1;
  const mostraOrigem = regra.origem && origens.length > 1;
  const mostraSafra = Boolean(regra.safra) && safras.length > 1;
  if (!mostraMunicipio && !mostraOrigem && !mostraSafra) return null;

  return (
    <div className="toolbar mb-5">
      <span className="toolbar-label">Recorte</span>
      {mostraMunicipio && <SeletorMunicipio />}
      {mostraOrigem && <SeletorOrigem />}
      {/* A safra fecha a linha dos recortes globais — ela morava sozinha no
          canto do cabeçalho da página, longe dos irmãos de mesmo alcance. */}
      {mostraSafra && <SeletorSafra />}
      <ChipsAplicados
        municipio={mostraMunicipio}
        origem={mostraOrigem}
        safra={mostraSafra}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────── Município ────── */

function SeletorMunicipio() {
  const { perfil, municipios, selecionados, ativos, alternar, apenas, todos } =
    useTerritorio();
  const [busca, setBusca] = useState("");

  const tudo = selecionados.length === 0;
  const [unico] = ativos;
  const valor = tudo
    ? `Todos (${municipios.length})`
    : ativos.length === 1 && unico
      ? rotuloMunicipio(unico)
      : `${ativos.length} de ${municipios.length}`;

  const lista = busca.trim()
    ? municipios.filter((m) =>
        rotuloMunicipio(m).toLowerCase().includes(busca.trim().toLowerCase()),
      )
    : municipios;

  return (
    <Seletor
      rotulo="Município"
      valor={valor}
      ativo={!tudo}
      largura="17rem"
      titulo="Quais municípios do seu território entram no painel agora"
    >
      {(fechar) => (
        <>
          {municipios.length >= COM_BUSCA && (
            <div className="menu-head">
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Filtrar município…"
                className="input w-full text-sm"
                autoFocus
              />
            </div>
          )}

          <ItemMenu
            marcado={tudo}
            radio
            rotulo="Todos os municípios"
            contagem={municipios.length}
            onClick={() => {
              todos();
              fechar();
            }}
            title="Painel inteiro, sem recorte de território"
          />
          <div className="menu-sep" />

          <div className="menu-scroll" role="listbox" aria-label="Municípios do painel">
            {lista.map((m) => (
              <ItemMenu
                key={m.ibge}
                marcado={!tudo && selecionados.includes(m.ibge)}
                rotulo={rotuloMunicipio(m)}
                onClick={() => alternar(m.ibge)}
                acessorio={
                  // atalho do caso mais comum: olhar UM município de uma vez
                  <button
                    type="button"
                    onClick={() => {
                      apenas(m.ibge);
                      fechar();
                    }}
                    title={`Ver só ${rotuloMunicipio(m)}`}
                    className="shrink-0 rounded px-1.5 py-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 opacity-0 transition hover:text-ink group-hover:opacity-100 focus:opacity-100"
                  >
                    só este
                  </button>
                }
              />
            ))}
            {lista.length === 0 && (
              <p className="px-2 py-2 text-sm text-ink-3">
                Nenhum município com esse nome.
              </p>
            )}
          </div>

          <div className="menu-foot">
            {(perfil?.areas ?? []).length > 0 && (
              <span className="min-w-0 truncate" title={perfil!.areas.join(", ")}>
                Áreas: {perfil!.areas.join(", ")}
              </span>
            )}
            {/* Conta demo: o território é semeado pela plataforma e o backend
                bloqueia o onboarding — sem o link, sem beco sem saída. */}
            {!perfil?.demo && (
              <Link href="/onboarding" className="link-soft ml-auto shrink-0">
                Ajustar perfil →
              </Link>
            )}
          </div>
        </>
      )}
    </Seletor>
  );
}

/* ────────────────────────────────────────────────────────── Origem ────── */

function SeletorOrigem() {
  const { origens, selecionadas, alternar, todas } = useOrigem();
  const tudo = selecionadas.length === 0;
  const valor = tudo
    ? `Todas (${origens.length})`
    : selecionadas.length === 1
      ? rotuloCurto(
          origens.find((o) => o.chave === selecionadas[0])?.label ??
            selecionadas[0]!,
        )
      : `${selecionadas.length} de ${origens.length}`;

  return (
    <Seletor
      rotulo="Origem do recurso"
      valor={valor}
      ativo={!tudo}
      largura="17rem"
      titulo="De qual fonte veio o registro"
    >
      {(fechar) => (
        <>
          <ItemMenu
            marcado={tudo}
            radio
            rotulo="Todas as origens"
            contagem={origens.length}
            onClick={() => {
              todas();
              fechar();
            }}
          />
          <div className="menu-sep" />
          <div role="listbox" aria-label="Origem do recurso">
            {origens.map((o) => (
              <ItemMenu
                key={o.chave}
                marcado={selecionadas.includes(o.chave)}
                rotulo={o.label}
                onClick={() => alternar(o.chave)}
              />
            ))}
          </div>
        </>
      )}
    </Seletor>
  );
}

/* ─────────────────────────────────────────────────────────── Safra ────── */

function SeletorSafra() {
  const { anos, opcoes, alternar, todos } = useSafra();
  const tudo = anos.length === 0;
  const valor = tudo
    ? "Todos os anos"
    : anos.length === 1
      ? anos[0]!
      : `${anos.length} safras`;

  return (
    <Seletor
      rotulo="Safra"
      valor={valor}
      ativo={!tudo}
      largura="14rem"
      titulo="Ano das propostas e dos repasses que entram no painel"
    >
      {(fechar) => (
        <>
          <ItemMenu
            marcado={tudo}
            radio
            rotulo="Todos os anos"
            onClick={() => {
              todos();
              fechar();
            }}
            title="Painel inteiro, sem recorte de safra"
          />
          <div className="menu-sep" />
          <div className="menu-scroll" role="listbox" aria-label="Safras do território">
            {opcoes.map((o) => (
              <ItemMenu
                key={o.ano}
                marcado={anos.includes(o.ano)}
                rotulo={o.ano}
                contagem={o.total}
                onClick={() => alternar(o.ano)}
                title={`Liga/desliga a safra ${o.ano} no recorte`}
              />
            ))}
          </div>
        </>
      )}
    </Seletor>
  );
}

/* ─────────────────────────────────────────────────── Chips aplicados ──── */

function ChipsAplicados({
  municipio,
  origem,
  safra,
}: {
  municipio: boolean;
  origem: boolean;
  safra: boolean;
}) {
  const { ativos, selecionados, alternar, todos } = useTerritorio();
  const {
    origens,
    selecionadas,
    alternar: alternarOrigem,
    todas,
  } = useOrigem();
  const {
    anos,
    alternar: alternarSafra,
    todos: todasSafras,
  } = useSafra();

  const chipsMunicipio = municipio && selecionados.length > 0 ? ativos : [];
  const chipsOrigem = origem
    ? origens.filter((o) => selecionadas.includes(o.chave))
    : [];
  const chipsSafra = safra ? anos : [];
  if (
    chipsMunicipio.length === 0 &&
    chipsOrigem.length === 0 &&
    chipsSafra.length === 0
  )
    return null;

  return (
    <>
      <span className="toolbar-sep" aria-hidden />
      {chipsMunicipio.map((m) => (
        <ChipFiltro
          key={m.ibge}
          onRemover={() => alternar(m.ibge)}
          title={`Tirar ${rotuloMunicipio(m)} do recorte`}
        >
          {rotuloMunicipio(m)}
        </ChipFiltro>
      ))}
      {chipsOrigem.map((o) => (
        <ChipFiltro
          key={o.chave}
          onRemover={() => alternarOrigem(o.chave)}
          title={`Tirar ${o.label} do recorte`}
        >
          {rotuloCurto(o.label)}
        </ChipFiltro>
      ))}
      {chipsSafra.map((ano) => (
        <ChipFiltro
          key={ano}
          onRemover={() => alternarSafra(ano)}
          title={`Tirar a safra ${ano} do recorte`}
        >
          {ano}
        </ChipFiltro>
      ))}
      <button
        type="button"
        onClick={() => {
          todos();
          todas();
          todasSafras();
        }}
        className="link-soft ml-1 text-[12px]"
      >
        Limpar recorte
      </button>
    </>
  );
}

/** "FNS — Fundo Nacional de Saúde" → "FNS" (o travessão separa nome e glosa). */
function rotuloCurto(label: string): string {
  const [nome] = label.split("—");
  return nome?.trim() || label;
}
