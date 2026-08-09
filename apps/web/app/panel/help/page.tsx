"use client";

/**
 * Central de ajuda — a porta "navegável" do help desk interno.
 *
 * As outras duas portas para o MESMO artigo são o link compartilhável
 * (/panel/help/<slug>) e o hint contextual (ⓘ ao lado do elemento na tela).
 * Aqui o gestor busca por termo ("empenho") ou navega por categoria.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { cx } from "@/components/ui";

interface Categoria {
  id: string;
  nome: string;
  slug: string;
  descricao?: string | null;
  artigos: number;
}

interface Artigo {
  id: string;
  titulo: string;
  slug: string;
  resumo?: string | null;
  categoria?: { nome: string; slug: string } | null;
  videos: number;
  documentos: number;
}

export default function CentralAjudaPage() {
  const [categorias, setCategorias] = useState<Categoria[] | null>(null);
  const [artigos, setArtigos] = useState<Artigo[] | null>(null);
  const [busca, setBusca] = useState("");
  const [categoria, setCategoria] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const { data } = await api.GET("/api/v1/help/categories");
      setCategorias((data as Categoria[]) ?? []);
    })();
  }, []);

  const carregar = useCallback(async (q: string, cat: string | null) => {
    const { data } = await api.GET("/api/v1/help/articles", {
      params: { query: { q: q || undefined, categoria: cat ?? undefined } },
    });
    setArtigos((data as Artigo[]) ?? []);
  }, []);

  // busca com debounce — mesma mecânica da captação
  useEffect(() => {
    const t = setTimeout(() => void carregar(busca, categoria), 350);
    return () => clearTimeout(t);
  }, [busca, categoria, carregar]);

  const comArtigos = (categorias ?? []).filter((c) => c.artigos > 0);

  return (
    <>
      <header>
        <h1 className="page-title">Central de ajuda</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          O que significam os termos, dados e etapas das suas propostas —
          artigos, vídeos e materiais preparados pela equipe. Onde você vir o
          ícone <span className="font-mono text-xs">?</span> no painel, há um
          destes conteúdos explicando o dado ao lado.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar (ex.: empenho, contrapartida, CAUC…)"
          className="input w-full max-w-md"
        />
        {comArtigos.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => setCategoria(null)}
              className={cx("chip", categoria === null && "chip-active")}
            >
              Todas
            </button>
            {comArtigos.map((c) => (
              <button
                key={c.slug}
                onClick={() => setCategoria(categoria === c.slug ? null : c.slug)}
                className={cx("chip", categoria === c.slug && "chip-active")}
              >
                {c.nome} <span className="text-ink-3">({c.artigos})</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {artigos === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      ) : artigos.length === 0 ? (
        <EmptyState
          titulo="Nada por aqui ainda"
          descricao={
            busca
              ? "Nenhum artigo casa com essa busca. Tente outro termo."
              : "A equipe ainda não publicou conteúdos de ajuda."
          }
        />
      ) : (
        <section className="stagger grid gap-3 md:grid-cols-2">
          {artigos.map((a) => (
            <Link key={a.id} href={`/panel/help/${a.slug}`} className="card block p-5">
              {a.categoria && (
                <p className="label-mono mb-1.5">{a.categoria.nome}</p>
              )}
              <h2 className="text-sm font-semibold leading-snug text-ink">
                {a.titulo}
              </h2>
              {a.resumo && (
                <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-ink-2">
                  {a.resumo}
                </p>
              )}
              {(a.videos > 0 || a.documentos > 0) && (
                <p className="mt-2.5 flex gap-3 font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                  {a.videos > 0 && (
                    <span>
                      ▸ {a.videos} vídeo{a.videos > 1 ? "s" : ""}
                    </span>
                  )}
                  {a.documentos > 0 && (
                    <span>
                      ⇩ {a.documentos} anexo{a.documentos > 1 ? "s" : ""}
                    </span>
                  )}
                </p>
              )}
            </Link>
          ))}
        </section>
      )}
    </>
  );
}
