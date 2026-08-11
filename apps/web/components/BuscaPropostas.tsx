"use client";

/**
 * Busca de propostas do Meu painel — número/código, natureza jurídica e faixa
 * de valor, sobre o cache do território (RLS). Não é a Captação: aqui não há
 * consulta ao vivo às fontes, abas, curadoria nem relatório — é o atalho de
 * "achar aquela proposta" sem sair da tela inicial.
 *
 * O recorte de município é o do trilho lateral (`useTerritorio`), o mesmo que
 * recorta o resto do painel; com mais de um município no perfil, as pílulas
 * abaixo mexem NESSE recorte (mesma store, não uma cópia).
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { formatBRL, municipioPrincipal, municipioSecundario } from "@/lib/format";
import { paramMunicipio, rotuloMunicipio, useTerritorio } from "@/lib/territorio";

interface Proposta {
  id: string;
  id_externo: string;
  numero_proposta?: string | null;
  titulo?: string | null;
  orgao_superior?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
}

// Mesmos slugs do classificador do backend (`classificar_natureza_juridica`)
// e da tela de Captação — um só vocabulário de natureza jurídica no produto.
const NATUREZAS: [string, string][] = [
  ["", "Todas"],
  ["municipal", "Adm. Pública Municipal"],
  ["estadual_df", "Adm. Pública Estadual/DF"],
  ["consorcio", "Consórcio Público"],
  ["empresa_publica", "Empresa pública / economia mista"],
  ["osc", "Organização da Sociedade Civil"],
];

const LIMITE = 8;

export function BuscaPropostas() {
  const { perfil, municipios, selecionados, alternar, todos } = useTerritorio();

  const [q, setQ] = useState("");
  const [naturezaJuridica, setNaturezaJuridica] = useState("");
  const [valorMin, setValorMin] = useState("");
  const [valorMax, setValorMax] = useState("");

  const [itens, setItens] = useState<Proposta[]>([]);
  const [total, setTotal] = useState(0);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // a busca por texto é debounced: não dispara request a cada tecla
  const [qDebounced, setQDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const temFiltro =
    qDebounced.trim() !== "" ||
    naturezaJuridica !== "" ||
    valorMin !== "" ||
    valorMax !== "";

  const rangeInvalido =
    valorMin !== "" && valorMax !== "" && Number(valorMin) > Number(valorMax);

  // descarta resposta antiga que chegue depois de uma mais nova
  const seqRef = useRef(0);

  const buscar = useCallback(async () => {
    if (!temFiltro || rangeInvalido) {
      setItens([]);
      setTotal(0);
      return;
    }
    const seq = ++seqRef.current;
    setBuscando(true);
    const { data, error } = await api.GET("/api/v1/proposals", {
      params: {
        query: {
          municipio: paramMunicipio(selecionados),
          q: qDebounced.trim() || undefined,
          natureza_juridica: naturezaJuridica || undefined,
          valor_min: valorMin || undefined,
          valor_max: valorMax || undefined,
          limite: LIMITE,
        } as never,
      },
    });
    if (seq !== seqRef.current) return; // resposta obsoleta
    if (error) {
      setErro("Não foi possível buscar agora. Tente de novo.");
    } else {
      setErro(null);
      const pagina = data as { itens?: Proposta[]; total?: number } | undefined;
      setItens(pagina?.itens ?? []);
      setTotal(pagina?.total ?? 0);
    }
    setBuscando(false);
  }, [
    temFiltro,
    rangeInvalido,
    selecionados,
    qDebounced,
    naturezaJuridica,
    valorMin,
    valorMax,
  ]);

  useEffect(() => {
    void buscar();
  }, [buscar]);

  function limpar() {
    setQ("");
    setNaturezaJuridica("");
    setValorMin("");
    setValorMax("");
  }

  // Captação desligada (plataforma ou plano): a listagem de propostas responde
  // 403/404 — sem módulo, o painel simplesmente não mostra a busca.
  if (!(perfil?.modulos ?? []).includes("captacao")) return null;

  return (
    <section className="anim-fade-up flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="tracking-tight">Buscar propostas</h2>
        <Link href="/panel/funding" className="btn btn-ghost btn-sm">
          Ver na Captação →
        </Link>
      </div>

      <div className="card flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1">
            <span className="field-label">Número da proposta</span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="nº da proposta, código, emenda, programa ou órgão"
              className="input w-full"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">Valor mín (R$)</span>
            <input
              type="number"
              min={0}
              value={valorMin}
              onChange={(e) => setValorMin(e.target.value)}
              className="input w-32"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">Valor máx (R$)</span>
            <input
              type="number"
              min={0}
              value={valorMax}
              onChange={(e) => setValorMax(e.target.value)}
              className="input w-32"
            />
          </label>
          {temFiltro && (
            <button onClick={limpar} className="btn btn-ghost btn-sm mb-1">
              Limpar filtros
            </button>
          )}
        </div>

        {rangeInvalido && (
          <p className="text-sm text-danger">
            O valor mínimo está maior que o máximo.
          </p>
        )}

        {/* município: mexe no MESMO recorte do trilho lateral */}
        {municipios.length > 1 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="field-label mr-1">Município</span>
            <Pilula ativo={selecionados.length === 0} onClick={todos}>
              Todos
            </Pilula>
            {municipios.map((m) => (
              <Pilula
                key={m.ibge}
                ativo={selecionados.includes(m.ibge)}
                onClick={() => alternar(m.ibge)}
              >
                {rotuloMunicipio(m)}
              </Pilula>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="field-label mr-1">Natureza jurídica</span>
          {NATUREZAS.map(([valor, rotulo]) => (
            <Pilula
              key={rotulo}
              ativo={naturezaJuridica === valor}
              onClick={() => setNaturezaJuridica(valor)}
            >
              {rotulo}
            </Pilula>
          ))}
        </div>
      </div>

      {erro && <p className="text-sm text-danger">{erro}</p>}

      {!temFiltro ? (
        <p className="text-sm text-ink-2">
          Digite um número ou escolha um filtro para buscar no seu território.
        </p>
      ) : buscando && itens.length === 0 ? (
        <p className="text-sm text-ink-2">Buscando…</p>
      ) : itens.length === 0 ? (
        <p className="text-sm text-ink-2">
          Nenhuma proposta com esses filtros no território selecionado.
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {itens.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/panel/funding/${p.id}`}
                  className="card card-hover flex flex-wrap items-center justify-between gap-3 p-4"
                >
                  <div className="min-w-0">
                    <p className="label-mono text-ink-3">
                      {p.numero_proposta ?? p.id_externo}
                    </p>
                    <p className="truncate">{p.titulo ?? "(sem título)"}</p>
                    <p className="text-sm text-ink-2">
                      {municipioPrincipal(p)}
                      {municipioSecundario(p) ? ` · ${municipioSecundario(p)}` : ""}
                      {p.situacao ? ` · ${p.situacao}` : ""}
                    </p>
                  </div>
                  <span className="tabular-nums">{formatBRL(p.valor_total)}</span>
                </Link>
              </li>
            ))}
          </ul>
          {total > itens.length && (
            <p className="text-sm text-ink-2">
              Mostrando {itens.length} de {total}.{" "}
              <Link href="/panel/funding" className="underline">
                Ver todas na Captação
              </Link>
              .
            </p>
          )}
        </>
      )}
    </section>
  );
}

function Pilula({
  ativo,
  onClick,
  children,
}: {
  ativo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm ${
        ativo
          ? "border-ink bg-ink text-surface"
          : "border-hairline text-ink-2 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}
