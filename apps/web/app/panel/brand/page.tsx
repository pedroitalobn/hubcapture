"use client";

import { useEffect, useState } from "react";
import type { components } from "@hub/api-client";
import { EditorMarca } from "@/components/marca/EditorMarca";
import { api } from "@/lib/api/client";

type Marca = components["schemas"]["MarcaRead"];

/** Minha marca (white label, §69) — o dono ajusta visual, endereço e equipe. */
export default function MinhaMarcaPage() {
  const [marcas, setMarcas] = useState<Marca[] | null>(null);
  const [atual, setAtual] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const { data } = await api.GET("/api/v1/brands/mine");
      const lista = data ?? [];
      setMarcas(lista);
      setAtual(lista[0]?.id ?? null);
    })();
  }, []);

  if (marcas === null) return <p className="text-sm text-ink-3">Carregando…</p>;
  if (!atual) {
    return (
      <div className="card max-w-xl p-6 text-sm text-ink-2">
        Nenhuma marca está no seu nome. A marca própria (white label) é criada pela
        administração da plataforma — fale com o suporte para ativar.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {marcas.length > 1 && (
        <div className="segmented flex-wrap self-start" role="tablist" aria-label="Marcas">
          {marcas.map((m) => (
            <button
              key={m.id}
              type="button"
              role="tab"
              aria-selected={m.id === atual}
              className={`segmented-item ${m.id === atual ? "segmented-item-active" : ""}`}
              onClick={() => setAtual(m.id)}
            >
              {m.nome}
            </button>
          ))}
        </div>
      )}
      <EditorMarca key={atual} marcaId={atual} />
    </div>
  );
}
