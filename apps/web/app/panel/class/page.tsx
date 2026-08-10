"use client";

/**
 * Class — a porta "navegável" do help desk interno.
 *
 * Dois acervos na mesma página: os MÓDULOS de aprendizagem (trilhas de aulas
 * em sequência — ex.: "Captação 101") e os artigos avulsos, buscáveis por
 * termo ("empenho") e por categoria. As outras duas portas para o mesmo
 * conteúdo são o link compartilhável (/panel/class/<slug>) e o hint
 * contextual (ⓘ ao lado do elemento na tela).
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

interface Modulo {
  id: string;
  titulo: string;
  slug: string;
  descricao?: string | null;
  aulas: number;
}

interface Artigo {
  id: string;
  titulo: string;
  slug: string;
  resumo?: string | null;
  categoria?: { nome: string; slug: string } | null;
  modulo?: { titulo: string; slug: string } | null;
  videos: number;
  documentos: number;
}

export default function ClassPage() {
  const [categorias, setCategorias] = useState<Categoria[] | null>(null);
  const [modulos, setModulos] = useState<Modulo[] | null>(null);
  const [artigos, setArtigos] = useState<Artigo[] | null>(null);
  const [busca, setBusca] = useState("");
  const [categoria, setCategoria] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const [cats, mods] = await Promise.all([
        api.GET("/api/v1/class/categories"),
        api.GET("/api/v1/class/modules"),
      ]);
      setCategorias((cats.data as Categoria[]) ?? []);
      setModulos((mods.data as Modulo[]) ?? []);
    })();
  }, []);

  const carregar = useCallback(async (q: string, cat: string | null) => {
    const { data } = await api.GET("/api/v1/class/articles", {
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
  const buscando = busca.trim() !== "";

  return (
    <>
      <header>
        <h1 className="page-title">Class</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          O que significam os termos, dados e etapas das suas propostas —
          módulos de aulas, artigos, vídeos e materiais preparados pela equipe.
          Onde você vir o ícone <span className="font-mono text-xs">?</span> no
          painel, há um destes conteúdos explicando o dado ao lado.
        </p>
      </header>

      {/* ── Módulos: trilhas de aulas em sequência ─────────────────────
          Somem durante a busca — o resultado da busca já inclui as aulas. */}
      {!buscando && (modulos === null || modulos.length > 0) && (
        <section>
          <h2 className="label-mono mb-3">Módulos</h2>
          {modulos === null ? (
            <div className="grid gap-3 md:grid-cols-2">
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </div>
          ) : (
            <div className="stagger grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {modulos.map((m) => (
                <Link
                  key={m.id}
                  href={`/panel/class/modules/${m.slug}`}
                  className="card block p-5"
                >
                  <p className="mb-1.5 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                    <span className="brand-dot" aria-hidden />
                    Módulo · {m.aulas} aula{m.aulas === 1 ? "" : "s"}
                  </p>
                  <h3 className="text-sm font-semibold leading-snug text-ink">
                    {m.titulo}
                  </h3>
                  {m.descricao && (
                    <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-ink-2">
                      {m.descricao}
                    </p>
                  )}
                </Link>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── Artigos avulsos + busca (a busca alcança as aulas também) ── */}
      <section className="flex flex-col gap-4">
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
          (modulos ?? []).length === 0 || buscando ? (
            <EmptyState
              titulo="Nada por aqui ainda"
              descricao={
                buscando
                  ? "Nenhum conteúdo casa com essa busca. Tente outro termo."
                  : "A equipe ainda não publicou conteúdos no Class."
              }
            />
          ) : null
        ) : (
          <div className="stagger grid gap-3 md:grid-cols-2">
            {artigos.map((a) => (
              <Link key={a.id} href={`/panel/class/${a.slug}`} className="card block p-5">
                {(a.modulo || a.categoria) && (
                  <p className="label-mono mb-1.5">
                    {a.modulo ? `Aula · ${a.modulo.titulo}` : a.categoria!.nome}
                  </p>
                )}
                <h3 className="text-sm font-semibold leading-snug text-ink">
                  {a.titulo}
                </h3>
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
          </div>
        )}
      </section>
    </>
  );
}
