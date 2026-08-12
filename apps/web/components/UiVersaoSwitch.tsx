"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

/** Versões de UI oferecidas — o backend sanitiza qualquer valor fora daqui. */
const VERSOES = [
  {
    id: "v2",
    titulo: "Bancada v2",
    resumo: "Acento duplo (lime + aqua), vidro e elevação, microanimações, aurora e grade no canvas.",
  },
  {
    id: "v1",
    titulo: "Clássica v1",
    resumo: "Acento único lime, superfícies chapadas, peso tipográfico único e canvas limpo.",
  },
] as const;

/**
 * Troca a versão da UI da plataforma com UM clique (chave `ui_versao`).
 *
 * Substitui o campo de texto genérico do catálogo: escrever "v1" à mão não é
 * interface. A escolha é aplicada NA HORA no próprio `<html>` do admin — sem
 * isso a mudança só apareceria na carga seguinte e pareceria não ter surtido
 * efeito. O `localStorage` acompanha para o boot script do layout raiz manter
 * a versão já na primeira pintura das próximas páginas.
 */
export function UiVersaoSwitch({
  valorAtual,
  onSalvo,
}: {
  valorAtual: string | null | undefined;
  onSalvo?: () => void;
}) {
  const efetiva = valorAtual === "v1" ? "v1" : "v2";
  const [salvando, setSalvando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // mantém o admin coerente com o que está gravado (inclusive ao recarregar)
  useEffect(() => {
    aplicarNoDocumento(efetiva);
  }, [efetiva]);

  function aplicarNoDocumento(versao: string) {
    if (versao === "v1") document.documentElement.setAttribute("data-ui", "v1");
    else document.documentElement.removeAttribute("data-ui");
    try {
      localStorage.setItem("hub_ui", versao);
    } catch {
      /* modo privativo — a próxima carga consulta a API de qualquer forma */
    }
  }

  async function escolher(versao: string) {
    if (versao === efetiva || salvando) return;
    setErro(null);
    setSalvando(versao);
    const { error } = await api.PUT("/api/v1/admin/config", {
      body: { chave: "ui_versao", valor: versao },
    });
    setSalvando(null);
    if (error) {
      setErro("Falha ao salvar (é necessário ser administrador).");
      return;
    }
    aplicarNoDocumento(versao);
    onSalvo?.();
  }

  return (
    <div className="card p-5">
      <h3 className="text-sm tracking-tight">Versão da interface</h3>
      <p className="mt-1 max-w-xl text-xs leading-relaxed text-ink-3">
        Vale para todo mundo e passa a valer na próxima carga de cada página —
        sem redeploy. As duas versões usam as mesmas telas; muda o acabamento
        visual.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {VERSOES.map((v) => {
          const ativa = efetiva === v.id;
          return (
            <button
              key={v.id}
              onClick={() => escolher(v.id)}
              disabled={!!salvando}
              aria-pressed={ativa}
              className={`card card-hover flex flex-col items-start gap-1 p-4 text-left ${
                ativa ? "border-lime" : ""
              }`}
            >
              <span className="flex w-full items-center gap-2">
                {/* marcador de rádio — o estado tem que ser legível sem cor */}
                <span
                  aria-hidden
                  className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                    ativa ? "border-lime" : "border-hairline"
                  }`}
                >
                  {ativa && (
                    <span className="h-2 w-2 rounded-full bg-lime" />
                  )}
                </span>
                <span className="flex-1 text-sm tracking-tight">{v.titulo}</span>
                <span className="label-mono">
                  {salvando === v.id ? "salvando…" : ativa ? "em uso" : v.id}
                </span>
              </span>
              <span className="text-xs leading-relaxed text-ink-3">
                {v.resumo}
              </span>
            </button>
          );
        })}
      </div>

      {erro && <p className="mt-3 text-xs text-warn">{erro}</p>}
    </div>
  );
}
