"use client";

/**
 * Admin da Central de ajuda — artigos e categorias.
 *
 * Daqui a equipe cria o conteúdo que responde as dúvidas de vocabulário do
 * gestor ("o que é um empenho?"): artigos de texto com vídeos e documentos
 * anexos, agrupados por categoria. O editor (mídias + hints) fica em
 * /admin/helpdesk/<id>; aqui é a lista, a criação e as categorias.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/Skeleton";

interface Categoria {
  id: string;
  nome: string;
  slug: string;
  artigos: number;
}

interface ArtigoResumo {
  id: string;
  titulo: string;
  slug: string;
  publicado: boolean;
  categoria?: { id?: string; nome: string } | null;
  videos: number;
  documentos: number;
  hints: number;
}

export default function AdminHelpdeskPage() {
  const router = useRouter();
  const [artigos, setArtigos] = useState<ArtigoResumo[] | null>(null);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [titulo, setTitulo] = useState("");
  const [categoriaId, setCategoriaId] = useState("");
  const [novaCategoria, setNovaCategoria] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const [arts, cats] = await Promise.all([
      api.GET("/api/v1/admin/help/articles"),
      api.GET("/api/v1/admin/help/categories"),
    ]);
    if (arts.error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      setArtigos([]);
      return;
    }
    setArtigos((arts.data as ArtigoResumo[]) ?? []);
    setCategorias((cats.data as Categoria[]) ?? []);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function criarArtigo(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    const { data, error } = await api.POST("/api/v1/admin/help/articles", {
      body: {
        titulo,
        categoria_id: categoriaId || null,
        corpo: "",
        publicado: false,
        ordem: 0,
      },
    });
    if (error || !data) {
      setMsg("Falha ao criar o artigo.");
      return;
    }
    // direto para o editor: o fluxo natural é escrever em seguida
    router.push(`/admin/helpdesk/${(data as { id: string }).id}`);
  }

  async function criarCategoria(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    const { error } = await api.POST("/api/v1/admin/help/categories", {
      body: { nome: novaCategoria, ordem: 0 },
    });
    if (error) {
      setMsg("Falha ao criar a categoria.");
      return;
    }
    setNovaCategoria("");
    await carregar();
  }

  async function excluirCategoria(id: string) {
    if (!window.confirm("Excluir a categoria? Os artigos dela ficam sem categoria.")) return;
    await api.DELETE("/api/v1/admin/help/categories/{categoria_id}", {
      params: { path: { categoria_id: id } },
    });
    await carregar();
  }

  return (
    <>
      <header>
        <h1 className="page-title">Central de ajuda</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Artigos, vídeos e materiais que explicam os termos e dados do painel
          (ex.: &ldquo;o que é um empenho?&rdquo;). Cada artigo pode virar um
          hint <span className="font-mono text-xs">?</span> ao lado do dado que
          ele explica — isso se configura dentro do artigo.
        </p>
      </header>

      {msg && <p className="text-sm text-warn">{msg}</p>}

      <form onSubmit={criarArtigo} className="card flex flex-wrap items-end gap-3 p-5">
        <label className="flex min-w-64 flex-1 flex-col gap-1.5">
          <span className="field-label">Novo artigo</span>
          <input
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ex.: O que é um empenho?"
            required
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Categoria</span>
          <select
            value={categoriaId}
            onChange={(e) => setCategoriaId(e.target.value)}
            className="input w-48"
          >
            <option value="">Sem categoria</option>
            {categorias.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn btn-primary">
          Criar e escrever
        </button>
      </form>

      {artigos === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : (
        <ul className="card flex flex-col divide-y divide-hairline px-5">
          {artigos.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-3 py-3.5">
              <div className="min-w-48 flex-1">
                <Link
                  href={`/admin/helpdesk/${a.id}`}
                  className="text-sm tracking-tight text-ink hover:underline"
                >
                  {a.titulo}
                </Link>
                <p className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                  {a.categoria && <span>{a.categoria.nome}</span>}
                  <span>/{a.slug}</span>
                  {a.videos > 0 && <span>▸ {a.videos} vídeo(s)</span>}
                  {a.documentos > 0 && <span>⇩ {a.documentos} anexo(s)</span>}
                  {a.hints > 0 && <span>? {a.hints} hint(s)</span>}
                </p>
              </div>
              <StatusBadge tone={a.publicado ? "success" : "neutral"}>
                {a.publicado ? "publicado" : "rascunho"}
              </StatusBadge>
              <Link href={`/admin/helpdesk/${a.id}`} className="btn btn-ghost btn-sm">
                Editar
              </Link>
            </li>
          ))}
          {artigos.length === 0 && (
            <li className="py-3.5 text-sm text-ink-3">
              Nenhum artigo ainda — crie o primeiro acima.
            </li>
          )}
        </ul>
      )}

      <section className="card p-5">
        <h2 className="label-mono mb-3 border-b border-hairline pb-2">Categorias</h2>
        <form onSubmit={criarCategoria} className="mb-3 flex flex-wrap items-end gap-3">
          <label className="flex min-w-56 flex-col gap-1.5">
            <span className="field-label">Nova categoria</span>
            <input
              value={novaCategoria}
              onChange={(e) => setNovaCategoria(e.target.value)}
              placeholder="Ex.: Orçamento e finanças"
              required
              className="input"
            />
          </label>
          <button type="submit" className="btn btn-ghost">
            Adicionar
          </button>
        </form>
        <ul className="flex flex-wrap gap-2">
          {categorias.map((c) => (
            <li
              key={c.id}
              className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1 text-sm text-ink-2"
            >
              {c.nome}
              <span className="font-mono text-[11px] text-ink-3">{c.artigos}</span>
              <button
                onClick={() => void excluirCategoria(c.id)}
                title="Excluir categoria"
                className="text-ink-3 transition-colors hover:text-ink"
              >
                ×
              </button>
            </li>
          ))}
          {categorias.length === 0 && (
            <li className="text-sm text-ink-3">Nenhuma categoria ainda.</li>
          )}
        </ul>
      </section>
    </>
  );
}
