"use client";

/**
 * Adicionar município ao território — a MESMA peça em Minha conta e no seletor
 * de Município do Meu painel.
 *
 * Busca por nome (malha municipal interna da API, tolerante a erro de
 * digitação) ou por código IBGE de 7 dígitos + Enter. A regra do plano (limite
 * de municípios e a feature `municipios_adicionar`) vem pronta do `/profile`
 * (`territorio`): sem permissão, a peça explica o porquê em vez de oferecer um
 * campo que só devolveria 403.
 */

import { useEffect, useState } from "react";
import { adicionarMunicipios, api } from "@/lib/api/client";
import { type Perfil, rotuloMunicipio } from "@/lib/territorio";

interface MunicipioSugerido {
  ibge: string;
  nome: string;
  uf?: string | null;
}

export type EdicaoTerritorio = NonNullable<Perfil["territorio"]>;

/** Frase para quando o plano não deixa adicionar (null = pode, ou nada a dizer). */
export function motivoSemAdicao(edicao: EdicaoTerritorio | undefined): string | null {
  if (!edicao || edicao.pode_adicionar) return null;
  if (edicao.motivo === "limite_atingido") {
    return `Você já acompanha o máximo de ${edicao.maximo} município(s) do seu plano. Remova um em Minha conta ou fale com a administração para mudar de plano.`;
  }
  if (edicao.motivo === "plano_nao_permite") {
    return "Seu plano não inclui adicionar municípios pelo painel — fale com a administração para mudar de plano.";
  }
  return null;
}

export function AdicionarMunicipio({
  edicao,
  jaNoTerritorio,
  aoAdicionar,
  compacto = false,
  autoFocus = false,
}: {
  edicao: EdicaoTerritorio | undefined;
  jaNoTerritorio: string[];
  /** Depois de gravar: recarregar o território e avisar. Recebe os rótulos. */
  aoAdicionar: (nomes: string[]) => Promise<void> | void;
  /** Versão de menu suspenso (seletor do Meu painel): sem rótulo de campo. */
  compacto?: boolean;
  autoFocus?: boolean;
}) {
  const [busca, setBusca] = useState("");
  const [sugestoes, setSugestoes] = useState<MunicipioSugerido[]>([]);
  const [semResultado, setSemResultado] = useState(false);
  const [enviando, setEnviando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setSemResultado(false);
    const termo = busca.trim();
    if (termo.length < 2) {
      setSugestoes([]);
      return;
    }
    let vivo = true;
    const t = setTimeout(async () => {
      const { data } = await api.GET("/api/v1/municipalities", {
        params: { query: { q: termo } },
      });
      if (!vivo) return; // resposta de uma tecla antiga
      const lista = ((data ?? []) as MunicipioSugerido[]).slice(0, compacto ? 6 : 8);
      setSugestoes(lista);
      setSemResultado(lista.length === 0);
    }, 300);
    return () => {
      vivo = false;
      clearTimeout(t);
    };
  }, [busca, compacto]);

  async function adicionar(m: MunicipioSugerido) {
    setErro(null);
    setEnviando(m.ibge);
    try {
      const r = await adicionarMunicipios([
        { ibge: m.ibge, nome: m.nome.startsWith("IBGE ") ? null : m.nome, uf: m.uf ?? null },
      ]);
      setBusca("");
      setSugestoes([]);
      await aoAdicionar(r.adicionados.map((a) => rotuloMunicipio(a)));
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível adicionar agora.");
    } finally {
      setEnviando(null);
    }
  }

  function adicionarPorCodigo() {
    const codigo = busca.trim();
    if (/^\d{7}$/.test(codigo)) {
      const sugerido = sugestoes.find((s) => s.ibge === codigo);
      void adicionar(sugerido ?? { ibge: codigo, nome: `IBGE ${codigo}` });
    }
  }

  const bloqueio = motivoSemAdicao(edicao);
  if (edicao && !edicao.pode_adicionar) {
    return bloqueio ? (
      <p
        className={
          compacto
            ? "px-2 py-2 text-[13px] leading-relaxed text-ink-2"
            : "rounded-lg border border-hairline p-3 text-[13px] text-ink-2"
        }
      >
        {bloqueio}
      </p>
    ) : null;
  }

  const campo = (
    <input
      value={busca}
      onChange={(e) => setBusca(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          adicionarPorCodigo();
        }
      }}
      placeholder="Nome do município ou código IBGE…"
      aria-label="Buscar município para adicionar"
      className={compacto ? "input w-full text-sm" : "input"}
      disabled={enviando != null}
      autoFocus={autoFocus}
    />
  );

  return (
    <div className={compacto ? "flex flex-col gap-2" : "flex flex-col gap-2 border-t border-hairline pt-4"}>
      {compacto ? (
        campo
      ) : (
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Adicionar município</span>
          {campo}
        </label>
      )}
      {edicao?.restantes != null && (
        <p className="text-[12px] text-ink-3">
          Cabem mais {edicao.restantes} município(s) no seu plano.
        </p>
      )}
      {semResultado && (
        <p className="text-[12px] text-ink-3">
          Nenhum município encontrado com esse nome. Confira a grafia ou digite
          o código IBGE (7 dígitos) e tecle Enter.
        </p>
      )}
      {sugestoes.length > 0 && (
        <ul className="flex flex-col divide-y divide-hairline rounded-lg border border-hairline">
          {sugestoes.map((s) => {
            const jaTem = jaNoTerritorio.includes(s.ibge);
            return (
              <li
                key={s.ibge}
                className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  {s.nome}
                  {s.uf ? `/${s.uf}` : ""}
                  {!compacto && (
                    <span className="ml-2 font-mono text-[11px] text-ink-3">{s.ibge}</span>
                  )}
                </span>
                {jaTem ? (
                  <span className="shrink-0 text-[12px] text-ink-3">já acompanha</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => void adicionar(s)}
                    disabled={enviando != null}
                    className="btn btn-primary btn-sm shrink-0"
                  >
                    {enviando === s.ibge ? "Adicionando…" : "Adicionar"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {erro && <p className="text-sm text-danger">{erro}</p>}
    </div>
  );
}
